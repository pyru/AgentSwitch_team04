"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-07).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

Seen live 2026-10-07 on complex_order_by_item_name: asked about "the Skid-Steer Quick-Attach Plate
job", the model read 20 of 77 WorkOrders, took WO-2026-00070 (completed in May) and reported the job
on time. The only open order for the item, WO-2026-00003, was overdue. find_orders_for_item returns
open orders only, late first, so a completed order cannot be mistaken for the job.

Run: python -m pytest tests_ai/test_find_orders_for_item.py -q
"""
import datetime as dt

import pytest

from prod_agent import config, domain
from prod_agent.agent import ProductionAgent

ITEM = {"id": "item-1", "code": "FG-PLT-0900", "name": "Skid-Steer Quick-Attach Plate", "number": "ITEM-1"}


def order(number, status, end, item_id="item-1"):
    return {"id": f"id-{number}", "number": number, "status": status, "item_id": item_id,
            "planned_start_date": "2026-07-01", "planned_end_date": end}


class FakeMcp:
    def __init__(self, orders, schedule=()):
        self.orders, self.schedule, self.list_calls = orders, list(schedule), []

    def list_all(self, entity, **filters):
        self.list_calls.append((entity, filters))
        if entity == "Item":
            return [ITEM]
        rows = self.orders
        if "item_id" in filters:
            rows = [r for r in rows if r["item_id"] == filters["item_id"]]
        return rows

    def call(self, name, args):
        assert name == "endpoint.manufacturing.finite_schedule", name
        return {"result": {"orders": self.schedule}}


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(config, "today", lambda: dt.date(2026, 10, 7))


def test_the_live_failure_cannot_repeat():
    """Ten completed orders and one overdue open one: only the open one is offered."""
    completed = [order(f"WO-2026-000{n}", "completed", "2026-05-15") for n in range(16, 71, 6)]
    mcp = FakeMcp(completed + [order("WO-2026-00003", "not_started", "2026-08-31")])
    r = domain.find_orders_for_item(mcp, "Skid-Steer Quick-Attach Plate")

    assert [o["number"] for o in r["open_orders"]] == ["WO-2026-00003"]
    assert r["open_orders"][0]["is_late"] is True and r["open_orders"][0]["days_past_due"] == 37
    assert r["closed_orders_not_listed"] == len(completed)
    assert "only open order" in r["instruction"]
    assert ("WorkOrder", {"item_id": "item-1"}) in mcp.list_calls


def test_late_orders_come_first_most_overdue_first():
    mcp = FakeMcp([order("WO-ON-TIME", "in_progress", "2026-12-01"),
                   order("WO-LATE-A", "stopped", "2026-09-01"),
                   order("WO-LATE-B", "not_started", "2026-06-01")])
    r = domain.find_orders_for_item(mcp, "FG-PLT-0900")
    assert [o["number"] for o in r["open_orders"]] == ["WO-LATE-B", "WO-LATE-A", "WO-ON-TIME"]
    assert "most overdue" in r["instruction"]


def test_the_schedule_verdict_also_makes_an_order_late():
    """Same rule as list_late_work_orders: due in the future but projected late still counts."""
    mcp = FakeMcp([order("WO-PROJECTED", "in_progress", "2026-12-01"), order("WO-FINE", "in_progress", "2026-12-05")],
                  schedule=[{"work_order_id": "id-WO-PROJECTED", "verdict": "late"}])
    r = domain.find_orders_for_item(mcp, "FG-PLT-0900")
    assert r["open_orders"][0]["number"] == "WO-PROJECTED" and r["open_orders"][0]["is_late"] is True
    assert "only WO-PROJECTED is late" in r["instruction"]


def test_no_open_order_says_so_instead_of_offering_a_closed_one():
    r = domain.find_orders_for_item(FakeMcp([order("WO-DONE", "completed", "2026-05-15")]), "FG-PLT-0900")
    assert r["open_orders"] == [] and r["closed_orders_not_listed"] == 1
    assert "no open work order" in r["instruction"]


def test_an_unknown_item_is_not_found():
    assert domain.find_orders_for_item(FakeMcp([]), "NO-SUCH-PART")["found"] is False


def test_the_agent_offers_the_tool_and_dispatches_it(monkeypatch):
    monkeypatch.setattr(domain, "find_orders_for_item", lambda mcp, item: {"called_with": item})
    agent = ProductionAgent.__new__(ProductionAgent)
    agent.mcp, agent._examined, agent.apply_mode, agent.escalate_mode = object(), set(), False, False
    names = {s["function"]["name"] for s in ProductionAgent.tool_specs(agent)}
    assert "find_orders_for_item" in names
    assert agent._dispatch("find_orders_for_item", {"item": "FG-PLT-0900"}) == {"called_with": "FG-PLT-0900"}
    assert "find_orders_for_item" in ProductionAgent.PARALLEL_SAFE and "find_orders_for_item" in ProductionAgent.REPEAT_GUARDED
