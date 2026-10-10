"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-08).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

AgentSwitch's harness runner (Release 8.1) gives a run AGENTSWITCH_BASE_URL, AGENTSWITCH_TOKEN and
AGENTSWITCH_INSTANCE plus OPENAI_* for its model, and nothing else: no password, no .env, no keys of
our own. These pin how the harness uses what it is given.

Run: python -m pytest tests_ai/test_platform_mode.py -q
"""
import os
from types import SimpleNamespace

import pytest

from prod_agent import config, mcp_client
from prod_agent.agent import ProductionAgent, default_llm

BASE = "https://copy.example.invalid"


@pytest.fixture
def platform_env(monkeypatch):
    monkeypatch.setenv("AGENTSWITCH_TOKEN", "seat-token")
    monkeypatch.setenv("AGENTSWITCH_BASE_URL", BASE + "/")
    monkeypatch.setenv("AGENTSWITCH_INSTANCE", "suryodaya")


@pytest.fixture
def no_password(monkeypatch):
    monkeypatch.setattr(config, "credentials", lambda instance: pytest.fail("a platform run looked up a password"))


def test_no_runner_environment_means_a_local_run():
    assert config.platform() is None
    assert not config.on_platform()


def test_the_runner_environment_is_used_as_given(platform_env):
    assert config.platform() == {"base": BASE, "token": "seat-token", "instance": "suryodaya"}


@pytest.mark.parametrize("missing", ["AGENTSWITCH_BASE_URL", "AGENTSWITCH_INSTANCE"])
def test_a_half_set_runner_environment_is_refused_by_name(platform_env, monkeypatch, missing):
    monkeypatch.delenv(missing)
    with pytest.raises(RuntimeError, match=missing):
        config.platform()


def test_an_instance_we_do_not_have_is_refused(platform_env, monkeypatch):
    monkeypatch.setenv("AGENTSWITCH_INSTANCE", "atlantis")
    with pytest.raises(RuntimeError, match="atlantis"):
        config.platform()


def test_dotenv_is_never_read_under_the_runner(platform_env, monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_MODEL=ours-from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_MODEL", "the-runners-model")

    config.load_dotenv(env_file)

    assert os.environ["OPENAI_MODEL"] == "the-runners-model"


def test_dotenv_still_wins_in_a_local_run(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_MODEL=ours-from-dotenv\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_MODEL", "exported-in-the-shell")

    config.load_dotenv(env_file)

    assert os.environ["OPENAI_MODEL"] == "ours-from-dotenv"


def test_session_uses_the_runner_token_without_logging_in(platform_env, no_password, monkeypatch, tmp_path):
    monkeypatch.setattr(mcp_client, "TOKEN_DIR", tmp_path)

    session = mcp_client.Session("suryodaya")

    assert (session.base, session.token) == (BASE, "seat-token")
    assert list(tmp_path.iterdir()) == [], "a platform run must not cache the runner's token"


def test_session_refuses_the_instance_this_run_does_not_serve(platform_env, no_password):
    with pytest.raises(ValueError, match="suryodaya only"):
        mcp_client.Session("keystone")


def test_a_rejected_runner_token_is_reported_not_retried_with_a_password(platform_env, no_password):
    session = mcp_client.Session("suryodaya")
    calls = []

    def expired():
        calls.append(1)
        raise mcp_client.AuthExpired("401")

    with pytest.raises(RuntimeError, match="rejected the harness runner's token"):
        session.with_reauth(expired)
    assert calls == [1]


def test_the_runner_forces_its_openai_compatible_model(platform_env, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENAI_MODEL", "platform-model")

    agent = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="suryodaya")), llm=object())

    assert agent.provider == "openai"
    assert agent.model == "platform-model"


def test_the_model_client_takes_the_runners_endpoint_and_key(platform_env, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "platform-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://model.example.invalid/v1")

    llm = default_llm("openai")

    assert str(llm.base_url).startswith("https://model.example.invalid/v1")
    assert llm.api_key == "platform-key"


def test_a_dotenv_line_cannot_switch_a_local_run_onto_a_runner_token(monkeypatch, tmp_path):
    """AGENTSWITCH_* and AGENT_OFFLINE are shell-only: copied from .env, the token would make every later
    on_platform() true."""
    env_file = tmp_path / ".env"
    env_file.write_text("AGENTSWITCH_TOKEN=stray\nAGENTSWITCH_BASE_URL=https://x.invalid\n"
                        "AGENTSWITCH_INSTANCE=suryodaya\nAGENT_OFFLINE=1\nOPENAI_MODEL=ours\n", encoding="utf-8")
    for name in ("AGENTSWITCH_TOKEN", "AGENTSWITCH_BASE_URL", "AGENTSWITCH_INSTANCE", "AGENT_OFFLINE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "exported")

    config.load_dotenv(env_file)

    assert not config.on_platform() and config.platform() is None
    assert "AGENT_OFFLINE" not in os.environ
    assert os.environ["OPENAI_MODEL"] == "ours", "ordinary keys still come from .env"
