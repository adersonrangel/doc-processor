"""Pruebas de la API y del pipeline del worker (DB temporal SQLite)."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, get_engine
from app.main import app
from app.models import Base, Job, JobStep
from app.worker import process_job

settings = get_settings()


@pytest.fixture(autouse=True)
def sent_jobs(monkeypatch):
    """Evita contactar el broker: registra los job_id encolados."""
    calls: list[str] = []
    monkeypatch.setattr("app.main.enqueue_job", lambda job_id: calls.append(job_id))
    return calls


@pytest.fixture()
def client():
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client, name="a.pdf", data=b"%PDF-1.4 hola", ctype="application/pdf"):
    return client.post("/api/jobs", files={"file": (name, data, ctype)})


def _make_job(session, filename="doc.pdf", created_at=None) -> Job:
    job = Job(
        original_filename=filename,
        status="pending",
        content_type="application/pdf",
        size_bytes=10,
        file_path="/tmp/noexiste.pdf",
        file_sha256="abc",
    )
    if created_at is not None:
        job.created_at = created_at
        job.updated_at = created_at
    session.add(job)
    session.commit()
    return job


# ---- health ---------------------------------------------------------------


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


# ---- POST /api/jobs -------------------------------------------------------


def test_create_job_returns_202_pending_and_enqueues(client, sent_jobs):
    response = _upload(client)
    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"job_id", "status"}
    assert body["status"] == "pending"
    uuid.UUID(body["job_id"])  # es un UUID válido
    assert sent_jobs == [body["job_id"]]


def test_create_job_stores_file_and_hash(client):
    data = b"%PDF-1.4 contenido de prueba"
    response = _upload(client, name="informe.pdf", data=data)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    session = SessionLocal()
    job = session.get(Job, uuid.UUID(job_id))
    assert job is not None
    assert job.original_filename == "informe.pdf"
    assert job.content_type == "application/pdf"
    assert job.size_bytes == len(data)
    assert job.file_sha256 == hashlib.sha256(data).hexdigest()
    assert job.file_path is not None
    stored = Path(job.file_path)
    assert stored.exists()
    assert stored.read_bytes() == data
    assert stored.parent.name == job_id
    session.close()


def test_create_job_rejects_bad_extension(client, sent_jobs):
    response = _upload(client, name="virus.exe", data=b"MZ", ctype="application/octet-stream")
    assert response.status_code == 400
    assert "Extensión no permitida" in response.json()["detail"]
    assert sent_jobs == []


def test_create_job_rejects_oversize(client, sent_jobs, monkeypatch):
    monkeypatch.setattr(settings, "max_file_size_mb", 0)
    response = _upload(client, data=b"demasiado grande")
    assert response.status_code == 400
    assert "tamaño máximo" in response.json()["detail"]
    assert sent_jobs == []


# ---- GET /api/jobs/{job_id} -----------------------------------------------


def test_get_job_full_shape(client):
    response = _upload(client, name="carta.docx", data=b"contenido", ctype="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    job_id = response.json()["job_id"]

    got = client.get(f"/api/jobs/{job_id}")
    assert got.status_code == 200
    body = got.json()
    assert body["job_id"] == job_id
    assert body["status"] == "pending"
    assert body["original_filename"] == "carta.docx"
    assert body["size_bytes"] == len(b"contenido")
    assert body["result"] is None
    assert body["error"] is None
    assert body["created_at"]
    assert body["updated_at"]


def test_get_job_unknown_returns_404(client):
    response = client.get(f"/api/jobs/{uuid.uuid4()}")
    assert response.status_code == 404


def test_get_job_invalid_uuid_returns_404(client):
    response = client.get("/api/jobs/no-es-un-uuid")
    assert response.status_code == 404


# ---- GET /api/jobs --------------------------------------------------------


def test_list_jobs_newest_first(client):
    session = SessionLocal()
    now = datetime.now(timezone.utc)
    older = _make_job(session, filename="viejo.pdf", created_at=now - timedelta(minutes=5))
    newer = _make_job(session, filename="nuevo.pdf", created_at=now)
    session.close()

    response = client.get("/api/jobs")
    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert [j["job_id"] for j in jobs] == [str(newer.id), str(older.id)]
    assert set(jobs[0]) == {"job_id", "status", "original_filename", "created_at"}


def test_list_jobs_caps_at_50(client):
    session = SessionLocal()
    now = datetime.now(timezone.utc)
    for i in range(55):
        _make_job(session, filename=f"f{i}.pdf", created_at=now + timedelta(seconds=i))
    session.close()

    response = client.get("/api/jobs")
    assert response.status_code == 200
    jobs = response.json()["jobs"]
    assert len(jobs) == 50
    # newest first
    assert jobs[0]["original_filename"] == "f54.pdf"


# ---- worker pipeline ------------------------------------------------------


def test_worker_pipeline_sets_ready_and_records_steps(client):
    session = SessionLocal()
    job = _make_job(session)
    job_id = str(job.id)

    result = process_job(job_id)
    assert result == "doc.pdf"

    session.expire_all()
    refreshed = session.get(Job, job.id)
    assert refreshed.status == "ready"
    assert refreshed.result == "doc.pdf"
    assert refreshed.error_message is None

    steps = (
        session.execute(select(JobStep).where(JobStep.job_id == job.id)).scalars().all()
    )
    names = [s.step for s in steps]
    assert "extract" in names
    assert "validate" in names
    assert any(n.startswith("agent.") for n in names)
    session.close()


def test_worker_pipeline_is_idempotent(client):
    session = SessionLocal()
    job = _make_job(session)
    job_id = str(job.id)

    process_job(job_id)
    session.expire_all()
    first_steps = (
        session.execute(select(JobStep).where(JobStep.job_id == job.id)).scalars().all()
    )
    first_count = len(first_steps)

    process_job(job_id)
    session.expire_all()
    second_steps = (
        session.execute(select(JobStep).where(JobStep.job_id == job.id)).scalars().all()
    )
    assert len(second_steps) == first_count

    jobs = session.execute(select(Job)).scalars().all()
    assert len(jobs) == 1
    assert jobs[0].status == "ready"
    session.close()


def test_worker_marks_error_on_unknown_job(client):
    from app.worker import JobProcessingError

    with pytest.raises(JobProcessingError):
        process_job(str(uuid.uuid4()))
