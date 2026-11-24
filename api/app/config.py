"""Configuración del backend, cargada desde variables de entorno / `.env`.

Se usa `pydantic-settings` para tener tipos validados y una sola fuente de
verdad. El `.env` vive junto a este paquete (`api/.env`) y se resuelve por ruta
absoluta, así el backend funciona aunque se ejecute desde otro directorio.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# api/app/config.py -> parents[0] = app/, parents[1] = api/, parents[2] = raíz del repo.
_API_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _API_DIR.parent
_ENV_FILE = _API_DIR / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Infraestructura ya levantada (S15, S16).
    database_url: str = "postgresql+psycopg://arangel:Qazw5xedc@localhost:5432/prototipo"
    redis_url: str = "redis://localhost:6379/0"

    # Almacenamiento en disco local (S14). Ruta relativa a la raíz del repo.
    storage_dir: str = "api/storage/uploads"

    # Límites (S10).
    max_file_size_mb: int = 10
    allowed_extensions: str = "pdf,xlsx,docx,txt"
    max_agent_iterations: int = 5
    job_timeout_seconds: int = 120
    file_retention_days: int = 7

    # Agente.
    agent_backend: str = "deterministic"
    openrouter_api_key: SecretStr = SecretStr("")
    openrouter_model: str = ""

    # CORS.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [e.strip().lower().lstrip(".") for e in self.allowed_extensions.split(",") if e.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def openrouter_api_key_value(self) -> str:
        return self.openrouter_api_key.get_secret_value().strip()

    @property
    def storage_path(self) -> Path:
        """Resuelve `STORAGE_DIR` a una ruta absoluta y portable.

        Acepta rutas absolutas o relativas. Si la ruta ya empieza por el nombre
        del paquete (`api/`, como en el spec) se ancla a la raíz del repo; en
        caso contrario se ancla al directorio `api/`.
        """
        raw = Path(self.storage_dir)
        if raw.is_absolute():
            return raw
        base = _REPO_ROOT if raw.parts and raw.parts[0] == _API_DIR.name else _API_DIR
        return (base / raw).resolve()

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
