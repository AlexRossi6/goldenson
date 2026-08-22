from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.agent.schemas import ToolPermission, ToolProposal
from goldenson_api.agent.tools import (
    AgentToolExecutor,
    expected_effect,
    tool_definitions,
    tool_permission,
    validate_tool_arguments,
)
from goldenson_api.db.models.agent_audit import AgentRun, AgentToolCall
from goldenson_api.db.repositories.agent_audit_repository import AgentAuditRepository
from goldenson_api.inference.provider import (
    ChatMessage,
    LLMProvider,
    LLMProviderTimeoutError,
    LLMResponse,
    LLMToolCall,
)
from goldenson_api.retrieval.service import RetrievalResult, WorkspaceRetrievalService
from goldenson_api.services.errors import BadRequestError, ConflictError, NotFoundError
from goldenson_api.services.page_service import PageService

_SECRET_PATTERN = re.compile(r"(?i)(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*\S+")
_SIMPLE_CREATE_PAGE_PATTERN = re.compile(
    r"^\s*(?:please\s+)?create\s+(?:a\s+)?(?:new\s+)?page\s+"
    r"(?:called|named)\s+(?P<title>.+?)\s*$",
    re.IGNORECASE,
)
logger = logging.getLogger(__name__)
_cancel_events: dict[str, asyncio.Event] = {}
_active_run_ids: set[str] = set()
_TERMINAL_STATUSES = {"completed", "cancelled", "failed", "timed_out"}


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


async def cancel_persisted_agent_run(session: AsyncSession, run_id: str) -> bool:
    repository = AgentAuditRepository(session)
    transitioned = await repository.transition_run(
        run_id,
        {"running", "resuming", "waiting_for_approval"},
        "cancelled",
    )
    if not transitioned:
        await session.rollback()
        return False
    event = _cancel_events.get(run_id)
    if event is not None:
        event.set()
    run = await repository.get_run(run_id)
    if run is not None:
        run.completed_at = run.updated_at
    await session.commit()
    return True


def _tool_call_message(call: LLMToolCall) -> dict[str, object]:
    return {
        "id": call.id,
        "type": "function",
        "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
    }


def _text_chunks(text: str, size: int = 80) -> list[str]:
    return [text[index : index + size] for index in range(0, len(text), size)]


def _serialize_messages(messages: list[ChatMessage]) -> list[dict[str, object]]:
    serialized = sanitize_for_audit(
        [message.model_dump(mode="json", exclude_none=True) for message in messages]
    )
    assert isinstance(serialized, list)
    return [item for item in serialized if isinstance(item, dict)]


def _deserialize_messages(messages: list[dict[str, object]]) -> list[ChatMessage]:
    return [ChatMessage.model_validate(message) for message in messages]


def _is_simple_create_page_request(request: str) -> bool:
    return _SIMPLE_CREATE_PAGE_PATTERN.fullmatch(request) is not None


