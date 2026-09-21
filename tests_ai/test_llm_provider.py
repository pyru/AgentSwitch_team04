"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-09-20).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero. They cover offline LLM provider selection and request construction.

Run: python -m pytest tests_ai/test_llm_provider.py -q
"""
from types import SimpleNamespace

import pytest

from prod_agent import config
from prod_agent.agent import ProductionAgent


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    for name in (
        "LLM_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_mcp():
    return SimpleNamespace(session=SimpleNamespace(instance="suryodaya"))


class FakeMessage:
    content = "done"
    tool_calls = []

    def model_dump(self, **kwargs):
        return {"role": "assistant", "content": self.content, "tool_calls": []}


class CapturingLLM:
    def __init__(self):
        self.kwargs = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=FakeMessage())])


def test_default_provider_preserves_openai_client(monkeypatch, fake_mcp):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-openai")
    looked_up = []
    real_env = config.env

    def recording_env(name, default=None):
        looked_up.append(name)
        return real_env(name, default)

    monkeypatch.setattr(config, "env", recording_env)
    agent = ProductionAgent(fake_mcp)

    assert agent.provider == "openai"
    assert agent.model == "gpt-4.1"
    assert str(agent.llm.base_url) == "https://api.openai.com/v1/"
    assert agent.llm.max_retries == 8
    assert not any(name.startswith("OPENROUTER_") for name in looked_up)


def test_openai_model_overrides_default(monkeypatch, fake_mcp):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")

    agent = ProductionAgent(fake_mcp, llm=object())

    assert agent.model == "gpt-4o"


def test_openrouter_client_uses_its_own_settings(monkeypatch, fake_mcp):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-fake")
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-must-not-be-used")

    agent = ProductionAgent(fake_mcp)

    assert agent.model == "anthropic/claude-sonnet-4.5"
    assert agent.llm.api_key == "sk-or-fake"
    assert str(agent.llm.base_url) == "https://openrouter.ai/api/v1/"
    assert agent.llm.max_retries == 8


def test_provider_is_case_and_whitespace_insensitive(monkeypatch, fake_mcp):
    monkeypatch.setenv("LLM_PROVIDER", "  OpenRouter  ")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4.1")

    agent = ProductionAgent(fake_mcp, llm=object())

    assert agent.provider == "openrouter"


def test_stray_openrouter_key_does_not_reroute(monkeypatch, fake_mcp):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-fake-openai")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-stray")

    agent = ProductionAgent(fake_mcp)

    assert agent.provider == "openai"
    assert str(agent.llm.base_url) == "https://api.openai.com/v1/"


def test_openrouter_missing_key_raises_when_building_client(monkeypatch, fake_mcp):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/gpt-4.1")

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        ProductionAgent(fake_mcp)


def test_openrouter_model_is_required_without_explicit_model(monkeypatch, fake_mcp):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")

    with pytest.raises(RuntimeError, match="OPENROUTER_MODEL"):
        ProductionAgent(fake_mcp, llm=object())

    agent = ProductionAgent(fake_mcp, model="openai/gpt-4.1", llm=object())
    assert agent.model == "openai/gpt-4.1"


def test_unknown_provider_is_rejected_even_with_injected_llm(monkeypatch, fake_mcp):
    monkeypatch.setenv("LLM_PROVIDER", "mystery")

    with pytest.raises(RuntimeError, match="mystery.*openai.*openrouter"):
        ProductionAgent(fake_mcp, llm=object())


@pytest.mark.parametrize(
    ("provider", "model"),
    [("openai", "gpt-4.1"), ("openrouter", "openai/gpt-4.1")],
)
def test_injected_llm_needs_no_credentials(monkeypatch, fake_mcp, provider, model):
    monkeypatch.setenv("LLM_PROVIDER", provider)

    injected = object()
    agent = ProductionAgent(fake_mcp, model=model, llm=injected)

    assert agent.llm is injected


@pytest.mark.parametrize(
    ("model", "expected_temperature"),
    [
        ("gpt-4.1", 0),
        ("gpt-3.5-turbo", 0),
        ("openai/gpt-4.1", 0),
        ("~openai/gpt-4.1-latest", 0),
        ("anthropic/claude-sonnet-4.5", None),
        ("gpt-5", None),
        ("o3", None),
    ],
)
def test_temperature_allow_list(fake_mcp, model, expected_temperature):
    llm = CapturingLLM()
    agent = ProductionAgent(fake_mcp, model=model, llm=llm)

    agent.run("test request")

    if expected_temperature is None:
        assert "temperature" not in llm.kwargs
    else:
        assert llm.kwargs["temperature"] == expected_temperature


@pytest.mark.parametrize(
    ("provider", "model"),
    [("openai", "gpt-4.1"), ("openrouter", "openai/gpt-4.1")],
)
def test_start_trace_carries_provider(monkeypatch, fake_mcp, provider, model):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    events = []
    agent = ProductionAgent(fake_mcp, model=model, llm=CapturingLLM(), trace=events.append)

    agent.run("test request")

    assert events[0]["type"] == "start"
    assert events[0]["provider"] == provider
