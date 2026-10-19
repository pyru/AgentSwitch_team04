"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-19).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

A local full run on deepseek-v4.1-flash (2026-10-19) spent 396k tokens on one task, bottleneck_lanes_reported,
because the thinking-off probe ran only in platform mode: a local rehearsal of the platform's reasoning model
thought freely, so neither its tokens nor its behaviour predicted the platform run. These pin that a local run
probes too, hands what it found to every task, and stops before any task when the model cannot be reached.

Run: python -m pytest tests_ai/test_local_thinking_off.py -q
"""
import json
import sys

import pytest

from harness import runner
from tests_ai.test_llm_error import isolated_environment  # noqa: F401
from tests_ai.test_token_budget import ThinkingHost

LOCK_FD_ENV = "HARNESS_RUN_LOCK_FD"  # runner.RUN_LOCK_FD_ENV
TASKS = [{"id": "refuse_x", "instances": ["suryodaya"]}, {"id": "why_late_x", "instances": ["keystone"]}]


@pytest.fixture
def local_run(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(runner, "RUN_LOCK_PATH", tmp_path / ".console-run.lock", raising=False)
    monkeypatch.delenv(LOCK_FD_ENV, raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "deepseek/deepseek-v4.1-flash")
    monkeypatch.setattr(runner, "load_tasks", lambda include_samples: TASKS)
    sent = []
    monkeypatch.setattr(runner, "run_one", lambda task, instance, root, **kw: sent.append(kw["request_extra"]) or {
        "task_id": task["id"], "instance": instance, "verdict": "approve", "reason": "ok", "sample": False,
        "run_id": "r", "seconds": 1.0})
    monkeypatch.setattr(sys, "argv", ["runner", "--runs-dir", str(tmp_path / "out")])

    def run(host):
        providers = []
        monkeypatch.setattr(runner, "default_llm", lambda provider: providers.append(provider) or host)
        return runner.main(), sent, providers

    return run


def test_a_local_run_sends_every_task_the_switch_the_probe_found(local_run, tmp_path):
    host = ThinkingHost({"reasoning_effort none": 900, "thinking disabled": 4})
    code, sent, providers = local_run(host)

    assert code == 0
    assert providers == ["openrouter"]
    assert {r["model"] for r in host.requests} == {"deepseek/deepseek-v4.1-flash"}
    assert sent == [{"extra_body": {"thinking": {"type": "disabled"}}}] * 2
    assert "thinking: thinking disabled" in json.dumps(json.loads((tmp_path / "results.json").read_text()))


def test_a_model_that_takes_no_switch_still_runs_every_task_as_it_is(local_run):
    code, sent, _ = local_run(ThinkingHost())
    assert code == 0 and sent == [{}, {}]


def test_a_model_that_cannot_be_reached_stops_the_run_before_any_task(local_run, capsys):
    code, sent, _ = local_run(ThinkingHost(error=RuntimeError("connection refused")))

    assert code == 1 and sent == []
    assert "thinking probe failed: RuntimeError: connection refused" in capsys.readouterr().err
