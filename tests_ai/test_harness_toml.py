"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-08).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

agentswitch-harness.toml is the contract with AgentSwitch's harness runner (Release 8.1): install,
run, results, instances, timeout_minutes. One run per team every 3 days, so a wrong value costs a run.

Run: python -m pytest tests_ai/test_harness_toml.py -q
"""
import tomllib
from pathlib import Path

from harness import runner
from harness.results import RESULTS_NAME
from prod_agent import config

ROOT = Path(__file__).resolve().parent.parent
SPEC = tomllib.loads((ROOT / "agentswitch-harness.toml").read_text(encoding="utf-8"))


def test_the_toml_has_every_key_the_runner_reads():
    assert {"install", "run", "results", "instances", "timeout_minutes"} <= set(SPEC)


def test_it_runs_our_harness_and_reads_the_file_it_writes():
    assert SPEC["run"].startswith("python -m harness.runner")
    assert SPEC["results"] == RESULTS_NAME


def test_it_lists_only_instances_we_have():
    assert SPEC["instances"] and set(SPEC["instances"]) <= set(config.INSTANCES)


def test_the_timeout_leaves_room_for_our_own_clock_to_stop_first():
    timeout = SPEC["timeout_minutes"]
    assert type(timeout) is int and 1 <= timeout <= 30
    assert runner.PLATFORM_BUDGET_MINUTES * 60 + runner.WATCHDOG_GRACE_SECONDS < timeout * 60


def test_install_pins_the_openai_sdk_and_brings_no_other_vendor_sdk():
    assert "requirements.txt" in SPEC["install"]
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    assert "openai>=1.40,<2" in requirements
    assert not any(sdk in requirements for sdk in ("anthropic", "google-generativeai", "google-genai"))


# What the first official run (2026-10-12) spent before every call was refused with budget_exhausted. Both
# instances share it, and each run's preflight spends a little before any task: about 300 tokens per instance in the
# 2026-10-19 official run (172,829 in all against 172.2k for its eight tasks), so 2,000 leaves room to spare.
SUBMISSION_TOKEN_BUDGET = 300_000
PREFLIGHT_TOKENS = 2_000


def test_every_platform_task_can_start_within_its_instances_share():
    run = SPEC["run"].split()
    assert "--platform-set" in run and "--token-budget" in run
    share = int(run[run.index("--token-budget") + 1])
    platform_tasks = [t for t in runner.load_tasks(False) if runner.platform_instances(t)]
    for instance in SPEC["instances"]:
        limits = [t.get("max_tokens", runner.TASK_TOKENS_DEFAULT) for t in platform_tasks
                  if instance in runner.platform_instances(t)]
        assert limits, f"no platform task on {instance}"
        assert sum(limits) <= share, f"{instance}: {sum(limits)} tokens of task limits in a {share} share"
    assert (share + PREFLIGHT_TOKENS) * len(SPEC["instances"]) <= SUBMISSION_TOKEN_BUDGET


def test_the_platform_set_only_reads():
    """No fixture writes and no write or escalation tool, so a task can never leave work for another to trip on."""
    for task in (t for t in runner.load_tasks(False) if t.get("platform")):
        assert runner.isolated(task), task["id"]


def test_results_json_is_never_committed():
    assert RESULTS_NAME in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
