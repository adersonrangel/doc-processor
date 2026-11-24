"""Pruebas de validación de subidas (extensión / MIME / tamaño)."""

import pytest

from app.validation import (
    ValidationError,
    extension_of,
    mime_matches,
    validate_extension,
    validate_size,
    validate_upload,
)

ALLOWED = ["pdf", "xlsx", "docx", "txt"]


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("a.pdf", "pdf"),
        ("b.XLSX", "xlsx"),
        ("c.docx", "docx"),
        ("d.txt", "txt"),
        ("sin_punto", ""),
        ("raro.tar.gz", "gz"),
    ],
)
def test_extension_of(filename, expected):
    assert extension_of(filename) == expected


@pytest.mark.parametrize("filename", ["a.pdf", "b.xlsx", "c.docx", "d.txt", "mayus.PDF"])
def test_validate_extension_accepts_allowed(filename):
    assert validate_extension(filename, ALLOWED) in ALLOWED


@pytest.mark.parametrize("filename", ["virus.exe", "script.sh", "archivo", "foto.png"])
def test_validate_extension_rejects_other(filename):
    with pytest.raises(ValidationError) as exc:
        validate_extension(filename, ALLOWED)
    assert "Extensión no permitida" in str(exc.value)


def test_validate_extension_message_lists_allowed():
    with pytest.raises(ValidationError) as exc:
        validate_extension("virus.exe", ALLOWED)
    assert "pdf" in str(exc.value)


def test_validate_size_accepts_within_cap():
    validate_size(10 * 1024 * 1024, 10)  # exact cap is allowed
    validate_size(1, 10)


def test_validate_size_rejects_over_cap():
    with pytest.raises(ValidationError) as exc:
        validate_size(10 * 1024 * 1024 + 1, 10)
    assert "tamaño máximo" in str(exc.value)


def test_validate_size_ignores_none():
    validate_size(None, 0)


def test_validate_upload_combines_checks():
    validate_upload(
        filename="ok.pdf", allowed_extensions=ALLOWED, max_file_size_mb=10, size_bytes=100
    )
    with pytest.raises(ValidationError):
        validate_upload(
            filename="ok.exe", allowed_extensions=ALLOWED, max_file_size_mb=10, size_bytes=1
        )
    with pytest.raises(ValidationError):
        validate_upload(
            filename="ok.pdf", allowed_extensions=ALLOWED, max_file_size_mb=1,
            size_bytes=2 * 1024 * 1024,
        )


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("a.pdf", "application/pdf"),
        ("a.pdf", "application/octet-stream"),
        ("a.pdf", ""),
        ("a.txt", "text/plain"),
    ],
)
def test_mime_matches_true(filename, content_type):
    assert mime_matches(filename, content_type) is True


@pytest.mark.parametrize(
    ("filename", "content_type"),
    [
        ("a.pdf", "image/png"),
        ("a.xlsx", "text/plain"),
    ],
)
def test_mime_matches_false(filename, content_type):
    assert mime_matches(filename, content_type) is False
