from fastapi import FastAPI

from goldenson_api.api.routes import router as api_router
from goldenson_api.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
