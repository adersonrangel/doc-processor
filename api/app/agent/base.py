"""Interfaz del agente, límites y utilidades de traza (S9, S10, S13)."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass

from app.config import Settings


class AgentError(RuntimeError):
    """Fallo del agente: el worker marca el job como `error` (sin fallback)."""


@dataclass(frozen=True)
class AgentContext:
    """Metadatos del archivo que recibe el agente."""

    job_id: str
    original_filename: str
    content_type: str | None = None
    size_bytes: int | None = None
    file_path: str | None = None
    file_sha256: str | None = None

    def metadata(self) -> dict:
        return {
            "job_id": self.job_id,
            "original_filename": self.original_filename,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "file_path": self.file_path,
            "file_sha256": self.file_sha256,
        }


@dataclass(frozen=True)
class AgentLimits:
    max_iterations: int = 5


#: Callback para registrar un paso de traza: `(step, detail)`.
StepRecorder = Callable[[str, "str | None"], None]


def json_detail(**kwargs) -> str:
    """Serializa el detalle de un paso a JSON (texto plano, S13)."""
    return json.dumps(kwargs, ensure_ascii=False, default=str, sort_keys=True)


class AgentRunner(ABC):
    """Contrato común de backends del agente."""

    backend: str = "base"

    def __init__(self, limits: AgentLimits | None = None) -> None:
        self.limits = limits or AgentLimits()

    @abstractmethod
    def run(self, ctx: AgentContext, record: StepRecorder) -> str:
        """Ejecuta el agente y devuelve el `result` esperado."""


def build_runner(settings: Settings) -> AgentRunner:
    """Selecciona el backend según `AGENT_BACKEND`."""
    from app.agent.deterministic import DeterministicAgent
    from app.agent.openrouter import OpenRouterAgent

    limits = AgentLimits(max_iterations=settings.max_agent_iterations)
    backend = (settings.agent_backend or "deterministic").strip().lower()
    if backend == "openrouter":
        return OpenRouterAgent(
            limits=limits,
            api_key=settings.openrouter_api_key_value,
            model=settings.openrouter_model,
        )
    return DeterministicAgent(limits=limits)
