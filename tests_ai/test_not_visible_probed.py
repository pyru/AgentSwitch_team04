"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-19).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Platform-set rehearsal, 2026-10-19 (deepseek-v4.1-flash, declared_policy_not_permission on Suryodaya, 1 of 4
runs): revise with "finding lists ['AgentFloorConfig', 'AgentPersona', 'AgentToolPolicy'] as not visible, but this
seat reads them". The model checked eight entities with seat_capability but not those three, and copied them from
the declared policy's denied_entities. record_finding now asks the platform about every entity a not_visible entry
names, and takes the entry out only when all of them answer 200; a 403 is a real limit and stays.

Run: python -m pytest tests_ai/test_not_visible_probed.py -q
"""
from types import SimpleNamespace

import pytest

from prod_agent import domain
from prod_agent.agent import ProductionAgent

# What REST answered on both live tenants, 2026-10-19.
STATUS = {"AgentPersona": 200, "AgentToolPolicy": 200, "AgentFloorConfig": 200, "SalesOrder": 200,
          "Coupon": 403, "ApprovalRequest": 403, "Employee": 403, "SalarySlip": 403, "PurchaseOrder": 403}


@pytest.fixture
def agent(monkeypatch):
    asked = []

    def rest_status(mcp, entity):
        asked.append(entity)
        return STATUS.get(entity, 404)

    monkeypatch.setattr(domain, "_rest_status", rest_status)
    events = []
    a = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="suryodaya")), llm=object(), model="m",
                        trace=events.append)
    a.mcp.call = lambda name, args: {"id": "mem-1"}
    a.events, a.asked = events, asked
    return a


def _finding(**over):
    return {"outcome": "answered", "work_order": None, "is_late": None, "currency": "INR",
            "blocking_causes": [], "contributing_causes": [], "evidence_records": [],
            "potentially_blocked_work_orders": [], "blocked_sales_orders": [], "rescheduled": [],
            "not_visible": [], "refusal_reason": None, **over}


def test_the_live_failure_keeps_only_the_real_limits(agent):
    claimed = ["SalarySlip", "Employee", "Coupon", "ApprovalRequest", "AgentPersona", "AgentToolPolicy",
               "AgentFloorConfig"]
    agent._dispatch("record_finding", _finding(not_visible=claimed))

    assert agent.finding["not_visible"] == ["SalarySlip", "Employee", "Coupon", "ApprovalRequest"]
    corrected = [e for e in agent.events if e["type"] == "finding_corrected"]
    assert corrected and corrected[-1]["dropped"] == ["AgentPersona", "AgentToolPolicy", "AgentFloorConfig"]


def test_an_entry_in_words_goes_only_when_every_entity_in_it_is_readable(agent):
    out = agent._drop_readable_entities(_finding(not_visible=[
        "AgentPersona (denied by the declared policy)",
        "Employee contact details",
        "AgentToolPolicy and Coupon",
    ]))
    assert out["not_visible"] == ["Employee contact details", "AgentToolPolicy and Coupon"]


def test_lanes_and_unknown_names_are_left_alone(agent):
    finding = _finding(not_visible=["shortages: permission_denied", "automation failures", "Not reachable"])
    assert agent._drop_readable_entities(finding) is finding


def test_each_entity_is_asked_once_per_run(agent):
    agent._drop_readable_entities(_finding(not_visible=["AgentPersona", "Employee"]))
    agent._drop_readable_entities(_finding(not_visible=["AgentPersona", "Employee"]))
    assert agent.asked == ["AgentPersona", "Employee"]


def test_no_answer_from_the_platform_keeps_the_entry(agent, monkeypatch):
    monkeypatch.setattr(domain, "_rest_status", lambda mcp, entity: None)
    finding = _finding(not_visible=["AgentPersona"])
    assert agent._drop_readable_entities(finding) is finding


def test_nothing_claimed_or_the_wrong_shape_is_left_for_the_other_guards(agent):
    for finding in (_finding(), _finding(not_visible="AgentPersona"), _finding(not_visible=None)):
        assert agent._drop_readable_entities(finding) is finding
    assert agent.asked == []
