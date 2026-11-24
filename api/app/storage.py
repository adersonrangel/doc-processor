"""Almacenamiento de archivos en disco local (S14).

Layout: `{STORAGE_DIR}/{job_id}/{uuid8}_{nombre_seguro}`.
El archivo nunca se guarda en la base de datos; solo se persiste su ruta,
tamaño y sha256.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

_CHUNK_SIZE = 1024 * 1024  # 1 MiB
_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class StorageError(Exception):
    """Error genérico de almacenamiento."""


class FileTooLargeError(StorageError):
    """El archivo supera el tamaño máximo permitido."""


@dataclass(frozen=True)
class StoredFile:
    path: Path
    size_bytes: int
    sha256: str
    stored_name: str


def safe_filename(name: str, max_length: int = 200) -> str:
    """Devuelve un nombre de archivo sin rutas ni caracteres peligrosos."""
    base = Path(name or "").name.strip()
    base = _UNSAFE_RE.sub("_", base).strip("._")
    if not base:
        base = "archivo"
    if len(base) > max_length:
        suffix = Path(base).suffix
        stem = Path(base).stem[: max(1, max_length - len(suffix))]
        base = f"{stem}{suffix}"
    return base


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def save_upload(
    stream: BinaryIO,
    *,
    job_id: str,
    original_filename: str,
    storage_dir: Path,
    max_bytes: int,
) -> StoredFile:
    """Guarda el stream en disco mientras calcula el sha256.

    Aborta y borra el archivo parcial si se supera `max_bytes`.
    """
    safe = safe_filename(original_filename)
    stored_name = f"{uuid.uuid4().hex[:8]}_{safe}"
    dest_dir = Path(storage_dir) / str(job_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / stored_name

    digest = hashlib.sha256()
    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = stream.read(_CHUNK_SIZE)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise FileTooLargeError(
                        f"El archivo supera el tamaño máximo de {max_bytes} bytes"
                    )
                digest.update(chunk)
                out.write(chunk)
    except FileTooLargeError:
        dest.unlink(missing_ok=True)
        raise
    except Exception:
        dest.unlink(missing_ok=True)
        raise

    return StoredFile(
        path=dest,
        size_bytes=total,
        sha256=digest.hexdigest(),
        stored_name=stored_name,
    )
