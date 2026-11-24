"""Backend determinista: sin red, siempre disponible (S4).

Devuelve el nombre original del archivo (S2). Es el backend por defecto para
que el prototipo funcione sin `OPENROUTER_API_KEY`.
"""

from __future__ import annotations

from app.agent.base import AgentContext, AgentRunner, StepRecorder, json_detail


class DeterministicAgent(AgentRunner):
    backend = "deterministic"

    def run(self, ctx: AgentContext, record: StepRecorder) -> str:
        # Lectura/verificación de metadatos (extractor sin extracción real, S9).
        record(
            "agent.iteration.1",
            json_detail(backend=self.backend, action="read_metadata", metadata=ctx.metadata()),
        )
        record(
            "agent.tool.get_file_metadata",
            json_detail(tool="get_file_metadata", result={"original_filename": ctx.original_filename}),
        )
        return ctx.original_filename
