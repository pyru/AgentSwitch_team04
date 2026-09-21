"""AI-WRITTEN REGRESSION TESTS (written by Codex, 2026-09-21).

These tests are ungraded and prove run-directory collisions fail without invoking the live harness.
The graded, hand-written tests live in tests/.
"""
import datetime as dt
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from harness import runner


def test_new_run_roots_are_distinct_ordered_and_checker_compatible(tmp_path):
    first = runner._new_run_root(tmp_path)
    second = runner._new_run_root(tmp_path)

    assert first != second
    assert first.is_dir()
    assert second.is_dir()
    assert sorted([first.name, second.name]) == [first.name, second.name]
    assert re.fullmatch(r"\d{8}-\d{6}-\d{6}", first.name)
    assert first in tmp_path.glob("2026*")


def test_new_run_root_refuses_collision_without_disturbing_first_run(monkeypatch, tmp_path):
    fixed = dt.datetime(2026, 9, 21, 12, 34, 56, 123456)

    class FrozenDatetime(dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(runner, "dt", SimpleNamespace(datetime=FrozenDatetime))
        first = runner._new_run_root(tmp_path)
        sentinel = first / "existing.json"
        sentinel.write_text("preserve me", encoding="utf-8")

        with pytest.raises(FileExistsError):
            runner._new_run_root(tmp_path)

        assert sentinel.read_text(encoding="utf-8") == "preserve me"

    assert runner.dt is dt


def test_checker_globs_accept_mixed_run_root_names(tmp_path):
    runs = tmp_path / "runs"
    old_root = runs / "20260916-114054"
    new_root = runs / "20260917-110938-000001"
    for root, task_id in ((old_root, "refuse_old"), (new_root, "refuse_new")):
        task_dir = root / "suryodaya" / task_id
        task_dir.mkdir(parents=True)
        (root / "summary.json").write_text(json.dumps({"runs": []}), encoding="utf-8")
        (task_dir / "verdict.json").write_text(json.dumps({"verdict": "approve"}), encoding="utf-8")
    adhoc = runs / "adhoc"
    adhoc.mkdir(parents=True)
    (adhoc / "summary.json").write_text(json.dumps({"runs": []}), encoding="utf-8")

    # This duplicates the checker's patterns, proving mixed names work but not detecting later checker changes.
    roots = sorted(path for path in runs.glob("2026*") if (path / "summary.json").exists())
    latest = roots[-1]
    task_dirs = list(latest.glob("*/*"))
    refusal_verdicts = list(latest.glob("*/refuse_*/verdict.json"))

    assert latest == new_root
    assert task_dirs == [new_root / "suryodaya" / "refuse_new"]
    assert refusal_verdicts == [new_root / "suryodaya" / "refuse_new" / "verdict.json"]
    assert runs / "adhoc" not in roots


def test_run_one_refuses_existing_task_directory_without_disturbing_it(tmp_path):
    run_dir = tmp_path / "suryodaya" / "collision"
    run_dir.mkdir(parents=True)
    sentinel = run_dir / "existing.json"
    sentinel.write_text("preserve me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        runner.run_one({"id": "collision"}, "suryodaya", tmp_path)

    assert sentinel.read_text(encoding="utf-8") == "preserve me"
    assert sorted(run_dir.iterdir()) == [sentinel]


def test_trace_modes_and_cli_run_directory_mode_are_exclusive_in_source():
    # The harness trace open follows live Session work; the CLI checks are coupled to its live main entry point.
    repo_root = Path(__file__).resolve().parent.parent
    harness_source = (repo_root / "harness" / "runner.py").read_text(encoding="utf-8")
    cli_source = (repo_root / "prod_agent" / "__main__.py").read_text(encoding="utf-8")
    exclusive_trace = '(run_dir / "trace.jsonl").open("x", encoding="utf-8")'
    append_trace = '(run_dir / "trace.jsonl").open("a", encoding="utf-8")'

    assert exclusive_trace in harness_source
    assert exclusive_trace in cli_source
    assert append_trace not in harness_source
    assert append_trace not in cli_source
    assert "run_dir.mkdir(parents=True, exist_ok=False)" in cli_source
    assert "run_dir.mkdir(parents=True, exist_ok=True)" not in cli_source
