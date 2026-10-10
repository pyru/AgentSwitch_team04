"""record_finding refuses causes that are not bare signal codes.

WRITTEN WITH CLAUDE (AI-assisted). Ungraded; the team's hand-written tests live in tests/.

The verifiers match cause codes exactly (harness/verifiers/team04.py _causes_problem). On the 2026-09-30 full run
z-ai/glm-5.3-flash recorded "subcontract_not_sent (SCO-2026-00024 draft, ...)" for WO-2026-00049, so a cause it
had found still scored as missing. The finding is persisted as-is, so the check has to happen before persisting.

Run: python -m pytest tests_ai/test_cause_codes.py -q
"""
import re
from types import SimpleNamespace

import pytest

from prod_agent import config, domain
from prod_agent.agent import RECORD_FINDING_SCHEMA, ProductionAgent


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    persisted = []
    monkeypatch.setattr(domain, "record_finding",
                        lambda mcp, run_id, finding: persisted.append(finding) or {"run_id": run_id})
    a = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="suryodaya")), llm=object(), model="m")
    a.persisted = persisted
    return a


def finding(**over):
    base = {"outcome": "answered", "work_order": "WO-2026-00049", "is_late": True, "currency": "INR",
            "blocking_causes": ["subcontract_not_sent"],
            "contributing_causes": ["stopped_without_recorded_reason", "material_request_open"],
            "evidence_records": ["WO-2026-00049", "SCO-2026-00024", "MR-2026-00065"],
            "potentially_blocked_work_orders": [], "blocked_sales_orders": ["SO-2026-00100"], "rescheduled": [],
            "not_visible": [], "refusal_reason": None}
    return {**base, **over}


def test_the_live_2026_09_30_finding_is_refused_and_not_persisted(agent):
    live = finding(blocking_causes=[
        "subcontract_not_sent (SCO-2026-00024 draft, vendor Shreeji Powder Coating, expected delivery 2026-01-17)",
        "engineering_change_pending (ECO-2026-00073, submitted, critical: EN8 round bar shortage on the scriber line)",
    ], contributing_causes=[])
    out = agent._dispatch("record_finding", live)
    assert out["error"] == "causes must be bare signal codes"
    assert len(out["entries"]) == 2
    assert agent.persisted == [] and agent.finding is None


def test_a_bad_contributing_cause_is_refused_too(agent):
    out = agent._dispatch("record_finding", finding(contributing_causes=["Material request open"]))
    assert out["entries"] == ["Material request open"]
    assert agent.persisted == []


def test_bare_codes_are_persisted_including_platform_schedule_codes(agent):
    ok = finding(contributing_causes=["material_request_open", "schedule_subcontract_pending"])
    agent._dispatch("record_finding", ok)
    assert agent.persisted == [ok]


def test_after_a_refusal_the_corrected_call_is_accepted(agent):
    agent._dispatch("record_finding", finding(blocking_causes=["subcontract_not_sent (SCO-2026-00024)"]))
    agent._dispatch("record_finding", finding())
    assert agent.persisted == [finding()]


def test_the_model_is_told_both_cause_lists_are_codes_and_required():
    props = RECORD_FINDING_SCHEMA["properties"]
    for field in ("blocking_causes", "contributing_causes"):
        assert field in RECORD_FINDING_SCHEMA["required"]
        pattern = re.compile(props[field]["items"]["pattern"])
        assert pattern.fullmatch("subcontract_not_sent")
        assert not pattern.fullmatch("subcontract_not_sent (SCO-2026-00024 draft)")
