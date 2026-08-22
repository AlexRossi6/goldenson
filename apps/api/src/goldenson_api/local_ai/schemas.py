from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class InstallationState(StrEnum):
    AVAILABLE = "available"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    INSTALLING = "installing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuntimeInstallationState(StrEnum):
    DOWNLOADING = "downloading"
    VERIFYING = "verifying"
    INSTALLING = "installing"
    READY = "ready"
    FAILED = "failed"


class RuntimeStatus(BaseModel):
    installed: bool
    reachable: bool
    usable: bool
    version: str | None = None
    error: str | None = None


class ModelStatus(BaseModel):
    id: str
    name: str
    size_bytes: int
    installed_size_bytes: int | None = None
    required_disk_bytes: int
    role: str
    state: InstallationState
    selected: bool
    recommended: bool
    progress: float | None = Field(default=None, ge=0, le=1)
    downloaded_bytes: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    error: str | None = None


class LocalAIStatus(BaseModel):
    runtime: RuntimeStatus
    selected_model: str | None
    models: list[ModelStatus]
    disk_free_bytes: int | None = None


class SelectModelRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=100)


class ModelActionResponse(BaseModel):
    status: str
    model_id: str


class InstallProgressEvent(BaseModel):
    state: InstallationState
    model_id: str
    progress: float | None = Field(default=None, ge=0, le=1)
    downloaded_bytes: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    message: str | None = None


class RuntimeInstallProgressEvent(BaseModel):
    state: RuntimeInstallationState
    progress: float | None = Field(default=None, ge=0, le=1)
    downloaded_bytes: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    message: str
