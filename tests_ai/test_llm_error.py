"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-09-21).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero. They cover offline containment of LLM response failures.

Run: python -m pytest tests_ai/test_llm_error.py -q
"""
import json
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


class FakeToolCall:
    def __init__(self, name, arguments):
        self.id = "call-1"
        self.function = SimpleNamespace(name=name, arguments=json.dumps(arguments))

    def model_dump(self, **kwargs):
        return {
            "id": self.id,
            "type": "function",
            "function": {"name": self.function.name, "arguments": self.function.arguments},
        }


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self, **kwargs):
        return {
            "role": "assistant",
            "content": self.content,
            "tool_calls": [call.model_dump() for call in self.tool_calls],
        }


class ScriptedLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls += 1
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return SimpleNamespace(choices=[SimpleNamespace(message=response)])


class EmptyChoicesLLM:
    def __init__(self):
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        return SimpleNamespace(choices=[])


@pytest.fixture
def recording_mcp():
    calls = []

    def call(name, args):
        calls.append((name, args))
        return {"id": "mem-1"}

    return SimpleNamespace(session=SimpleNamespace(instance="suryodaya"), call=call), calls


def finding_args():
    return {
        "outcome": "answered",
        "work_order": "WO-2026-00001",
        "is_late": True,
        "currency": "INR",
        "blocking_causes": ["material_shortage"],
        "evidence_records": ["WO-2026-00001"],
        "potentially_blocked_work_orders": [],
        "blocked_sales_orders": [],
        "rescheduled": [],
        "not_visible": [],
        "refusal_reason": None,
    }


def test_llm_failure_after_recorded_finding_is_contained(recording_mcp):
    mcp, mcp_calls = recording_mcp
    finding = finding_args()
    llm = ScriptedLLM([
        FakeMessage(tool_calls=[FakeToolCall("record_finding", finding)]),
        RuntimeError("provider disconnected"),
    ])
    events = []
    agent = ProductionAgent(mcp, llm=llm, model="gpt-4.1", trace=events.append, max_steps=3)

    result = agent.run("diagnose this order")

    assert result["stop_reason"] == "llm_error"
    assert result["finding"] == finding
    assert result["finding_record"]["agent_memory_id"] == "mem-1"
    assert llm.calls == 2
    assert [name for name, _ in mcp_calls] == ["AgentMemory.create"]
    assert events[-1]["type"] == "end"
    assert "RuntimeError: provider disconnected" in events[-1]["error"]


def test_llm_failure_before_finding_does_not_fabricate_one(recording_mcp):
    mcp, mcp_calls = recording_mcp
    llm = ScriptedLLM([RuntimeError("provider disconnected")])
    events = []
    agent = ProductionAgent(mcp, llm=llm, model="gpt-4.1", trace=events.append)

    result = agent.run("diagnose this order")

    assert result["stop_reason"] == "llm_error"
    assert result["finding"] is None
    assert result["finding_record"] is None
    assert llm.calls == 1
    assert mcp_calls == []


def test_keyboard_interrupt_still_propagates(recording_mcp):
    mcp, _ = recording_mcp
    llm = ScriptedLLM([KeyboardInterrupt()])
    agent = ProductionAgent(mcp, llm=llm, model="gpt-4.1")

    with pytest.raises(KeyboardInterrupt):
        agent.run("diagnose this order")


def test_successful_final_answer_end_event_is_unchanged(recording_mcp):
    mcp, _ = recording_mcp
    llm = ScriptedLLM([FakeMessage(content="done")])
    events = []
    agent = ProductionAgent(mcp, llm=llm, model="gpt-4.1", trace=events.append)

    result = agent.run("diagnose this order")

    assert result["stop_reason"] == "final_answer"
    assert [event["type"] for event in events] == ["start", "llm", "end"]
    assert events[-1] == {"type": "end", **result}


def test_empty_choices_response_is_contained_as_llm_error(recording_mcp):
    mcp, _ = recording_mcp
    events = []
    agent = ProductionAgent(mcp, llm=EmptyChoicesLLM(), model="gpt-4.1", trace=events.append)

    result = agent.run("diagnose this order")

    assert result["stop_reason"] == "llm_error"
    assert events[-1]["type"] == "end"
    assert "IndexError" in events[-1]["error"]


def test_malformed_tool_call_is_contained_without_partial_llm_event(recording_mcp):
    mcp, _ = recording_mcp
    malformed_call = SimpleNamespace(id="call-1")
    llm = ScriptedLLM([FakeMessage(tool_calls=[malformed_call])])
    events = []
    agent = ProductionAgent(mcp, llm=llm, model="gpt-4.1", trace=events.append)

    result = agent.run("diagnose this order")

    assert result["stop_reason"] == "llm_error"
    assert "AttributeError" in events[-1]["error"]
    assert [event["type"] for event in events] == ["start", "end"]


def test_llm_trace_callback_failure_propagates(recording_mcp):
    mcp, _ = recording_mcp
    llm = ScriptedLLM([FakeMessage(content="done")])

    def failing_trace(event):
        if event["type"] == "llm":
            raise OSError("trace disk failure")

    agent = ProductionAgent(mcp, llm=llm, model="gpt-4.1", trace=failing_trace)

    with pytest.raises(OSError, match="trace disk failure"):
        agent.run("diagnose this order")
