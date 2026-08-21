from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette import status

from goldenson_api.schemas.common import ErrorBody, ErrorResponse
from goldenson_api.services.errors import (
    BadRequestError,
    ConcurrencyConflictError,
    ConflictError,
    NotFoundError,
)


def _error_payload(
    code: str,
    message: str,
    details: dict[str, object] | None = None,
) -> dict[str, object]:
    payload = ErrorResponse(
        error=ErrorBody(code=code, message=message, details=details or {})
    )
    return payload.model_dump()


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=_error_payload("NOT_FOUND", str(exc)),
        )

    @app.exception_handler(ConcurrencyConflictError)
    async def concurrency_handler(_: Request, exc: ConcurrencyConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_payload(
                "CONCURRENCY_CONFLICT",
                "The resource was modified by another operation.",
                {"reason": str(exc)},
            ),
        )

    @app.exception_handler(ConflictError)
    async def conflict_handler(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_payload("CONFLICT", str(exc)),
        )

    @app.exception_handler(BadRequestError)
    async def bad_request_handler(_: Request, exc: BadRequestError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_payload("BAD_REQUEST", str(exc)),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_payload(
                "VALIDATION_ERROR",
                "Request validation failed.",
                {"issues": exc.errors()},
            ),
        )

    @app.exception_handler(IntegrityError)
    async def integrity_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_error_payload(
                "CONFLICT",
                "The operation conflicts with existing data.",
                {"reason": str(exc.orig) if exc.orig is not None else "integrity error"},
            ),
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_handler(_: Request, __: SQLAlchemyError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=_error_payload("BAD_REQUEST", "Database operation failed."),
        )
