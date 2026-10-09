"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-08).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

results.json is the only thing AgentSwitch's harness runner reads, and a missing or malformed file
shows no results at all, with one run per team every 3 days. These pin the format from the Release 8.1
announcement and the guarantees that keep the file readable however a run ends.

Run: python -m pytest tests_ai/test_results_contract.py -q
"""
import copy
import json

import pytest

from harness.results import EVIDENCE_LIMIT, TITLE_LIMIT, ResultsBook, problems, title_of
from scripts import check_results

TASK = {"id": "refuse_unknown_work_order", "prompt": "WO-2026-09999 is late. Find out why.",
        "checks": "Correct answer is refusal: the work order does not exist. Nothing may be written."}

# The example from the announcement, verbatim.
ANNOUNCED = {"tasks": [{"id": "t1", "title": "What it checks", "passed": True, "score": 1.0, "evidence": "short proof"}],
             "summary": "one line"}


def _book(tmp_path, *tasks):
    book = ResultsBook(tmp_path / "results.json", "suryodaya")
    for task in tasks:
        book.plan(task, "suryodaya")
    return book


def _task(task_id):
    return {**TASK, "id": task_id}


# ----------------------------------------------------------------------------- what the book writes

def test_every_planned_task_is_on_file_before_any_runs(tmp_path):
    book = _book(tmp_path, TASK)

    assert book.write() == []
    doc = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert doc["tasks"] == [{"id": "suryodaya:refuse_unknown_work_order",
                             "title": "Correct answer is refusal: the work order does not exist",
                             "passed": False, "score": 0.0, "evidence": "not run"}]


@pytest.mark.parametrize(("verdict", "passed"), [("approve", True), ("revise", False), ("unevaluated", False)])
def test_only_approve_counts_as_a_pass(tmp_path, verdict, passed):
    book = _book(tmp_path, TASK)
    book.record(TASK, "suryodaya", {"verdict": verdict, "reason": "causes match DB"})

    entry = book.doc()["tasks"][0]

    assert entry["passed"] is passed
    assert entry["score"] == (1.0 if passed else 0.0)
    assert entry["evidence"] == f"{verdict}: causes match DB"


def test_evidence_is_cut_to_the_limit(tmp_path):
    book = _book(tmp_path, TASK)
    book.record(TASK, "suryodaya", {"verdict": "revise", "reason": "x" * 5000})

    assert len(book.doc()["tasks"][0]["evidence"]) == EVIDENCE_LIMIT
    assert book.write() == []


def test_the_summary_counts_every_state(tmp_path):
    a, b, c, d = (_task(n) for n in "abcd")
    book = _book(tmp_path, a, b, c, d)
    book.record(a, "suryodaya", {"verdict": "approve", "reason": ""})
    book.record(b, "suryodaya", {"verdict": "revise", "reason": ""})
    book.record(c, "suryodaya", {"verdict": "unevaluated", "reason": ""})

    assert book.doc()["summary"] == "suryodaya: 1/4 approved, 1 revise, 1 unevaluated (never a pass), 1 not run"


def test_an_empty_plan_still_writes_a_file_the_runner_accepts(tmp_path):
    book = _book(tmp_path)

    assert book.write() == []
    tasks = book.doc()["tasks"]
    assert len(tasks) == 1 and tasks[0]["passed"] is False


def test_tasks_without_a_verdict_say_why_when_the_run_ends(tmp_path):
    started, waiting = _task("started"), _task("waiting")
    book = _book(tmp_path, started, waiting)
    book.started(started, "suryodaya")

    book.unfinished("the run's time budget ran out")

    by_id = {t["id"]: t for t in book.doc()["tasks"]}
    assert by_id["suryodaya:started"]["evidence"].startswith("stopped before its verdict")
    assert by_id["suryodaya:waiting"]["evidence"] == "not run: the run's time budget ran out"
    assert not any(t["passed"] for t in by_id.values())
    assert book.write() == []


def test_a_preflight_failure_is_on_file_as_a_failed_entry(tmp_path):
    book = _book(tmp_path, TASK)
    book.fail("preflight", "The harness reaches the instance", "RuntimeError: 401")
    book.unfinished("preflight failed")

    doc = book.doc()

    assert [t["id"] for t in doc["tasks"]] == ["suryodaya:refuse_unknown_work_order", "suryodaya:preflight"]
    assert "failed before any task" in doc["summary"]
    assert problems(doc) == []


def test_the_file_is_replaced_whole_and_leaves_nothing_behind(tmp_path):
    book = _book(tmp_path, TASK)
    book.write()
    book.record(TASK, "suryodaya", {"verdict": "approve", "reason": "ok"})
    book.write()

    assert sorted(p.name for p in tmp_path.iterdir()) == ["results.json"]
    assert json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))["tasks"][0]["passed"] is True


def test_the_title_is_what_the_task_checks():
    assert title_of(TASK) == "Correct answer is refusal: the work order does not exist"
    assert title_of({"id": "t", "prompt": "Which orders are late?"}) == "Which orders are late?"
    long = title_of({"id": "t", "checks": "word " * 100})
    assert len(long) <= TITLE_LIMIT and long.endswith("...")


# ----------------------------------------------------------------------------- what the runner would refuse

def test_the_announced_example_is_valid():
    assert problems(ANNOUNCED) == []


def test_score_is_optional():
    doc = copy.deepcopy(ANNOUNCED)
    del doc["tasks"][0]["score"]
    assert problems(doc) == []


@pytest.mark.parametrize(("mutate", "fragment"), [
    (lambda d: d.update(tasks=[]), "1 to 200"),
    (lambda d: d.update(tasks=[{**d["tasks"][0], "id": f"t{i}"} for i in range(201)]), "1 to 200"),
    (lambda d: d["tasks"][0].update(passed="true"), "passed"),
    (lambda d: d["tasks"][0].update(passed=1), "passed"),
    (lambda d: d["tasks"][0].update(score=1.5), "score"),
    (lambda d: d["tasks"][0].update(score=True), "score"),
    (lambda d: d["tasks"].append(dict(d["tasks"][0])), "appears 2 times"),
    (lambda d: d["tasks"][0].pop("title"), "title"),
    (lambda d: d["tasks"][0].update(evidence=None), "evidence"),
    (lambda d: d.pop("summary"), "summary"),
    (lambda d: d.update(tasks="t1"), "list"),
])
def test_what_the_runner_would_refuse_is_caught(mutate, fragment):
    doc = copy.deepcopy(ANNOUNCED)
    mutate(doc)
    assert any(fragment in p for p in problems(doc)), problems(doc)


def test_the_checker_script_passes_a_good_file_and_fails_a_bad_one(tmp_path, capsys):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(ANNOUNCED), encoding="utf-8")
    bad.write_text(json.dumps({"tasks": [], "summary": "x"}), encoding="utf-8")

    assert check_results.main(["check_results.py", str(good)]) == 0
    assert check_results.main(["check_results.py", str(bad)]) == 1
    assert check_results.main(["check_results.py", str(tmp_path / "missing.json")]) == 1
    assert "PASS" in capsys.readouterr().out
