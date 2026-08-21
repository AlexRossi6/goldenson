from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    details: dict[str, object] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody
