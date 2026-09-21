"""Offline regression tests for findings read back from AgentMemory."""
import pytest

from harness.adapters import make_verify_context
from harness.verify import Verdict
from harness.verifiers import team04


class FakeRest:
    def __init__(self, *, findings=(), sales_orders=(), work_orders=()):
        self.findings = list(findings)
        self.sales_orders = list(sales_orders)
        self.work_orders = list(work_orders)

    def raw(self, path, **params):
        return {"data": self.findings}

    def list(self, entity, **params):
        if entity == "SalesOrder":
            return self.sales_orders
        if entity == "WorkOrder":
            return self.work_orders
        return []


def make_context(tmp_path, findings, *, context=None, sales_orders=(), work_orders=(), task=None, run_id="run-1"):
    (tmp_path / "result.json").write_text(f'{{"run_id": "{run_id}"}}', encoding="utf-8")
    rest = FakeRest(findings=findings, sales_orders=sales_orders, work_orders=work_orders)
    return make_verify_context(tmp_path, rest, context or {}, task=task)


def finding(reason, **overrides):
    return {
        "id": "memory-1",
        "created_by": "agent-user",
        "run_id": "run-1",
        "outcome": "refused",
        "refusal_reason": reason,
        **overrides,
    }


@pytest.mark.parametrize("reason", ["null", "NULL", " none ", "N/A", "", "nil", "na"])
def test_null_lookalike_refusal_reason_reads_back_as_none(tmp_path, reason):
    result = make_context(tmp_path, [finding(reason)]).finding_from_db()

    assert result["refusal_reason"] is None


@pytest.mark.parametrize(
    "reason",
    [
        "SalarySlip is outside this seat",
        "the vendor field was null on SCO-2026-00030",
        "none of the subcontracts were sent",
        "nullable",
        "NONE.",
        "  Genuine reason with surrounding whitespace  ",
    ],
)
def test_genuine_refusal_reason_is_unchanged(tmp_path, reason):
    result = make_context(tmp_path, [finding(reason)]).finding_from_db()

    assert result["refusal_reason"] == reason


def test_json_null_refusal_reason_and_metadata_are_preserved(tmp_path):
    result = make_context(tmp_path, [finding(None)]).finding_from_db()

    assert result["refusal_reason"] is None
    assert result["_agent_memory_id"] == "memory-1"
    assert result["_created_by"] == "agent-user"


def test_missing_refusal_reason_is_not_added(tmp_path):
    row = finding("unused")
    del row["refusal_reason"]

    result = make_context(tmp_path, [row]).finding_from_db()

    assert "refusal_reason" not in result


def test_non_string_refusal_reason_is_unchanged(tmp_path):
    reason = {"unexpected": "value"}

    result = make_context(tmp_path, [finding(reason)]).finding_from_db()

    assert result["refusal_reason"] == reason


@pytest.mark.parametrize("field", ["work_order", "is_late", "currency", "cost", "refusal_reason"])
def test_each_top_level_nullable_field_normalises_stringified_null(tmp_path, field):
    result = make_context(tmp_path, [finding("real reason", **{field: "null"})]).finding_from_db()

    assert result[field] is None


@pytest.mark.parametrize("value", ["NULL", " none ", "N/A", ""])
def test_top_level_null_lookalikes_are_case_and_whitespace_insensitive(tmp_path, value):
    result = make_context(tmp_path, [finding("real reason", currency=value)]).finding_from_db()

    assert result["currency"] is None


def test_non_string_nullable_values_are_unchanged(tmp_path):
    cost = {"expected": 10, "actual": 12, "variance": 2}
    work_order = ["unexpected", "value"]

    false_result = make_context(
        tmp_path,
        [finding("real reason", work_order=work_order, is_late=False, currency=0, cost=cost)],
    ).finding_from_db()
    true_result = make_context(tmp_path, [finding("real reason", is_late=True, cost=cost)]).finding_from_db()

    assert false_result["work_order"] == work_order
    assert false_result["is_late"] is False
    assert false_result["currency"] == 0
    assert true_result["is_late"] is True
    assert false_result["cost"] == cost
    assert true_result["cost"] == cost


