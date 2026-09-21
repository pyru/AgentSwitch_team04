"""Keep pytest offline when AGENT_OFFLINE=1 is set in the shell, not in .env.

The gate is bypassed whenever pytest does not load this file, including ``cd tests && pytest .``,
an absolute tests path from an unrelated directory, or ``--noconftest``. Always invoke pytest from
the repository root.

Written with Claude (AI-assisted).
"""
import os

import pytest


LIVE_TENANT_FIXTURES = frozenset({"surya", "suryodaya", "keystone"})


def pytest_collection_modifyitems(config, items):
    if os.environ.get("AGENT_OFFLINE") != "1":
        return

    for item in items:
        fixture_names = set(getattr(item, "fixturenames", ()))
        if fixture_names & LIVE_TENANT_FIXTURES:
            item.add_marker(pytest.mark.skip(reason="live tenant fixture; AGENT_OFFLINE=1"))
