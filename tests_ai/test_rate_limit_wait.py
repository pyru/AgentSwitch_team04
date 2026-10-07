"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-07).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Seen 2026-10-01: two harness runs shared one OpenAI key (gpt-4.1, 30k tokens per minute). The SDK's
eight retries gave up after about forty seconds, the window stayed full, and two tasks ended with
stop_reason llm_error and no finding. The loop now waits out the window a bounded number of times.

Run: python -m pytest tests_ai/test_rate_limit_wait.py -q
"""
import httpx
import openai
import pytest

from prod_agent import agent as agent_module
from prod_agent.agent import ProductionAgent
from tests_ai.test_llm_error import FakeMessage, ScriptedLLM, isolated_environment, recording_mcp  # noqa: F401


def _429(code="rate_limit_exceeded", type_="tokens"):
    return openai.RateLimitError("Rate limit reached for gpt-4.1 on tokens per min (TPM)",
                                 response=httpx.Response(429, request=httpx.Request("POST", "https://api")),
                                 body={"message": "rate limited", "type": type_, "code": code})


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(agent_module.time, "sleep", slept.append)
    return slept


def test_a_rate_limit_is_waited_out_and_the_run_completes(recording_mcp, no_real_sleep):
    mcp, _ = recording_mcp
    llm = ScriptedLLM([_429(), _429(), FakeMessage(content="done")])
    events = []
    result = ProductionAgent(mcp, llm=llm, model="gpt-4.1", trace=events.append).run("why is WO-1 late?")

    assert result["stop_reason"] == "final_answer"
    assert llm.calls == 3
    assert no_real_sleep == [ProductionAgent.RATE_LIMIT_WAIT_SECONDS] * 2
    waits = [e for e in events if e["type"] == "llm_wait"]
    assert [w["attempt"] for w in waits] == [1, 2]


def test_a_key_that_stays_saturated_still_ends_the_run(recording_mcp, no_real_sleep):
    """Bounded: a run must not hang on a key that never recovers."""
    mcp, _ = recording_mcp
    llm = ScriptedLLM([_429()] * (ProductionAgent.RATE_LIMIT_WAITS + 1))
    events = []
    result = ProductionAgent(mcp, llm=llm, model="gpt-4.1", trace=events.append).run("why is WO-1 late?")

    assert result["stop_reason"] == "llm_error"
    assert llm.calls == ProductionAgent.RATE_LIMIT_WAITS + 1
    assert len(no_real_sleep) == ProductionAgent.RATE_LIMIT_WAITS
    assert "RateLimitError" in events[-1]["error"]


def test_an_exhausted_quota_is_not_waited_on(recording_mcp, no_real_sleep):
    """insufficient_quota is also a 429, but no wait clears it."""
    mcp, _ = recording_mcp
    llm = ScriptedLLM([_429(code="insufficient_quota")])
    result = ProductionAgent(mcp, llm=llm, model="gpt-4.1").run("why is WO-1 late?")

    assert result["stop_reason"] == "llm_error"
    assert llm.calls == 1
    assert no_real_sleep == []


def test_no_credit_left_is_not_waited_on_whichever_field_says_so(recording_mcp, no_real_sleep):
    """The live error on 2026-10-07: type insufficient_quota, code credit_balance_exhausted. Checking
    code alone waited three minutes per task on an account that could not recover."""
    mcp, _ = recording_mcp
    llm = ScriptedLLM([_429(code="credit_balance_exhausted", type_="insufficient_quota")])
    result = ProductionAgent(mcp, llm=llm, model="gpt-4.1").run("why is WO-1 late?")

    assert result["stop_reason"] == "llm_error"
    assert llm.calls == 1
    assert no_real_sleep == []


def test_other_llm_errors_are_not_retried(recording_mcp, no_real_sleep):
    mcp, _ = recording_mcp
    llm = ScriptedLLM([RuntimeError("provider disconnected")])
    result = ProductionAgent(mcp, llm=llm, model="gpt-4.1").run("why is WO-1 late?")

    assert result["stop_reason"] == "llm_error"
    assert llm.calls == 1
    assert no_real_sleep == []
