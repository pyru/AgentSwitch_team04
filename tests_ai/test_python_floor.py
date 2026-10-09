"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-10-08).

These are NOT the team's hand-written tests and must not be claimed as such: the course scores
AI-written tests at zero.

AgentSwitch's harness runner does not say which Python it runs; stock Ubuntu 22.04 ships 3.10. On
3.10, datetime.UTC (new in 3.11) made record_finding raise for every task, so no finding was ever
saved. Run under 3.10 on 2026-10-08: 5 tests failed on that one name. The runtime code (prod_agent,
harness) must stay on what 3.10 has; tests and scripts/verify_submission.py may use 3.11 (tomllib).

Run: python -m pytest tests_ai/test_python_floor.py -q
"""
import io
import re
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = sorted(p for d in ("prod_agent", "harness") for p in (ROOT / d).rglob("*.py"))


def _code_only(source: str) -> str:
    """The source with every comment blanked, so a comment explaining why a name is avoided is not a use of it."""
    lines = source.splitlines(keepends=True)
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            row, col = tok.start
            line = lines[row - 1]
            body = line.rstrip("\r\n")
            lines[row - 1] = body[:col] + " " * (len(body) - col) + line[len(body):]
    return "".join(lines)

# Names a 3.10 interpreter does not have, as they would appear in this codebase.
NEWER_THAN_310 = {
    r"\bdt\.UTC\b|\bdatetime\.UTC\b": "datetime.UTC is 3.11+; use dt.timezone.utc",
    r"\bimport tomllib\b|\bfrom tomllib\b": "tomllib is 3.11+",
    r"\bStrEnum\b": "enum.StrEnum is 3.11+",
    r"\bexcept\s*\*": "except* is 3.11+",
    r"\bfrom typing import .*\bSelf\b": "typing.Self is 3.11+",
}


def _uses(source: str) -> list[str]:
    code = _code_only(source)
    return [why for pattern, why in NEWER_THAN_310.items() if re.search(pattern, code)]


def test_the_scan_catches_the_line_that_broke_and_ignores_comments_about_it():
    assert _uses('payload = {"recorded_at": dt.datetime.now(dt.UTC).isoformat()}\n')
    assert _uses("x = 1  # not dt.UTC: 3.11+\n") == []


@pytest.mark.parametrize("path", RUNTIME, ids=lambda p: str(p.relative_to(ROOT)))
def test_runtime_code_runs_on_python_310(path):
    source = _code_only(path.read_text(encoding="utf-8"))
    found = [f"line {source[:m.start()].count(chr(10)) + 1}: {why}"
             for pattern, why in NEWER_THAN_310.items() for m in re.finditer(pattern, source)]
    assert not found, found
