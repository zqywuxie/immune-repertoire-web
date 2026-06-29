"""Pydantic domain models matching the stable API surface.

These are auto-generated from docs/api/openapi-draft.yaml during Phase 5.
For now they mirror the OpenAPI spec manually as a starting point.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Pagination ───────────────────────────────────────────────────────

class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int = 0


# ── Project ──────────────────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    institution: Optional[str] = None
    cooperation_level: Optional[str] = None
    description: Optional[str] = None
    status: str = "active"


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    institution: Optional[str] = None
    cooperation_level: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectSummary(BaseModel):
    id: str
    name: str
    user_id: Optional[int] = None
    institution: Optional[str] = None
    cooperation_level: Optional[str] = None
    description: Optional[str] = None
    status: str
    asset_counts: dict[str, int] = Field(default_factory=dict)
    sample_count: int = 0
    result_count: int = 0
    group_spec_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    projects: list[ProjectSummary]


class ProjectDetail(ProjectSummary):
    assets: list["Asset"] = Field(default_factory=list)
    group_specs: list[dict] = Field(default_factory=list)
    samples_preview: list[dict] = Field(default_factory=list)


# ── Asset ────────────────────────────────────────────────────────────

class Asset(BaseModel):
    id: str
    project_id: str
    asset_type: str
    original_name: str
    storage_path: str
    storage_uri: Optional[str] = None
    mime_type: Optional[str] = None
    size: int = 0
    metadata: dict = Field(default_factory=dict)
    uploaded_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    assets: list[Asset]
    pagination: Optional[Pagination] = None


class AssetUploadResponse(BaseModel):
    assets: list[Asset]


# ── Job ──────────────────────────────────────────────────────────────

class JobSummary(BaseModel):
    id: str
    job_id: Optional[str] = None
    job_type: str
    module: str
    status: str = "queued"
    progress: float = 0.0
    stage: Optional[str] = None
    detail: Optional[str] = None
    payload: dict = Field(default_factory=dict)
    result: dict = Field(default_factory=dict)
    error: Optional[str] = None
    project_id: Optional[str] = None
    user_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    success: bool = True
    jobs: list[JobSummary]


class JobModule(BaseModel):
    key: str
    label: str


class JobModulesResponse(BaseModel):
    success: bool = True
    modules: list[JobModule]


class JobOutput(BaseModel):
    label: str
    url: str
    kind: str


class SubmitJobRequest(BaseModel):
    module: str
    payload: dict = Field(default_factory=dict)
    project_id: Optional[str] = None
    force_rerun: bool = False


class SubmitJobResponse(BaseModel):
    success: bool = True
    job_id: str
    task_id: Optional[str] = None
    status_url: Optional[str] = None
    status: Optional[str] = None
    reused_result: bool = False
    result_id: Optional[str] = None
    result: Optional[dict] = None


class JobResultsResponse(BaseModel):
    success: bool = True
    job: JobSummary
    status: str
    result: dict = Field(default_factory=dict)
    outputs: list[JobOutput] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)


# ── Info ─────────────────────────────────────────────────────────────

class AppInfo(BaseModel):
    name: str = "immune-repertoire-api"
    version: str = "0.1.0"