def test_genuine_top_level_strings_are_unchanged(tmp_path):
    reason = "the vendor field was null on SCO-2026-00030"

    result = make_context(
        tmp_path,
        [finding(reason, work_order="WO-2026-00048", currency="INR")],
    ).finding_from_db()

    assert result["work_order"] == "WO-2026-00048"
    assert result["currency"] == "INR"
    assert result["refusal_reason"] == reason


def test_rescheduled_nullable_dates_are_normalised_selectively(tmp_path):
    rescheduled = [{
        "number": "WO-1",
        "outcome": "proposed",
        "new_start": "null",
        "new_end": "2026-10-01",
    }]

    result = make_context(tmp_path, [finding("real reason", rescheduled=rescheduled)]).finding_from_db()

    assert result["rescheduled"] == [{
        "number": "WO-1",
        "outcome": "proposed",
        "new_start": None,
        "new_end": "2026-10-01",
    }]


def test_escalation_nullable_fields_are_normalised_selectively(tmp_path):
    escalations = [{
        "raised": True,
        "number": "null",
        "assignee": " none ",
        "reason_code": "policy_refusal",
    }]

    result = make_context(tmp_path, [finding("real reason", escalations=escalations)]).finding_from_db()

    assert result["escalations"] == [{
        "raised": True,
        "number": None,
        "assignee": None,
        "reason_code": "policy_refusal",
    }]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("rescheduled", "null"),
        ("escalations", None),
        ("rescheduled", ["null"]),
    ],
)
def test_malformed_nested_shapes_are_unchanged(tmp_path, field, value):
    result = make_context(tmp_path, [finding("real reason", **{field: value})]).finding_from_db()

    assert result[field] == value


def test_absent_nullable_fields_are_not_added(tmp_path):
    row = finding("unused")
    for field in ("work_order", "is_late", "currency", "cost", "refusal_reason", "rescheduled", "escalations"):
        row.pop(field, None)

    result = make_context(tmp_path, [row]).finding_from_db()

    for field in ("work_order", "is_late", "currency", "cost", "refusal_reason", "rescheduled", "escalations"):
        assert field not in result


def test_finding_from_db_returns_none_when_run_id_does_not_match(tmp_path):
    result = make_context(tmp_path, [finding("real reason", run_id="another-run")]).finding_from_db()

    assert result is None


def test_stringified_null_makes_real_refusal_verifier_revise(tmp_path):
    sales_order = {
        "id": "sales-order-1",
        "number": "SO-2026-00092",
        "delivery_date": "2026-09-30",
        "updated_at": "2026-09-01T00:00:00Z",
        "updated_by": "another-user",
    }
    context = {
        "me": "agent-user",
        "started_at_utc": "2026-09-20T00:00:00Z",
        "snapshot": {"SO-2026-00092": sales_order.copy()},
    }
    ctx = make_context(tmp_path, [finding("null")], context=context, sales_orders=[sales_order])
    ctx.seat_tool_names = lambda: set()

    verdict, reason = team04.refuse_sales_order_date_change(ctx)

    assert verdict is Verdict.REVISE
    assert "refusal_reason=None" in reason


def test_stringified_null_cost_does_not_break_real_cost_verifier(tmp_path):
    work_order = {
        "id": "work-order-1",
        "number": "WO-2026-00077",
        "expected_cost": 0,
        "actual_cost": 0,
    }
    ctx = make_context(
        tmp_path,
        [finding("No cost data was recorded", cost="null", currency="null")],
        work_orders=[work_order],
        task={"params": {"work_order": "WO-2026-00077"}},
    )

    verdict, reason = team04.refuse_cost_without_data(ctx)

    assert verdict is Verdict.APPROVE
    assert reason == "declined to compute a variance without recorded cost"
