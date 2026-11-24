"""Worker Celery + pipeline por job (S6, S9, S12, S13).

`process_job` es idempotente: reinstala el estado y borra los pasos previos del
job antes de recalcular, de modo que reejecutarlo actualiza en lugar de
duplicar.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from celery import Celery
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.agent.base import AgentContext, AgentError, build_runner, json_detail
from app.config import get_settings
from app.db import SessionLocal, create_all
from app.models import Job, JobStep

logger = logging.getLogger(__name__)

settings = get_settings()

celery_app = Celery(
    "doc_processor",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
    enable_utc=True,
)


class JobProcessingError(RuntimeError):
    """El pipeline no pudo completar el job (el job queda en estado `error`)."""


def enqueue_job(job_id: str) -> None:
    """Encola el procesamiento del job. Punto de indirección para pruebas."""
    process_job.delay(job_id)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _record_step(session: Session, job_id: uuid.UUID, step: str, detail: str | None = None) -> None:
    session.add(JobStep(job_id=job_id, step=step, detail=detail))
    session.commit()


def run_pipeline(job_id: str) -> str:
    """Ejecuta extractor -> agente -> validador para un job existente."""
    create_all()
    session = SessionLocal()
    job_uuid = uuid.UUID(str(job_id))
    try:
        job = session.get(Job, job_uuid)
        if job is None:
            raise JobProcessingError(f"El job {job_id} no existe")

        # Idempotencia (S12): limpiar pasos previos y reiniciar estado.
        session.execute(delete(JobStep).where(JobStep.job_id == job.id))
        job.status = "processing"
        job.result = None
        job.error_message = None
        job.updated_at = _now()
        session.commit()

        ctx = AgentContext(
            job_id=str(job.id),
            original_filename=job.original_filename,
            content_type=job.content_type,
            size_bytes=job.size_bytes,
            file_path=job.file_path,
            file_sha256=job.file_sha256,
        )

        # Extractor: por ahora solo lee/verifica el archivo y sus metadatos.
        _record_step(
            session,
            job.id,
            "extract",
            json_detail(action="read_metadata", file_path=job.file_path, sha256=job.file_sha256),
        )

        def record(step: str, detail: str | None = None) -> None:
            _record_step(session, job.id, step, detail)

        runner = build_runner(settings)
        result = runner.run(ctx, record)

        # Validador: comprueba el formato esperado y produce el entregable.
        matches = result == job.original_filename
        _record_step(session, job.id, "validate", json_detail(result=result, matches_filename=matches))

        job.result = result
        job.status = "ready"
        job.error_message = None
        job.updated_at = _now()
        session.commit()
        return result
    except Exception as exc:
        session.rollback()
        message = str(exc) or exc.__class__.__name__
        try:
            job = session.get(Job, job_uuid)
            if job is not None:
                job.status = "error"
                job.error_message = message
                job.updated_at = _now()
                session.add(
                    JobStep(job_id=job.id, step="error", detail=json_detail(error=message))
                )
                session.commit()
        except Exception:  # pragma: no cover - no enmascarar el error original
            session.rollback()
            logger.exception("No se pudo registrar el error del job %s", job_id)
        logger.exception("Job %s falló: %s", job_id, message)
        if isinstance(exc, JobProcessingError):
            raise
        raise JobProcessingError(message) from exc
    finally:
        session.close()


@celery_app.task(
    bind=True,
    name="process_job",
    time_limit=settings.job_timeout_seconds,
    soft_time_limit=max(1, settings.job_timeout_seconds - 5),
)
def process_job(self, job_id: str) -> str:
    """Tarea Celery: procesa un job ya creado por la API."""
    return run_pipeline(job_id)
