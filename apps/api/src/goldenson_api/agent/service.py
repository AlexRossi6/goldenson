from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.agent.schemas import ToolPermission, ToolProposal
from goldenson_api.agent.tools import (
    AgentToolExecutor,
    expected_effect,
    tool_definitions,
    tool_permission,
    validate_tool_arguments,
)
from goldenson_api.db.repositories.agent_audit_repository import AgentAuditRepository
from goldenson_api.inference.provider import (
    ChatMessage,
    LLMProvider,
    LLMProviderTimeoutError,
    LLMResponse,
    LLMToolCall,
)
from goldenson_api.retrieval.service import WorkspaceRetrievalService
from goldenson_api.services.errors import BadRequestError, NotFoundError

_SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*\S+")
_cancel_events: dict[str, asyncio.Event] = {}


class CircuitBreakerError(RuntimeError):
    pass


def _sanitize_text(value: str) -> str:
    return _SECRET_PATTERN.sub(r"\1=[REDACTED]", value)


def sanitize_for_audit(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, item in value.items():
            if any(
                secret in key.casefold()
                for secret in ("key", "token", "secret", "password", "authorization")
            ):
                sanitized[str(key)] = "[REDACTED]"
            else:
                sanitized[str(key)] = sanitize_for_audit(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_for_audit(item) for item in value]
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    return str(value)


def cancel_agent_run(run_id: str) -> bool:
    event = _cancel_events.get(run_id)
    if event is None:
        return False
    event.set()
    return True


def _tool_call_message(call: LLMToolCall) -> dict[str, object]:
    return {
        "id": call.id,
        "type": "function",
        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
    }


def _text_chunks(text: str, size: int = 80) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


class AgentService:
    def __init__(
        self,
        session: AsyncSession,
        provider: LLMProvider,
        *,
        max_tool_calls: int,
        max_run_seconds: float,
        tool_timeout_seconds: float,
    ) -> None:
        self._session = session
        self._provider = provider
        self._max_tool_calls = max_tool_calls
        self._max_run_seconds = max_run_seconds
        self._tool_timeout_seconds = tool_timeout_seconds
        self._audit = AgentAuditRepository(session)

    async def run(self, workspace_id: str, request: str) -> AsyncIterator[dict[str, object]]:
        run = await self._audit.create_run(workspace_id, _sanitize_text(request))
        await self._session.commit()
        cancel_event = asyncio.Event()
        _cancel_events[run.id] = cancel_event
        yield {"type": "run", "run_id": run.id}

        try:
            async with asyncio.timeout(self._max_run_seconds):
                async for event in self._run_loop(run.id, workspace_id, request, cancel_event):
                    yield event
        except asyncio.CancelledError:
            await self._finish_run(run.id, "cancelled")
            raise
        except TimeoutError:
            await self._finish_run(run.id, "stopped", "maximum run duration reached")
            yield {"type": "error", "message": "Agent stopped: maximum run duration reached."}
            yield {"type": "done", "status": "stopped"}
        except CircuitBreakerError as exc:
            await self._finish_run(run.id, "stopped", str(exc))
            yield {"type": "error", "message": f"Agent stopped: {exc}."}
            yield {"type": "done", "status": "stopped"}
        except LLMProviderTimeoutError:
            await self._finish_run(run.id, "error", "local model response timed out")
            yield {
                "type": "error",
                "message": "The local model took too long to respond. Try the request again.",
            }
            yield {"type": "done", "status": "error"}
        except Exception:
            await self._finish_run(run.id, "error", "provider or agent failure")
            yield {"type": "error", "message": "The local agent could not complete this request."}
            yield {"type": "done", "status": "error"}
        finally:
            _cancel_events.pop(run.id, None)

    async def _run_loop(
        self,
        run_id: str,
        workspace_id: str,
        request: str,
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[dict[str, object]]:
        yield {"type": "activity", "message": "Searching your workspace..."}
        retrieval = await WorkspaceRetrievalService(self._session).search(workspace_id, request)
        yield {
            "type": "sources",
            "sources": [source.model_dump(mode="json") for source in retrieval.sources],
        }

        safe_request = _sanitize_text(request)
        safe_context = _sanitize_text(retrieval.context)
        system_prompt = (
            "You are GoldenSon's local workspace assistant. Use only the supplied retrieved "
            "context and validated tools. Never invent sources. Do not request secrets, paths, "
            "SQL, shell commands, environment variables, or arbitrary URLs. For a mutation, call "
            "the appropriate tool; the application will request approval. Keep answers concise.\n\n"
            f"RETRIEVED WORKSPACE CONTEXT:\n{safe_context or 'No relevant content found.'}"
        )
        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=safe_request),
        ]
        executor = AgentToolExecutor(self._session, workspace_id)
        tool_count = 0

        while True:
            if cancel_event.is_set():
                await self._finish_run(run_id, "cancelled")
                yield {"type": "done", "status": "cancelled"}
                return

            response = await self._complete_or_cancel(messages, cancel_event)
            if response is None:
                await self._finish_run(run_id, "cancelled")
                yield {"type": "done", "status": "cancelled"}
                return
            if not response.tool_calls:
                for chunk in _text_chunks(response.content):
                    yield {"type": "text", "content": chunk}
                await self._finish_run(run_id, "completed")
                yield {"type": "done", "status": "completed"}
                return

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=[_tool_call_message(call) for call in response.tool_calls],
                )
            )
            for call in response.tool_calls:
                tool_count += 1
                if tool_count > self._max_tool_calls:
                    raise CircuitBreakerError("maximum tool calls reached")
                arguments = validate_tool_arguments(call.name, call.arguments)
                permission = tool_permission(call.name)
                audit_arguments = sanitize_for_audit(arguments.model_dump(mode="json"))
                assert isinstance(audit_arguments, dict)
                audit_call = await self._audit.create_tool_call(
                    run_id,
                    call.id,
                    call.name,
                    permission.value,
                    audit_arguments,
                    "not_required" if permission == ToolPermission.READ else "pending",
                )
                await self._session.commit()

                if permission != ToolPermission.READ:
                    proposal = ToolProposal(
                        tool_call_id=audit_call.id,
                        tool_name=call.name,
                        permission=permission,
                        arguments=arguments.model_dump(mode="json"),
                        expected_effect=expected_effect(call.name, arguments),
                    )
                    await self._finish_run(run_id, "awaiting_approval")
                    yield {"type": "proposal", "proposal": proposal.model_dump(mode="json")}
                    yield {"type": "done", "status": "awaiting_approval"}
                    return

                yield {"type": "activity", "message": f"Using {call.name}..."}
                result = await asyncio.wait_for(
                    executor.execute(call.name, arguments),
                    timeout=self._tool_timeout_seconds,
                )
                await self._audit.finish_tool_call(
                    audit_call, result_summary=f"{call.name} completed successfully"
                )
                await self._session.commit()
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=json.dumps(sanitize_for_audit(result))[:20000],
                    )
                )

    async def _complete_or_cancel(
        self,
        messages: list[ChatMessage],
        cancel_event: asyncio.Event,
    ) -> LLMResponse | None:
        provider_task = asyncio.create_task(self._provider.complete(messages, tool_definitions()))
        cancel_task = asyncio.create_task(cancel_event.wait())
        try:
            done, _ = await asyncio.wait(
                {provider_task, cancel_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if cancel_task in done:
                provider_task.cancel()
                await asyncio.gather(provider_task, return_exceptions=True)
                return None
            return await provider_task
        finally:
            cancel_task.cancel()
            await asyncio.gather(cancel_task, return_exceptions=True)

    async def _finish_run(self, run_id: str, status: str, error_summary: str | None = None) -> None:
        run = await self._audit.get_run(run_id)
        if run is not None:
            await self._audit.finish_run(run, status, error_summary)
            await self._session.commit()


class ApprovalService:
    def __init__(self, session: AsyncSession, tool_timeout_seconds: float) -> None:
        self._session = session
        self._tool_timeout_seconds = tool_timeout_seconds
        self._audit = AgentAuditRepository(session)

    async def decide(
        self, workspace_id: str, tool_call_id: str, approved: bool
    ) -> dict[str, object]:
        tool_call = await self._audit.get_tool_call(tool_call_id)
        if tool_call is None:
            raise NotFoundError("agent tool call not found")
        run = await self._audit.get_run(tool_call.run_id)
        if run is None or run.workspace_id != workspace_id:
            raise NotFoundError("agent tool call not found")
        if tool_call.approval_state != "pending":
            raise BadRequestError("agent tool call already decided")

        if not approved:
            tool_call.approval_state = "rejected"
            await self._audit.finish_tool_call(tool_call, result_summary="rejected by user")
            await self._audit.finish_run(run, "rejected")
            await self._session.commit()
            return {"status": "rejected", "tool_call_id": tool_call.id}

        arguments = validate_tool_arguments(tool_call.tool_name, tool_call.arguments)
        permission = tool_permission(tool_call.tool_name)
        if permission == ToolPermission.READ:
            raise BadRequestError("READ tools do not require approval")
        tool_call.approval_state = "approved"
        result = await asyncio.wait_for(
            AgentToolExecutor(self._session, workspace_id).execute(tool_call.tool_name, arguments),
            timeout=self._tool_timeout_seconds,
        )
        await self._audit.finish_tool_call(
            tool_call, result_summary=f"{tool_call.tool_name} completed successfully"
        )
        await self._audit.finish_run(run, "completed")
        await self._session.commit()
        return {
            "status": "completed",
            "tool_call_id": tool_call.id,
            "result": result,
        }
