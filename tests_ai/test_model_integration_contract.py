"""The integration contract the README promises to anyone bringing their own model.

WRITTEN WITH CLAUDE (AI-assisted). Ungraded; the team's hand-written tests live in tests/.

README.md "Integrating your own model" tells outsiders that `llm=` needs none of our
credentials and that one method plus four attributes is enough to drive the loop. Nobody on the
team exercises that path, so it can rot silently and the first person to find out would be the
person we asked to integrate. These tests are the contract: the client below implements exactly
what the README documents and nothing more, so anything the loop starts depending on breaks here.

Run: python -m pytest tests_ai/test_model_integration_contract.py -q
"""
import json
from types import SimpleNamespace

import pytest

from prod_agent import config, domain
from prod_agent.agent import ProductionAgent

MODEL_CREDENTIALS = ("LLM_PROVIDER", "OPENAI_API_KEY", "OPENAI_BASE_URL", "OPENAI_MODEL",
                     "OPENROUTER_API_KEY", "OPENROUTER_MODEL")


@pytest.fixture(autouse=True)
def no_model_credentials(monkeypatch):
    """Strip every model credential: an outsider integrating their own client has none of ours."""
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    for name in MODEL_CREDENTIALS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_mcp():
    return SimpleNamespace(session=SimpleNamespace(instance="suryodaya"))


class ContractMessage:
    """Only the four attributes the README's table lists. Anything else raises AttributeError."""

    __slots__ = ("content", "tool_calls")

    def __init__(self, content=None, tool_calls=()):
        self.content = content
        self.tool_calls = list(tool_calls)

    def model_dump(self, **_kwargs):
        return {"role": "assistant", "content": self.content,
                "tool_calls": [{"id": c.id, "type": "function",
                                "function": {"name": c.function.name, "arguments": c.function.arguments}}
                               for c in self.tool_calls]}


def _tool_call(call_id, name, arguments):
    return SimpleNamespace(id=call_id, type="function",
                           function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


class ContractClient:
    """A client built strictly to README.md 'What your client has to implement'.

    No usage attribute on purpose: the README says usage is optional, so the loop must cope
    without it. Scripted replies, so the test drives the loop rather than a real model.
    """

    def __init__(self, replies):
        self._replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        message = self._replies.pop(0) if self._replies else ContractMessage(content="done")
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


FINDING = {"outcome": "answered", "work_order": "WO-1", "is_late": True, "currency": "INR",
           "blocking_causes": [], "evidence_records": ["WO-1"], "potentially_blocked_work_orders": [],
           "blocked_sales_orders": [], "rescheduled": [], "not_visible": [], "refusal_reason": None}


def test_a_client_built_only_from_the_readme_drives_a_full_run(monkeypatch, fake_mcp):
    """Tool call, tool result, finding, final answer — with no credentials and no usage attribute."""
    recorded = {}
    monkeypatch.setattr(domain, "company_context", lambda mcp: {"currency": "INR", "country": "India"})
    monkeypatch.setattr(domain, "record_finding",
                        lambda mcp, run_id, finding: recorded.setdefault("finding", finding) or {"run_id": run_id})

    client = ContractClient([
        ContractMessage(tool_calls=[_tool_call("c1", "company_context", {})]),
        ContractMessage(tool_calls=[_tool_call("c2", "record_finding", FINDING)]),
        ContractMessage(content="WO-1 is late because of a subcontract."),
    ])
    agent = ProductionAgent(fake_mcp, llm=client, model="some-vendor/some-model")
    out = agent.run("why is WO-1 late?")

    assert out["stop_reason"] == "final_answer"
    assert recorded["finding"]["work_order"] == "WO-1"
    assert len(client.calls) == 3


def test_the_loop_asks_for_nothing_the_readme_does_not_document(fake_mcp):
    """create() must be called with only model, messages, tools and the documented sampling keys."""
    client = ContractClient([ContractMessage(content="done")])
    ProductionAgent(fake_mcp, llm=client, model="some-vendor/some-model").run("hello")

    sent = client.calls[0]
    assert set(sent) <= {"model", "messages", "tools", "temperature", "tool_choice"}, sent
    assert sent["model"] == "some-vendor/some-model"
    assert sent["messages"][0]["role"] == "system"
    assert all("function" in spec for spec in sent["tools"])


def test_temperature_is_not_forced_on_a_model_that_may_reject_it(fake_mcp):
    """The README says temperature=0 is sent only for gpt-4*/gpt-3*; other models must not receive it."""
    client = ContractClient([ContractMessage(content="done")])
    ProductionAgent(fake_mcp, llm=client, model="accounts/fireworks/models/deepseek-v4p1-flash").run("hi")

    assert "temperature" not in client.calls[0]


def test_forced_tool_choice_is_used_near_the_step_budget(fake_mcp, monkeypatch):
    """The README warns the model must support a forced tool_choice; this is where the loop needs it.

    The client keeps calling a harmless read and never records anything, which is the case the wrap-up
    exists for: a model that would otherwise burn the budget and leave nothing in the database.
    """
    monkeypatch.setattr(domain, "company_context", lambda mcp: {"currency": "INR"})
    monkeypatch.setattr(domain, "record_finding", lambda mcp, run_id, finding: {"run_id": run_id})
    client = ContractClient([ContractMessage(tool_calls=[_tool_call(f"c{i}", "company_context", {})])
                             for i in range(5)])
    ProductionAgent(fake_mcp, llm=client, model="some-model", max_steps=3).run("why is WO-1 late?")

    forced = [c.get("tool_choice") for c in client.calls if c.get("tool_choice")]
    assert forced, "loop never forced a tool_choice, so a finding could never be guaranteed"
    assert forced[-1]["function"]["name"] == "record_finding"


@pytest.mark.parametrize("model", ["gpt-4.1", "accounts/fireworks/models/deepseek-v4p1-flash",
                                   "claude-sonnet-4-20250514", "gemini-3.1-flash-lite-preview"])
def test_any_model_id_the_platform_advertises_can_be_passed_through(fake_mcp, model):
    """AgentProvider.list advertises these; passing one must not trip provider validation."""
    client = ContractClient([ContractMessage(content="done")])
    agent = ProductionAgent(fake_mcp, llm=client, model=model)

    assert agent.model == model
    assert agent.run("hello")["stop_reason"] == "final_answer"


def test_the_readme_documents_the_injection_seam():
    """If the section is renamed or dropped, the contract above is no longer promised to anyone."""
    import pathlib

    readme = pathlib.Path(__file__).resolve().parents[1] / "README.md"
    text = readme.read_text(encoding="utf-8")

    assert "## Integrating your own model" in text
    assert "llm=your_client" in text
    assert "tool_choice" in text
