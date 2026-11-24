"""Validación de subidas: extensión, MIME (best-effort) y tamaño.

El rechazo duro es por extensión y tamaño; el MIME se comprueba de forma
tolerante (`mime_matches`) porque los navegadores reportan tipos genéricos.
"""

from __future__ import annotations

from pathlib import Path

# MIME esperados por extensión (se aceptan también tipos genéricos).
_MIME_BY_EXTENSION: dict[str, set[str]] = {
    "pdf": {"application/pdf"},
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-excel",
    },
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
    },
    "txt": {"text/plain"},
}

_GENERIC_MIME = {"", "application/octet-stream", "binary/octet-stream"}


class ValidationError(ValueError):
    """Error de validación de una subida (se traduce a HTTP 400)."""


def extension_of(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix[1:] if suffix.startswith(".") else suffix


def validate_extension(filename: str, allowed_extensions: list[str]) -> str:
    ext = extension_of(filename)
    allowed = {e.lower().lstrip(".") for e in allowed_extensions}
    if not ext or ext not in allowed:
        listado = ", ".join(sorted(allowed))
        mostrada = ext if ext else "(sin extensión)"
        raise ValidationError(
            f"Extensión no permitida: '{mostrada}'. Extensiones permitidas: {listado}"
        )
    return ext


def validate_size(size_bytes: int | None, max_file_size_mb: int) -> None:
    if size_bytes is None:
        return
    cap = max_file_size_mb * 1024 * 1024
    if size_bytes > cap:
        raise ValidationError(
            f"El archivo supera el tamaño máximo de {max_file_size_mb} MB"
        )


def mime_matches(filename: str, content_type: str | None) -> bool:
    """Comprueba el MIME declarado contra la extensión.

    Es best-effort: los tipos genéricos se aceptan siempre y una extensión sin
    MIME conocido no se considera inválida por sí sola.
    """
    declared = (content_type or "").split(";")[0].strip().lower()
    if declared in _GENERIC_MIME:
        return True
    expected = _MIME_BY_EXTENSION.get(extension_of(filename))
    if expected is None:
        return True
    return declared in expected


def validate_upload(
    *,
    filename: str,
    allowed_extensions: list[str],
    max_file_size_mb: int,
    size_bytes: int | None = None,
) -> None:
    validate_extension(filename, allowed_extensions)
    validate_size(size_bytes, max_file_size_mb)
