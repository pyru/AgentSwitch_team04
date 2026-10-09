"""Check a results.json against AgentSwitch's harness runner format before spending a submission on it.

    python scripts/check_results.py                      # ./results.json
    python scripts/check_results.py path/to/results.json

The runner allows one run per team every 3 days and shows no results at all for a malformed file.

Written with Claude (AI-assisted).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.results import RESULTS_NAME, problems  # noqa: E402


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else Path.cwd() / RESULTS_NAME
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"FAIL  {path}: {exc}")
        return 1
    found = problems(doc)
    for problem in found:
        print(f"FAIL  {problem}")
    if found:
        return 1
    tasks = doc["tasks"]
    print(f"PASS  {path}: {len(tasks)} tasks, {sum(t['passed'] for t in tasks)} passed")
    print(f"      {doc['summary']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
