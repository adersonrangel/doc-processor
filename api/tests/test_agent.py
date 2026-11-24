"""Pruebas del agente: determinista, selección de backend y errores de OpenRouter."""

import pytest

from app.agent.base import AgentContext, AgentError, AgentLimits, build_runner
from app.agent.deterministic import DeterministicAgent
from app.agent.openrouter import OpenRouterAgent
from app.config import Settings


def _ctx(**overrides) -> AgentContext:
    base = dict(
        job_id="11111111-1111-1111-1111-111111111111",
        original_filename="contrato.pdf",
        content_type="application/pdf",
        size_bytes=1234,
        file_path="/tmp/contrato.pdf",
        file_sha256="deadbeef",
    )
    base.update(overrides)
    return AgentContext(**base)


def test_deterministic_returns_original_filename():
    steps: list[tuple[str, str | None]] = []
    agent = DeterministicAgent()
    result = agent.run(_ctx(), lambda step, detail=None: steps.append((step, detail)))
    assert result == "contrato.pdf"
    assert steps, "debe registrar al menos un paso"


def test_deterministic_records_iteration_and_tool_steps():
    steps: list[str] = []
    DeterministicAgent().run(_ctx(), lambda step, detail=None: steps.append(step))
    assert any(s.startswith("agent.iteration.") for s in steps)
    assert any(s.startswith("agent.tool.") for s in steps)


def test_deterministic_step_detail_contains_metadata():
    details: list[str] = []
    DeterministicAgent().run(_ctx(), lambda step, detail=None: details.append(detail or ""))
    joined = " ".join(details)
    assert "contrato.pdf" in joined
    assert "deadbeef" in joined


def test_build_runner_defaults_to_deterministic():
    runner = build_runner(Settings(agent_backend="deterministic"))
    assert isinstance(runner, DeterministicAgent)


def test_build_runner_selects_openrouter():
    runner = build_runner(Settings(agent_backend="openrouter", openrouter_api_key="k"))
    assert isinstance(runner, OpenRouterAgent)


def test_build_runner_unknown_backend_falls_back_to_deterministic():
    runner = build_runner(Settings(agent_backend="otro"))
    assert isinstance(runner, DeterministicAgent)


def test_openrouter_without_key_raises_without_network():
    agent = OpenRouterAgent(limits=AgentLimits(max_iterations=5), api_key="")
    with pytest.raises(AgentError) as exc:
        agent.run(_ctx(), lambda step, detail=None: None)
    assert "OPENROUTER_API_KEY" in str(exc.value)


def test_agent_limits_default_max_iterations():
    assert AgentLimits().max_iterations == 5


# ---- backend OpenRouter con cliente simulado (sin red) --------------------


class _Fn:
    def __init__(self, name="get_file_metadata", arguments="{}"):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, call_id="call_1", name="get_file_metadata", arguments="{}"):
        self.id = call_id
        self.function = _Fn(name, arguments)


class _Message:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class _Choice:
    def __init__(self, message):
        self.message = message


class _Response:
    def __init__(self, message):
        self.choices = [_Choice(message)]


class _FakeChat:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def send(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)


class _FakeClient:
    def __init__(self, responses):
        self.chat = _FakeChat(responses)


def _tool_then_answer(filename):
    return [
        _Response(_Message(content=None, tool_calls=[_ToolCall()])),
        _Response(_Message(content=filename, tool_calls=None)),
    ]


def test_openrouter_tool_use_loop_returns_filename():
    agent = OpenRouterAgent(api_key="test-key", model="test/model")
    agent._client = _FakeClient(_tool_then_answer("contrato.pdf"))
    steps: list[str] = []
    result = agent.run(_ctx(), lambda step, detail=None: steps.append(step))

    assert result == "contrato.pdf"
    assert "agent.iteration.1" in steps
    assert "agent.tool.get_file_metadata" in steps
    assert "agent.iteration.2" in steps


def test_openrouter_loop_feeds_tool_result_back_to_model():
    agent = OpenRouterAgent(api_key="test-key")
    client = _FakeClient(_tool_then_answer("contrato.pdf"))
    agent._client = client
    agent.run(_ctx(), lambda step, detail=None: None)

    second_messages = client.chat.calls[1]["messages"]
    assert any(m.get("role") == "tool" for m in second_messages)
    assert any(m.get("role") == "assistant" and m.get("tool_calls") for m in second_messages)


def test_openrouter_cleans_quoted_result():
    agent = OpenRouterAgent(api_key="test-key")
    agent._client = _FakeClient(_tool_then_answer('"contrato.pdf"'))
    assert agent.run(_ctx(), lambda step, detail=None: None) == "contrato.pdf"


def test_openrouter_respects_max_iterations():
    agent = OpenRouterAgent(limits=AgentLimits(max_iterations=2), api_key="test-key")
    always_tool = [_Response(_Message(content=None, tool_calls=[_ToolCall()])) for _ in range(2)]
    agent._client = _FakeClient(always_tool)
    with pytest.raises(AgentError) as exc:
        agent.run(_ctx(), lambda step, detail=None: None)
    assert "iteraciones" in str(exc.value)
