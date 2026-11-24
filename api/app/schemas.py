"""Esquemas Pydantic de request/response (contrato de la API)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models import Job


class JobCreateResponse(BaseModel):
    job_id: str
    status: str


class JobResponse(BaseModel):
    job_id: str
    status: str
    original_filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    result: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> "JobResponse":
        return cls(
            job_id=str(job.id),
            status=job.status,
            original_filename=job.original_filename,
            content_type=job.content_type,
            size_bytes=job.size_bytes,
            result=job.result,
            error=job.error_message,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )


class JobListItem(BaseModel):
    job_id: str
    status: str
    original_filename: str
    created_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> "JobListItem":
        return cls(
            job_id=str(job.id),
            status=job.status,
            original_filename=job.original_filename,
            created_at=job.created_at,
        )


class JobListResponse(BaseModel):
    jobs: list[JobListItem]


class HealthResponse(BaseModel):
    ok: bool


def parse_job_id(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
