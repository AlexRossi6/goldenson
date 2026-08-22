from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.agent_audit import AgentRun, AgentToolCall


class AgentAuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_run(self, workspace_id: str, request: str) -> AgentRun:
        run = AgentRun(workspace_id=workspace_id, request=request)
        self._session.add(run)
        await self._session.flush()
        return run

    async def get_run(self, run_id: str) -> AgentRun | None:
        return await self._session.get(AgentRun, run_id)

    async def finish_run(
        self, run: AgentRun, status: str, error_summary: str | None = None
    ) -> None:
        run.status = status
        run.error_summary = error_summary
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
    ) -> AgentToolCall:
        tool_call = AgentToolCall(
            run_id=run_id,
            provider_call_id=provider_call_id,
            tool_name=tool_name,
            permission=permission,
            arguments=arguments,
            approval_state=approval_state,
        )
        self._session.add(tool_call)
        await self._session.flush()
        return tool_call

    async def get_tool_call(self, tool_call_id: str) -> AgentToolCall | None:
        return await self._session.get(AgentToolCall, tool_call_id)

    async def finish_tool_call(
        self,
        tool_call: AgentToolCall,
        *,
        result_summary: str | None = None,
        error_summary: str | None = None,
    ) -> None:
        tool_call.result_summary = result_summary
        tool_call.error_summary = error_summary
        tool_call.completed_at = datetime.now(UTC)
        await self._session.flush()