def _simple_create_page_title(request: str) -> str | None:
    match = _SIMPLE_CREATE_PAGE_PATTERN.fullmatch(request)
    if match is None:
        return None
    title = match.group("title").strip().strip("\"'").removesuffix(".").strip()
    return title if title else None


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
        lifecycle_started = time.monotonic()
        run = await self._audit.create_run(
            workspace_id,
            _sanitize_text(request),
            self._max_run_seconds,
        )
        await self._session.commit()
        logger.debug("agent lifecycle run=%s stage=request duration_ms=%.1f", run.id, 0.0)
        async for event in self._activate_and_execute(
            run, request=request, lifecycle_started=lifecycle_started
        ):
            yield event

    async def reconnect(self, workspace_id: str, run_id: str) -> AsyncIterator[dict[str, object]]:
        run = await self._audit.get_run(run_id)
        if run is None or run.workspace_id != workspace_id:
            raise NotFoundError("agent run not found")
        yield {"type": "run", "run_id": run.id}

        if run.status == "waiting_for_approval":
            pending = await self._audit.get_pending_tool_call(run.id)
            if pending is None:
                raise BadRequestError("agent run has no pending approval")
            arguments = validate_tool_arguments(pending.tool_name, pending.arguments)
            proposal = ToolProposal(
                tool_call_id=pending.id,
                tool_name=pending.tool_name,
                permission=tool_permission(pending.tool_name),
                arguments=arguments.model_dump(mode="json"),
                expected_effect=expected_effect(pending.tool_name, arguments),
            )
            yield {"type": "proposal", "proposal": proposal.model_dump(mode="json")}
            yield {"type": "done", "status": "waiting_for_approval"}
            return
        if run.status in _TERMINAL_STATUSES:
            yield {"type": "done", "status": run.status}
            return
        if run.id in _active_run_ids:
            raise ConflictError("agent run is already active")
        if run.status not in {"running", "resuming"}:
            raise BadRequestError("agent run cannot be resumed")
        transitioned = await self._audit.transition_run(run.id, {"running", "resuming"}, "resuming")
        if not transitioned:
            await self._session.rollback()
            raise ConflictError("agent run is already being resumed")
        await self._session.commit()
        await self._session.refresh(run)
        yield {"type": "activity", "message": "Reconnected — continuing..."}
        async for event in self._activate_and_execute(run):
            if event.get("type") != "run":
                yield event

    async def decide(
        self,
        workspace_id: str,
        tool_call_id: str,
        approved: bool,
    ) -> AsyncIterator[dict[str, object]]:
        tool_call = await self._audit.get_tool_call(tool_call_id)
        if tool_call is None:
            raise NotFoundError("agent tool call not found")
        run = await self._audit.get_run(tool_call.run_id)
        if run is None or run.workspace_id != workspace_id:
            raise NotFoundError("agent tool call not found")

        decision = "approved" if approved else "rejected"
        if tool_call.approval_state != "pending":
            if tool_call.approval_state != decision:
                raise BadRequestError("agent tool call already decided differently")
            yield {"type": "activity", "message": "Approval decision already recorded."}
            yield {"type": "done", "status": run.status}
            return
        if run.status != "waiting_for_approval":
            raise BadRequestError("agent run is not waiting for approval")
        if run.remaining_seconds <= 0:
            await self._finish_run(run.id, "timed_out", "maximum run duration reached")
            yield {"type": "error", "message": "Agent stopped: maximum run duration reached."}
            yield {"type": "done", "status": "timed_out"}
            return

        arguments = validate_tool_arguments(tool_call.tool_name, tool_call.arguments)
        permission = tool_permission(tool_call.tool_name)
        if permission == ToolPermission.READ:
            raise BadRequestError("READ tools do not require approval")
        claimed = await self._audit.claim_tool_call_decision(tool_call.id, decision)
        transitioned = await self._audit.transition_run(
            run.id, {"waiting_for_approval"}, "resuming"
        )
        if not claimed or not transitioned:
            await self._session.rollback()
            raise ConflictError("agent approval was already claimed")
        await self._session.commit()
        await self._session.refresh(tool_call)
        await self._session.refresh(run)

        message = "Approved — continuing..." if approved else "Rejected — continuing..."
        yield {"type": "activity", "message": message}
        messages = _deserialize_messages(run.messages)
        if approved:
            result = await self._execute_approved_tool(run, tool_call, arguments)
            if result is None:
                yield {"type": "error", "message": "The approved change could not be completed."}
                yield {"type": "done", "status": run.status}
                return
            yield {
                "type": "workspace_changed",
                "tool_name": tool_call.tool_name,
                "result": result,
            }
            tool_content: dict[str, object] = {"status": "approved", "result": result}
        else:
            tool_content = {"status": "rejected", "message": "The user rejected this change."}
            await self._audit.finish_tool_call(
                tool_call,
                result=tool_content,
                result_summary="rejected by user",
            )

        messages.append(
            ChatMessage(
                role="tool",
                tool_call_id=tool_call.provider_call_id,
                content=json.dumps(tool_content),
            )
        )
        await self._audit.save_run_state(
            run,
            messages=_serialize_messages(messages),
            tool_call_count=run.tool_call_count,
            remaining_seconds=run.remaining_seconds,
            status="resuming",
        )
        await self._session.commit()
        async for event in self._activate_and_execute(run):
            if event.get("type") != "run":
                yield event

    async def _activate_and_execute(
        self,
        run: AgentRun,
        *,
        request: str | None = None,
        lifecycle_started: float | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        if run.id in _active_run_ids:
            raise ConflictError("agent run is already active")
        _active_run_ids.add(run.id)
        cancel_event = asyncio.Event()
        _cancel_events[run.id] = cancel_event
        try:
            yield {"type": "run", "run_id": run.id}
            async for event in self._execute_segment(
                run,
                cancel_event,
                request=request,
                lifecycle_started=lifecycle_started,
            ):
                yield event
        finally:
            _cancel_events.pop(run.id, None)
            _active_run_ids.discard(run.id)

    async def _execute_segment(
        self,
        run: AgentRun,
        cancel_event: asyncio.Event,
        *,
        request: str | None,
        lifecycle_started: float | None,
    ) -> AsyncIterator[dict[str, object]]:
        started = time.monotonic()
        try:
            if run.remaining_seconds <= 0:
                raise TimeoutError
            async with asyncio.timeout(run.remaining_seconds):
                if request is not None:
                    retrieval_started = time.monotonic()
                    if _is_simple_create_page_request(request):
                        retrieval = RetrievalResult(context="", sources=[])
                        yield {"type": "activity", "message": "Preparing change..."}
                    else:
                        yield {"type": "activity", "message": "Searching your workspace..."}
                        retrieval = await WorkspaceRetrievalService(self._session).search(
                            run.workspace_id, request
                        )
                    logger.debug(
                        "agent lifecycle run=%s stage=retrieval duration_ms=%.1f skipped=%s",
                        run.id,
                        (time.monotonic() - retrieval_started) * 1000,
                        _is_simple_create_page_request(request),
                    )
                    yield {
                        "type": "sources",
                        "sources": [source.model_dump(mode="json") for source in retrieval.sources],
                    }
                    safe_request = _sanitize_text(request)
                    safe_context = _sanitize_text(retrieval.context)
                    system_prompt = (
                        "You are GoldenSon's local workspace assistant. Use only the supplied "
                        "retrieved context and validated tools. Never invent sources. Do not "
                        "request secrets, paths, SQL, shell commands, environment variables, or "
                        "arbitrary URLs. For a mutation, call exactly one tool; the application "
                        "will request approval. Keep answers concise.\n\n"
                        f"RETRIEVED WORKSPACE CONTEXT:\n"
                        f"{safe_context or 'No relevant content found.'}"
                    )
                    messages = [
                        ChatMessage(role="system", content=system_prompt),
                        ChatMessage(role="user", content=safe_request),
                    ]
                else:
                    messages = _deserialize_messages(run.messages)
                await self._audit.save_run_state(
                    run,
                    messages=_serialize_messages(messages),
                    tool_call_count=run.tool_call_count,
                    remaining_seconds=run.remaining_seconds,
                    status="running",
                )
                await self._session.commit()
                initial_response: LLMResponse | None = None
                if request is not None:
                    title = _simple_create_page_title(request)
                    if title is not None:
                        pages = await PageService(self._session).list_pages(run.workspace_id)
                        root_positions = [
                            page.position for page in pages if page.parent_page_id is None
                        ]
                        initial_response = LLMResponse(
                            tool_calls=[
                                LLMToolCall(
                                    id=f"direct-{uuid4()}",
                                    name="create_page",
                                    arguments={
                                        "title": title,
                                        "parent_page_id": None,
                                        "position": max(root_positions, default=-1) + 1,
                                    },
                                )
                            ]
                        )
                        logger.debug(
                            "agent lifecycle run=%s stage=provider duration_ms=%.1f skipped=True",
                            run.id,
                            0.0,
                        )
                async for event in self._run_loop(
                    run,
                    messages,
                    cancel_event,
                    lifecycle_started=lifecycle_started,
                    initial_response=initial_response,
                ):
                    yield event
        except asyncio.CancelledError:
            if run.status == "running":
                await self._audit.save_run_state(
                    run,
                    messages=run.messages,
                    tool_call_count=run.tool_call_count,
                    remaining_seconds=run.remaining_seconds,
                    status="resuming",
                )
                await self._session.commit()
            raise
        except TimeoutError:
            await self._finish_run(run.id, "timed_out", "maximum run duration reached")
            yield {"type": "error", "message": "Agent stopped: maximum run duration reached."}
            yield {"type": "done", "status": "timed_out"}
        except CircuitBreakerError as exc:
            await self._finish_run(run.id, "failed", str(exc))
            yield {"type": "error", "message": f"Agent stopped: {exc}."}
            yield {"type": "done", "status": "failed"}
        except LLMProviderTimeoutError:
            await self._finish_run(run.id, "timed_out", "local model response timed out")
            yield {
                "type": "error",
                "message": "The local model took too long to respond. Try the request again.",
            }
            yield {"type": "done", "status": "timed_out"}
        except Exception:
            await self._finish_run(run.id, "failed", "provider or agent failure")
            yield {"type": "error", "message": "The local agent could not complete this request."}
            yield {"type": "done", "status": "failed"}
        finally:
            elapsed = time.monotonic() - started
            run.remaining_seconds = max(0, run.remaining_seconds - elapsed)
            await self._session.commit()

    async def _run_loop(
        self,
        run: AgentRun,
        messages: list[ChatMessage],
        cancel_event: asyncio.Event,
        *,
        lifecycle_started: float | None = None,
        initial_response: LLMResponse | None = None,
    ) -> AsyncIterator[dict[str, object]]:
        executor = AgentToolExecutor(self._session, run.workspace_id)

        while True:
            if cancel_event.is_set():
                await self._finish_run(run.id, "cancelled")
                yield {"type": "done", "status": "cancelled"}
                return

            await self._audit.save_run_state(
                run,
                messages=_serialize_messages(messages),
                tool_call_count=run.tool_call_count,
                remaining_seconds=run.remaining_seconds,
                status="running",
            )
            await self._session.commit()
            response: LLMResponse | None
            if initial_response is not None:
                response = initial_response
                initial_response = None
            else:
                provider_started = time.monotonic()
                response = await self._complete_or_cancel(
                    messages,
                    cancel_event,
                    tool_definitions(),
                )
                logger.debug(
                    "agent lifecycle run=%s stage=provider duration_ms=%.1f skipped=False",
                    run.id,
                    (time.monotonic() - provider_started) * 1000,
                )
            if response is None:
                await self._finish_run(run.id, "cancelled")
                yield {"type": "done", "status": "cancelled"}
                return
            messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=[_tool_call_message(call) for call in response.tool_calls] or None,
                )
            )
            if not response.tool_calls:
                for chunk in _text_chunks(response.content):
                    yield {"type": "text", "content": chunk}
                run.messages = _serialize_messages(messages)
                await self._finish_run(run.id, "completed")
                yield {"type": "done", "status": "completed"}
                return

            permissions = [tool_permission(call.name) for call in response.tool_calls]
            if len(response.tool_calls) > 1 and any(
                permission != ToolPermission.READ for permission in permissions
            ):
                raise CircuitBreakerError("model requested multiple changes at once")
            for call in response.tool_calls:
                run.tool_call_count += 1
                if run.tool_call_count > self._max_tool_calls:
                    raise CircuitBreakerError("maximum tool calls reached")
                arguments = validate_tool_arguments(call.name, call.arguments)
                permission = tool_permission(call.name)
                audit_arguments = sanitize_for_audit(arguments.model_dump(mode="json"))
                assert isinstance(audit_arguments, dict)
                audit_call = await self._audit.create_tool_call(
                    run.id,
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
                    await self._audit.save_run_state(
                        run,
                        messages=_serialize_messages(messages),
                        tool_call_count=run.tool_call_count,
                        remaining_seconds=run.remaining_seconds,
                        status="waiting_for_approval",
                    )
                    await self._session.commit()
                    yield {"type": "proposal", "proposal": proposal.model_dump(mode="json")}
                    if lifecycle_started is not None:
                        logger.debug(
                            "agent lifecycle run=%s stage=approval_ready duration_ms=%.1f",
                            run.id,
                            (time.monotonic() - lifecycle_started) * 1000,
                        )
                    yield {"type": "done", "status": "waiting_for_approval"}
                    return

                yield {"type": "activity", "message": f"Using {call.name}..."}
                result = await asyncio.wait_for(
                    executor.execute(call.name, arguments),
                    timeout=self._tool_timeout_seconds,
                )
                sanitized_result = sanitize_for_audit(result)
                assert isinstance(sanitized_result, dict)
                await self._audit.finish_tool_call(
                    audit_call,
                    result=sanitized_result,
                    result_summary=f"{call.name} completed successfully",
                )
                await self._session.commit()
                messages.append(
                    ChatMessage(
                        role="tool",
                        tool_call_id=call.id,
                        content=json.dumps(sanitized_result)[:20000],
                    )
                )

    async def _execute_approved_tool(
        self,
        run: AgentRun,
        tool_call: AgentToolCall,
        arguments: BaseModel,
    ) -> dict[str, object] | None:
        started = time.monotonic()
        run_id = run.id
        tool_call_id = tool_call.id
        remaining_seconds = run.remaining_seconds
        try:
            if run.remaining_seconds <= 0:
                raise TimeoutError
            async with asyncio.timeout(run.remaining_seconds):
                result = await asyncio.wait_for(
                    AgentToolExecutor(self._session, run.workspace_id).execute(
                        tool_call.tool_name, arguments
                    ),
                    timeout=self._tool_timeout_seconds,
                )
            sanitized_result = sanitize_for_audit(result)
            assert isinstance(sanitized_result, dict)
            await self._audit.finish_tool_call(
                tool_call,
                result=sanitized_result,
                result_summary=f"{tool_call.tool_name} completed successfully",
            )
            await self._session.commit()
            return sanitized_result
        except TimeoutError:
            await self._session.rollback()
            tool_call = await self._audit.get_tool_call(tool_call_id) or tool_call
            await self._audit.finish_tool_call(tool_call, error_summary="tool execution timed out")
            await self._finish_run(run_id, "timed_out", "tool execution timed out")
            return None
        except Exception:
            await self._session.rollback()
            tool_call = await self._audit.get_tool_call(tool_call_id) or tool_call
            await self._audit.finish_tool_call(tool_call, error_summary="tool execution failed")
            await self._finish_run(run_id, "failed", "approved tool execution failed")
            return None
        finally:
            run.remaining_seconds = max(0, remaining_seconds - (time.monotonic() - started))

    async def _complete_or_cancel(
        self,
        messages: list[ChatMessage],
        cancel_event: asyncio.Event,
        tools: list[dict[str, object]],
    ) -> LLMResponse | None:
        provider_task = asyncio.create_task(self._provider.complete(messages, tools))
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
