"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-21).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Platform-set rehearsal, 2026-10-21 (deepseek-v4.1-flash, Release 13, capacity_load_disputed on Suryodaya): revise
with "finding records no capacity block, so neither load figure was persisted". capacity_outlook had returned both
figures and the model gave them in its reply, but left the capacity field out of record_finding. record_finding now
files the field from the tool's result whenever the run read the board.

Run: python -m pytest tests_ai/test_capacity_from_tool.py -q
"""
from types import SimpleNamespace

import pytest

from prod_agent import domain
from prod_agent.agent import ProductionAgent

# What capacity_outlook returned in the failed run, trimmed to the fields that matter.
OUTLOOK = {"available": True, "horizon_days": 21, "open_job_cards": 149,
           "board_reported": {"booked_minutes": 129772.0, "available_minutes": 110880.0, "load_pct": 117.04},
           "work_content": {"minutes": 129772.0, "load_pct": 117.0}, "board_understates_load": False,
           "confidence": "board_agrees"}
FILED = {"board_load_pct": 117.04, "work_content_load_pct": 117.0, "figures_disagree": False}


@pytest.fixture
def agent(monkeypatch):
    outlook = {"value": dict(OUTLOOK)}
    monkeypatch.setattr(domain, "capacity_outlook", lambda mcp, horizon_days=21: outlook["value"])
    events = []
    a = ProductionAgent(SimpleNamespace(session=SimpleNamespace(instance="suryodaya")), llm=object(), model="m",
                        trace=events.append)
    a.mcp.call = lambda name, args: {"id": "mem-1"}
    a.events, a.outlook = events, outlook
    return a


def _finding(**over):
    return {"outcome": "answered", "work_order": None, "is_late": None, "currency": "INR",
            "blocking_causes": [], "contributing_causes": [],
            "evidence_records": ["WS-2026-00009", "WS-2026-00008", "WS-2026-00005"],
            "potentially_blocked_work_orders": [], "blocked_sales_orders": [], "rescheduled": [],
            "not_visible": [], "refusal_reason": None, **over}


def test_the_live_failure_now_files_both_figures(agent):
    agent._dispatch("capacity_outlook", {"horizon_days": 21})
    agent._dispatch("record_finding", _finding())

    assert agent.finding["capacity"] == FILED
    assert [e for e in agent.events if e["type"] == "finding_corrected" and e.get("capacity_recorded") == FILED]


def test_figures_typed_differently_are_replaced_by_the_tools(agent):
    agent._dispatch("capacity_outlook", {})
    out = agent._capacity_from_tool(_finding(capacity={"board_load_pct": 1.24, "work_content_load_pct": 117.0,
                                                       "figures_disagree": True}))
    assert out["capacity"] == FILED


def test_a_finding_that_already_matches_is_left_as_it_was(agent):
    agent._dispatch("capacity_outlook", {})
    finding = _finding(capacity=dict(FILED))
    assert agent._capacity_from_tool(finding) is finding


def test_disagreeing_figures_are_filed_as_disagreeing(agent):
    agent.outlook["value"] = {**OUTLOOK, "board_reported": {"load_pct": 1.24}, "board_understates_load": True}
    agent._dispatch("capacity_outlook", {})
    out = agent._capacity_from_tool(_finding())
    assert out["capacity"] == {"board_load_pct": 1.24, "work_content_load_pct": 117.0, "figures_disagree": True}


def test_a_run_that_never_read_the_board_is_left_alone(agent):
    finding = _finding()
    assert agent._capacity_from_tool(finding) is finding


def test_an_unreadable_board_files_nothing(agent):
    agent.outlook["value"] = {"available": False, "error": "capacity board not readable"}
    agent._dispatch("capacity_outlook", {})
    finding = _finding()
    assert agent._capacity_from_tool(finding) is finding
