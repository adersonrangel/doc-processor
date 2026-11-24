"""Backend OpenRouter: agente real con tool-use (S4).

Usa el SDK oficial de OpenRouter (`openrouter`) con la API de chat compatible
con OpenAI. El agente recibe los metadatos del archivo, dispone de una única
herramienta (`get_file_metadata`) y debe responder con el nombre del archivo.

Si falta la API key o la llamada falla, se lanza `AgentError`: el worker marca
el job como `error` y NO hay fallback silencioso al backend determinista.
"""

from __future__ import annotations

import json

from app.agent.base import AgentContext, AgentError, AgentLimits, AgentRunner, StepRecorder, json_detail

SYSTEM_PROMPT = (
    "Eres un agente de procesamiento de documentos. Recibes los metadatos de un "
    "archivo subido. Debes llamar a la herramienta `get_file_metadata` para "
    "obtenerlos y después responder ÚNICAMENTE con el nombre original del "
    "archivo, sin comillas, sin texto adicional y sin formato."
)

USER_PROMPT = (
    "Archivo subido: {filename}. Usa la herramienta get_file_metadata y "
    "devuelve el nombre original del archivo."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_file_metadata",
            "description": "Devuelve los metadatos básicos del archivo subido.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }
]


class OpenRouterAgent(AgentRunner):
    backend = "openrouter"

    def __init__(
        self,
        limits: AgentLimits | None = None,
        api_key: str = "",
        model: str = "",
    ) -> None:
        super().__init__(limits)
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from openrouter import OpenRouter
            except ImportError as exc:  # pragma: no cover - dependencia declarada
                raise AgentError("El SDK 'openrouter' no está instalado") from exc
            self._client = OpenRouter(
                api_key=self.api_key,
                x_open_router_title="doc-processor-prototype",
            )
        return self._client

    def _execute_tool(self, name: str, ctx: AgentContext) -> dict:
        if name == "get_file_metadata":
            return ctx.metadata()
        raise AgentError(f"Herramienta desconocida: {name!r}")

    @staticmethod
    def _clean_result(content: str) -> str:
        text = (content or "").strip()
        # El modelo puede envolver el nombre en comillas o backticks.
        for left, right in (("`", "`"), ('"', '"'), ("'", "'")):
            if text.startswith(left) and text.endswith(right) and len(text) >= 2:
                text = text[1:-1].strip()
        return text

    def run(self, ctx: AgentContext, record: StepRecorder) -> str:
        if not self.api_key:
            raise AgentError(
                "OPENROUTER_API_KEY no configurada: no se puede usar AGENT_BACKEND=openrouter"
            )
        client = self._get_client()

        messages: list[dict] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT.format(filename=ctx.original_filename)},
        ]

        for iteration in range(1, self.limits.max_iterations + 1):
            record(
                f"agent.iteration.{iteration}",
                json_detail(backend=self.backend, model=self.model or "(default)"),
            )
            try:
                kwargs: dict = {"messages": messages, "tools": TOOLS, "temperature": 0}
                if self.model:
                    kwargs["model"] = self.model
                response = client.chat.send(**kwargs)
            except Exception as exc:  # red, timeout, créditos, respuesta inesperada
                raise AgentError(f"OpenRouter falló: {type(exc).__name__}: {exc}") from exc

            message = response.choices[0].message if response.choices else None
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if tool_calls:
                messages.append(self._assistant_message(message, tool_calls))
                for call in tool_calls:
                    function = getattr(call, "function", None)
                    name = getattr(function, "name", "") or "unknown"
                    arguments = getattr(function, "arguments", "") or ""
                    record(f"agent.tool.{name}", json_detail(tool=name, arguments=arguments))
                    result = self._execute_tool(name, ctx)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": getattr(call, "id", "") or "",
                            "content": json.dumps(result, ensure_ascii=False, default=str),
                        }
                    )
                continue

            content = self._clean_result(getattr(message, "content", None) or "")
            if content:
                return content

        raise AgentError(
            f"El agente no produjo un resultado en {self.limits.max_iterations} iteraciones"
        )

    @staticmethod
    def _assistant_message(message, tool_calls) -> dict:
        return {
            "role": "assistant",
            "content": getattr(message, "content", None) or "",
            "tool_calls": [
                {
                    "id": getattr(call, "id", "") or "",
                    "type": "function",
                    "function": {
                        "name": getattr(getattr(call, "function", None), "name", "") or "",
                        "arguments": getattr(getattr(call, "function", None), "arguments", "") or "{}",
                    },
                }
                for call in tool_calls
            ],
        }
