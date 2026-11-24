"""Motor SQLAlchemy: engine, fábrica de sesiones y creación de tablas."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base

_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        connect_args: dict = {}
        if url.startswith("sqlite"):
            # TestClient atiende peticiones síncronas en un hilo distinto.
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


def SessionLocal() -> Session:
    """Devuelve una sesión nueva (azúcar sobre la fábrica de sesiones)."""
    return get_session_factory()()


def create_all() -> None:
    """Crea las tablas si no existen (MVP: sin Alembic)."""
    Base.metadata.create_all(bind=get_engine())


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: entrega una sesión y la cierra al terminar."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """Libera el engine cacheado (útil en pruebas que cambian DATABASE_URL)."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None
