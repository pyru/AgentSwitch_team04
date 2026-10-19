"""AI-WRITTEN TESTS (written by Claude, 2026-10-19).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

The platform set grew from 6 tasks (8 runs) to 9 tasks (11 runs) to cover more complex cases: feasibility by a date,
the declared seat policy that is not this seat's permission, and the machine that lost most time to breakdowns.
Both instances share one 300k submission budget, so `"platform"` may now name the instances a task joins on, and a
task declared on both instances can join on only the one where it fits.

Run: python -m pytest tests_ai/test_platform_instances.py -q
"""
from harness import runner


def test_true_means_every_declared_instance():
    task = {"instances": ["suryodaya", "keystone"], "platform": True}
    assert runner.platform_instances(task) == ["suryodaya", "keystone"]


def test_a_list_names_some_of_the_declared_instances():
    task = {"instances": ["suryodaya", "keystone"], "platform": ["keystone"]}
    assert runner.platform_instances(task) == ["keystone"]


def test_a_list_cannot_add_an_instance_the_task_does_not_declare():
    task = {"instances": ["suryodaya"], "platform": ["keystone"]}
    assert runner.platform_instances(task) == []


def test_no_flag_is_no_platform_run():
    assert runner.platform_instances({"instances": ["suryodaya", "keystone"]}) == []
    assert runner.platform_instances({"instances": ["suryodaya"], "platform": False}) == []


def test_the_platform_set_is_the_one_rehearsed():
    runs = sorted((t["id"], i) for t in runner.load_tasks(False) for i in runner.platform_instances(t))
    assert runs == [
        ("blocks_wo48_sales_order", "suryodaya"),
        ("capacity_load_disputed", "keystone"),
        ("capacity_load_disputed", "suryodaya"),
        ("declared_policy_not_permission", "suryodaya"),
        ("downtime_breakdown_top_machine", "keystone"),
        ("feasible_by_wo48", "suryodaya"),
        ("keystone_customer_impact_wo4", "keystone"),
        ("keystone_why_late_wo3", "keystone"),
        ("refuse_unknown_work_order", "keystone"),
        ("refuse_unknown_work_order", "suryodaya"),
        ("why_late_wo48_subcontract", "suryodaya"),
    ]
