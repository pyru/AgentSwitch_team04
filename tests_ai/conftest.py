"""Keep the AgentSwitch harness runner's variables out of AI-written tests unless a test sets them itself.

A shell that has just run a platform rehearsal still exports AGENTSWITCH_TOKEN; left in place it would switch every
Session and agent built here into platform mode, and HARNESS_BUDGET_MINUTES would put a clock on them.

Written with Claude (AI-assisted).
"""
import pytest

HARNESS_RUNNER_VARIABLES = ("AGENTSWITCH_TOKEN", "AGENTSWITCH_BASE_URL", "AGENTSWITCH_INSTANCE", "HARNESS_BUDGET_MINUTES")


@pytest.fixture(autouse=True)
def no_harness_runner_environment(monkeypatch):
    for name in HARNESS_RUNNER_VARIABLES:
        monkeypatch.delenv(name, raising=False)
