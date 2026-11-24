"""API FastAPI: endpoints, CORS y creación de tablas al arrancar.

Contrato en el spec (``odd/tasks/doc-processor-prototype.md``): responde con el
`job_id` sin esperar al agente (S8).
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import create_all, get_db
from app.models import Job
from app.schemas import (
    HealthResponse,
    JobCreateResponse,
    JobListItem,
    JobListResponse,
    JobResponse,
    parse_job_id,
)
from app.storage import FileTooLargeError, save_upload
from app.validation import ValidationError, validate_extension
from app.worker import enqueue_job

settings = get_settings()

MAX_JOBS_IN_LIST = 50


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_all()
    yield


app = FastAPI(title="doc-processor-prototype", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True)


@app.post("/api/jobs", status_code=202, response_model=JobCreateResponse)
def create_job(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> JobCreateResponse:
    filename = file.filename or ""
    try:
        validate_extension(filename, settings.allowed_extensions_list)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_id = uuid.uuid4()
    try:
        stored = save_upload(
            file.file,
            job_id=str(job_id),
            original_filename=filename,
            storage_dir=settings.storage_path,
            max_bytes=settings.max_file_size_bytes,
        )
    except FileTooLargeError:
        raise HTTPException(
            status_code=400,
            detail=f"El archivo supera el tamaño máximo de {settings.max_file_size_mb} MB",
        ) from None
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job = Job(
        id=job_id,
        status="pending",
        original_filename=filename,
        content_type=file.content_type,
        size_bytes=stored.size_bytes,
        file_path=str(stored.path),
        file_sha256=stored.sha256,
    )
    db.add(job)
    db.commit()

    enqueue_job(str(job.id))
    return JobCreateResponse(job_id=str(job.id), status=job.status)


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, db: Session = Depends(get_db)) -> JobResponse:
    job_uuid = parse_job_id(job_id)
    job = db.get(Job, job_uuid) if job_uuid is not None else None
    if job is None:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    return JobResponse.from_job(job)


@app.get("/api/jobs", response_model=JobListResponse)
def list_jobs(db: Session = Depends(get_db)) -> JobListResponse:
    rows = (
        db.execute(select(Job).order_by(Job.created_at.desc(), Job.id.desc()).limit(MAX_JOBS_IN_LIST))
        .scalars()
        .all()
    )
    return JobListResponse(jobs=[JobListItem.from_job(job) for job in rows])
