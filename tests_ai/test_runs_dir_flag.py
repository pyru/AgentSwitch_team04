"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-09-30).

Ungraded. Prove --runs-dir moves a run root without changing the default the submission checker reads.
The graded, hand-written tests live in tests/.
"""
import sys

from harness import runner
from prod_agent import config


def _record(task, instance, root):
    return {"task_id": task["id"], "instance": instance, "verdict": "approve", "reason": "ok",
            "sample": False, "run_id": "r1", "seconds": 1.0}


def test_runs_dir_puts_the_run_root_and_summary_under_the_given_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "load_tasks", lambda include_samples: [{"id": "refuse_x", "instances": ["suryodaya"]}])
    monkeypatch.setattr(runner, "run_one", _record)
    demo = tmp_path / "demo"
    monkeypatch.setattr(sys, "argv", ["runner", "--task", "refuse_x", "--runs-dir", str(demo)])

    runner.main()

    roots = [p for p in demo.iterdir() if p.is_dir()]
    assert len(roots) == 1
    assert (roots[0] / "summary.json").exists()


def test_default_runs_dir_is_still_the_directory_the_checker_reads(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(runner, "load_tasks", lambda include_samples: [])
    monkeypatch.setattr(runner, "_new_run_root", lambda base: seen.append(base) or tmp_path)
    monkeypatch.setattr(sys, "argv", ["runner"])

    runner.main()

    assert seen == [config.ROOT / "runs"]
