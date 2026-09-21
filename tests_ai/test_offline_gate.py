"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-09-21).

These tests are ungraded and prove the offline collection gate without using a real tenant. The
graded, hand-written tests live in tests/.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_offline_gate_skips_live_fixture_closure_and_requires_exact_value(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    shutil.copyfile(repo_root / "conftest.py", tmp_path / "conftest.py")
    (tmp_path / "test_synthetic.py").write_text(
        """import pytest


@pytest.fixture(scope="module")
def surya():
    raise AssertionError("surya sentinel fixture executed")


@pytest.fixture(scope="module")
def keystone():
    raise AssertionError("keystone sentinel fixture executed")


@pytest.fixture
def through_keystone(keystone):
    return keystone


def test_direct_live_fixture(surya):
    pass


def test_transitive_live_fixture(through_keystone):
    pass


def test_plain():
    pass
""",
        encoding="utf-8",
    )
    command = [sys.executable, "-m", "pytest", str(tmp_path), "-q", "-p", "no:cacheprovider"]

    offline_env = os.environ.copy()
    offline_env["AGENT_OFFLINE"] = "1"
    offline = subprocess.run(command, cwd=tmp_path, env=offline_env, capture_output=True, text=True)
    assert offline.returncode == 0, offline.stdout + offline.stderr
    assert "1 passed, 2 skipped" in offline.stdout

    unset_env = os.environ.copy()
    unset_env.pop("AGENT_OFFLINE", None)
    unset = subprocess.run(command, cwd=tmp_path, env=unset_env, capture_output=True, text=True)
    assert unset.returncode != 0, unset.stdout + unset.stderr
    assert "1 passed, 2 errors" in unset.stdout

    false_env = os.environ.copy()
    false_env["AGENT_OFFLINE"] = "0"
    false = subprocess.run(command, cwd=tmp_path, env=false_env, capture_output=True, text=True)
    assert false.returncode != 0, false.stdout + false.stderr
    assert "1 passed, 2 errors" in false.stdout
