from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Result, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.agent_audit import AgentRun, AgentToolCall


class AgentAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(
        self,
        workspace_id: str,
        request: str,
        remaining_seconds: float,
    ) -> AgentRun:
        run = AgentRun(
            workspace_id=workspace_id,
            request=request,
            remaining_seconds=remaining_seconds,
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_run(self, run_id: str) -> AgentRun | None:
        return await self._session.get(AgentRun, run_id)

    async def save_run_state(
        self,
        run: AgentRun,
        *,
        messages: list[dict[str, object]],
        tool_call_count: int,
        remaining_seconds: float,
        status: str,
    ) -> None:
        run.messages = messages
        run.tool_call_count = tool_call_count
        run.remaining_seconds = max(0, remaining_seconds)
        run.status = status
        run.updated_at = datetime.now(UTC)
        run.completed_at = None
        await self._session.flush()

    async def transition_run(
        self,
        run_id: str,
        from_statuses: set[str],
        to_status: str,
    ) -> bool:
        statement = (
            update(AgentRun)
            .where(AgentRun.id == run_id, AgentRun.status.in_(from_statuses))
            .values(status=to_status, updated_at=datetime.now(UTC))
        )
        result = await self._session.execute(statement)
        assert isinstance(result, CursorResult)
        return (result.rowcount or 0) == 1

    async def finish_run(
        self, run: AgentRun, status: str, error_summary: str | None = None
    ) -> None:
        run.status = status
        run.error_summary = error_summary
        run.updated_at = datetime.now(UTC)
        run.completed_at = datetime.now(UTC)
        await self._session.flush()

    async def create_tool_call(
        self,
        run_id: str,
        provider_call_id: str,
        tool_name: str,
        permission: str,
        arguments: dict[str, object],
        approval_state: str,
        execution_arguments: dict[str, object] | None = None,
    ) -> AgentToolCall:
        tool_call = AgentToolCall(
            run_id=run_id,
            provider_call_id=provider_call_id,
            tool_name=tool_name,
            permission=permission,
            arguments=arguments,
            execution_arguments=execution_arguments,
            approval_state=approval_state,
        )
        self._session.add(tool_call)
        await self._session.flush()
        return tool_call

    async def get_tool_call(self, tool_call_id: str) -> AgentToolCall | None:
        return await self._session.get(AgentToolCall, tool_call_id)

    async def get_pending_tool_call(self, run_id: str) -> AgentToolCall | None:
        statement = select(AgentToolCall).where(
            AgentToolCall.run_id == run_id,
            AgentToolCall.approval_state == "pending",
        )
        result: Result[tuple[AgentToolCall]] = await self._session.execute(statement)
        return result.scalar_one_or_none()

    async def claim_tool_call_decision(self, tool_call_id: str, decision: str) -> bool:
        statement = (
            update(AgentToolCall)
            .where(
                AgentToolCall.id == tool_call_id,
                AgentToolCall.approval_state == "pending",
            )
            .values(approval_state=decision, decision_at=datetime.now(UTC))
        )
        result = await self._session.execute(statement)
        assert isinstance(result, CursorResult)
        return (result.rowcount or 0) == 1

    async def finish_tool_call(
        self,
        tool_call: AgentToolCall,
        *,
        result: dict[str, object] | None = None,
        result_summary: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        tool_call.result = result
        tool_call.result_summary = result_summary
        tool_call.error_summary = error_summary
        tool_call.completed_at = datetime.now(UTC)
        await self._session.flush()
