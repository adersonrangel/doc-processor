"""Configuración común de pruebas.

Antes de importar cualquier módulo de `app`, redirige la base de datos a un
SQLite temporal y el almacenamiento a un directorio temporal, de modo que las
pruebas NUNCA tocan la base `prototipo` real ni dejan archivos en el repo.
"""

import os
import shutil
import tempfile
from pathlib import Path

# Directorio de scratch fuera del árbol de trabajo.
_SCRATCH = Path(tempfile.mkdtemp(prefix="docproc-tests-"))

# Variables de entorno (tienen prioridad sobre .env en pydantic-settings).
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_SCRATCH / 'test.sqlite3'}"
os.environ["STORAGE_DIR"] = str(_SCRATCH / "uploads")
os.environ["AGENT_BACKEND"] = "deterministic"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["OPENROUTER_MODEL"] = ""
os.environ["REDIS_URL"] = "redis://localhost:6379/15"


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    shutil.rmtree(_SCRATCH, ignore_errors=True)
