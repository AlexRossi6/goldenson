from sqlalchemy.ext.asyncio import AsyncSession

from goldenson_api.db.models.local_ai_settings import LocalAISettings


class LocalAISettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self) -> LocalAISettings:
        settings = await self._session.get(LocalAISettings, "default")
        if settings is None:
            settings = LocalAISettings(id="default")
            self._session.add(settings)
            await self._session.flush()
        return settings

    async def select_model(self, model_id: str | None) -> LocalAISettings:
        settings = await self.get()
        settings.selected_model = model_id
        await self._session.flush()
        return settings
