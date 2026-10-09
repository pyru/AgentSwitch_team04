"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-08).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

The loop forces record_finding (and escalate) by name so a finding always reaches the database.
AgentSwitch's harness runner promises a model with tool calls, not one that accepts a forced call.
These pin the fallback: named, then "required" with only that tool on offer, then "auto", kept for the
rest of the run once found, and never triggered by an error that is not about tool_choice.

Run: python -m pytest tests_ai/test_tool_choice_fallback.py -q
"""
from types import SimpleNamespace

import httpx
import openai
import pytest

from prod_agent.agent import ProductionAgent, probe_tool_choice
from tests_ai.test_llm_error import FakeMessage, FakeToolCall, isolated_environment, recording_mcp  # noqa: F401

FORCE_FINDING = {"type": "function", "function": {"name": "record_finding"}}


def _400(message="Invalid value for 'tool_choice': only 'auto' and 'none' are supported"):
    return openai.BadRequestError(message, response=httpx.Response(400, request=httpx.Request("POST", "https://api")),
                                  body={"message": message})


class ChoiceLLM:
    """Rejects the tool_choice forms listed, as a provider without forced calls would; answers everything else."""

    def __init__(self, rejects=(), error=None, call_tool=False):
        self.rejects, self.error, self.call_tool = set(rejects), error, call_tool
        self.requests = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        choice = kwargs.get("tool_choice")
        if ("named" if isinstance(choice, dict) else choice) in self.rejects:
            raise _400()
        message = FakeMessage(tool_calls=[FakeToolCall("ping", {})]) if self.call_tool else FakeMessage(content="done")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _agent(mcp, llm, events, **kwargs):
    return ProductionAgent(mcp, llm=llm, model="platform-model", trace=events.append, **kwargs)


def _force(agent, choice=FORCE_FINDING):
    return agent._complete(0, model="platform-model", messages=[], tools=agent.tool_specs(), tool_choice=choice)


def test_a_rejected_named_call_falls_back_to_required_with_only_that_tool(recording_mcp):
    mcp, _ = recording_mcp
    llm, events = ChoiceLLM(rejects={"named"}), []
    agent = _agent(mcp, llm, events)

    _force(agent)

    assert [r["tool_choice"] for r in llm.requests] == [FORCE_FINDING, "required"]
    assert [t["function"]["name"] for t in llm.requests[1]["tools"]] == ["record_finding"]
    assert agent.forced_tool_choice == "required"
    assert [(e["from"], e["to"]) for e in events if e["type"] == "tool_choice_fallback"] == [("named", "required")]


def test_the_form_that_worked_is_kept_for_the_rest_of_the_run(recording_mcp):
    mcp, _ = recording_mcp
    llm = ChoiceLLM(rejects={"named"})
    agent = _agent(mcp, llm, [])

    _force(agent)
    _force(agent)

    assert [r["tool_choice"] for r in llm.requests] == [FORCE_FINDING, "required", "required"]


def test_a_model_that_refuses_both_forced_forms_ends_at_auto(recording_mcp):
    mcp, _ = recording_mcp
    llm = ChoiceLLM(rejects={"named", "required"})
    agent = _agent(mcp, llm, [])

    _force(agent)

    assert llm.requests[-1]["tool_choice"] == "auto"
    assert [t["function"]["name"] for t in llm.requests[-1]["tools"]] == ["record_finding"]
    assert agent.forced_tool_choice == "auto"


def test_none_is_sent_as_none_unless_the_model_takes_only_auto(recording_mcp):
    mcp, _ = recording_mcp
    llm = ChoiceLLM()
    required = _agent(mcp, llm, [], forced_tool_choice="required")
    auto = _agent(mcp, llm, [], forced_tool_choice="auto")

    _force(required, "none")
    _force(auto, "none")

    assert [r["tool_choice"] for r in llm.requests] == ["none", "auto"]


def test_an_unrelated_400_is_not_mistaken_for_a_tool_choice_problem(recording_mcp):
    mcp, _ = recording_mcp
    llm = ChoiceLLM(error=_400("This model's maximum context length is 128000 tokens"))
    agent = _agent(mcp, llm, [])

    with pytest.raises(openai.BadRequestError):
        _force(agent)
    assert len(llm.requests) == 1 and agent.forced_tool_choice == "named"


def test_a_request_without_tool_choice_is_never_reshaped(recording_mcp):
    mcp, _ = recording_mcp
    llm = ChoiceLLM()
    agent = _agent(mcp, llm, [], forced_tool_choice="auto")
    tools = agent.tool_specs()

    agent._complete(0, model="platform-model", messages=[], tools=tools)

    assert "tool_choice" not in llm.requests[0] and llm.requests[0]["tools"] == tools


def test_an_unknown_mode_is_refused(recording_mcp):
    mcp, _ = recording_mcp
    with pytest.raises(ValueError, match="forced_tool_choice"):
        _agent(mcp, ChoiceLLM(), [], forced_tool_choice="sometimes")


# ----------------------------------------------------------------------------- the probe

def test_the_probe_returns_the_strongest_form_the_model_accepts():
    out = probe_tool_choice(ChoiceLLM(rejects={"named"}, call_tool=True), "platform-model")

    assert out["mode"] == "required" and out["tool_called"] is True
    assert len(out["rejected"]) == 1 and out["rejected"][0].startswith("named:")


def test_the_probe_says_when_a_form_is_accepted_but_not_honoured():
    assert probe_tool_choice(ChoiceLLM(), "platform-model") == {"mode": "named", "tool_called": False, "rejected": []}


def test_the_probe_gives_up_when_every_form_is_rejected():
    with pytest.raises(RuntimeError, match="rejected every form"):
        probe_tool_choice(ChoiceLLM(rejects={"named", "required", "auto"}), "platform-model")


def test_the_probe_does_not_swallow_other_errors():
    with pytest.raises(RuntimeError, match="provider down"):
        probe_tool_choice(ChoiceLLM(error=RuntimeError("provider down")), "platform-model")
