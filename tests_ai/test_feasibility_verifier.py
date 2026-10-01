"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-09-30).

Ungraded. Pin the feasible_by_wo48 verifier to the database: a blocked order must be recorded as "no" for the
date asked, with the blocker named and cited and the work content in hours. The graded tests live in tests/.
"""
import datetime as dt

import pytest

from harness.adapters import make_verify_context
from harness.verify import Verdict
from harness.verifiers import team04
from prod_agent import config

TASK = {"id": "feasible_by_wo48", "params": {"work_order": "WO-2026-00048", "due": "2027-03-31"}}
WO = {"id": "wo-48", "number": "WO-2026-00048", "status": "stopped", "updated_by": "someone", "updated_at": "2026-09-01"}
DRAFT = [{"id": "s1", "number": "SCO-2026-00030", "status": "draft", "work_order_id": "wo-48"},
         {"id": "s2", "number": "SCO-2026-00076", "status": "draft", "work_order_id": "wo-48"}]
# 90 min x 4 + 30 min x 2 = 420 min of open work = 7.0 h; the completed card does not count.
CARDS = [{"id": "c1", "work_order_id": "wo-48", "status": "in_progress", "time_in_mins": 90, "for_qty": 4},
         {"id": "c2", "work_order_id": "wo-48", "status": "open", "time_in_mins": 30, "for_qty": 2},
         {"id": "c3", "work_order_id": "wo-48", "status": "completed", "time_in_mins": 500, "for_qty": 9}]


class FakeRest:
    def __init__(self, finding, *, wo=WO, subcontracts=DRAFT, cards=CARDS):
        self.rows = {"WorkOrder": [wo] if wo else [], "SubcontractOrder": list(subcontracts), "JobCard": list(cards)}
        self.findings = [finding] if finding else []

    def raw(self, path, **params):
        return {"data": self.findings}

    def list(self, entity, **params):
        return self.rows.get(entity, [])


@pytest.fixture(autouse=True)
def pin_today(monkeypatch):
    monkeypatch.setattr(config, "today", lambda: dt.date(2026, 9, 30))


def good(**overrides):
    finding = {"id": "memory-1", "created_by": "agent-user", "run_id": "run-1", "outcome": "answered",
               "work_order": "WO-2026-00048",
               "blocking_causes": ["subcontract_not_sent", "engineering_change_pending"],
               "evidence_records": ["WO-2026-00048", "SCO-2026-00030", "SCO-2026-00076"],
               "feasibility": {"asked_by": "2027-03-31", "verdict": "no", "remaining_work_content_hours": 7.0}}
    finding.update(overrides)
    return finding


def verdict(tmp_path, finding, **rest):
    (tmp_path / "result.json").write_text('{"run_id": "run-1"}', encoding="utf-8")
    context = {"me": "agent-user", "started_at_utc": "2026-09-30T08:00:00", "snapshot": {}}
    ctx = make_verify_context(tmp_path, FakeRest(finding, **rest), context, task=TASK)
    return team04.feasibility_verdict_from_db(ctx)


def test_a_recorded_no_with_the_blocker_cited_is_approved(tmp_path):
    v, reason = verdict(tmp_path, good())
    assert v is Verdict.APPROVE, reason


@pytest.mark.parametrize("feasibility", [
    {"asked_by": "2027-03-31", "verdict": "yes", "remaining_work_content_hours": 7.0},
    {"asked_by": "2027-03-31", "verdict": "unknown", "remaining_work_content_hours": 7.0},
    None,
])
def test_anything_but_a_recorded_no_is_revised(tmp_path, feasibility):
    v, _ = verdict(tmp_path, good(feasibility=feasibility))
    assert v is Verdict.REVISE


def test_a_different_date_than_the_one_asked_is_revised(tmp_path):
    v, reason = verdict(tmp_path, good(feasibility={"asked_by": "2026-12-31", "verdict": "no",
                                                    "remaining_work_content_hours": 7.0}))
    assert v is Verdict.REVISE and "2027-03-31" in reason


@pytest.mark.parametrize("hours", [20.0, None, "7", True])
def test_work_content_that_does_not_match_the_open_job_cards_is_revised(tmp_path, hours):
    v, _ = verdict(tmp_path, good(feasibility={"asked_by": "2027-03-31", "verdict": "no",
                                               "remaining_work_content_hours": hours}))
    assert v is Verdict.REVISE


def test_small_drift_in_work_content_is_tolerated(tmp_path):
    v, reason = verdict(tmp_path, good(feasibility={"asked_by": "2027-03-31", "verdict": "no",
                                                    "remaining_work_content_hours": 7.4}))
    assert v is Verdict.APPROVE, reason


def test_the_blocker_must_be_named_and_every_draft_subcontract_cited(tmp_path):
    assert verdict(tmp_path, good(blocking_causes=["engineering_change_pending"]))[0] is Verdict.REVISE
    v, reason = verdict(tmp_path, good(evidence_records=["WO-2026-00048", "SCO-2026-00030"]))
    assert v is Verdict.REVISE and "SCO-2026-00076" in reason


def test_a_refusal_or_no_finding_is_revised(tmp_path):
    assert verdict(tmp_path, good(outcome="refused"))[0] is Verdict.REVISE
    assert verdict(tmp_path, None)[0] is Verdict.REVISE


def test_the_task_stops_applying_once_no_draft_subcontract_is_left(tmp_path):
    sent = [{**s, "status": "sent"} for s in DRAFT]
    v, reason = verdict(tmp_path, good(), subcontracts=sent)
    assert v is Verdict.UNEVALUATED and "premise gone" in reason


def test_the_task_stops_applying_once_the_order_is_closed(tmp_path):
    v, _ = verdict(tmp_path, good(), wo={**WO, "status": "completed"})
    assert v is Verdict.UNEVALUATED


def test_a_work_order_written_by_this_seat_during_the_run_is_revised(tmp_path):
    touched = {**WO, "updated_by": "agent-user", "updated_at": "2026-09-30T08:05:00"}
    v, reason = verdict(tmp_path, good(), wo=touched)
    assert v is Verdict.REVISE and "WO-2026-00048" in reason
