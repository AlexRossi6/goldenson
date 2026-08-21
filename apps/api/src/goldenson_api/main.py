from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from goldenson_api.api.error_handlers import register_error_handlers
from goldenson_api.api.routes import router as api_router
from goldenson_api.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(api_router, prefix=settings.api_prefix)
    return app


app = create_app()
