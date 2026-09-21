"""Pre-submission checklist. Not a test (it scores nothing); it only reports readiness.

    python scripts/verify_submission.py            # all checks, including live bug-report lookup
    python scripts/verify_submission.py --offline  # skip network checks

Written with Claude (AI-assisted).
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def main():
    offline = "--offline" in sys.argv
    if os.environ.get("AGENT_OFFLINE") == "1" and not offline:
        print("ERROR: AGENT_OFFLINE=1 requires --offline; pass --offline or unset AGENT_OFFLINE")
        return 1

    print("\n== A. Gap report")
    gap = ROOT / "GAP_REPORT.md"
    text = gap.read_text(encoding="utf-8") if gap.exists() else ""
    check("GAP_REPORT.md exists", bool(text))
    for needle, label in [("Carbon", "names a modern competitor"),
                          ("## 1.", "Q1: what they do that we do not"),
                          ("## 2.", "Q2: gaps an agent can close today"),
                          ("platform work", "gaps that need platform work"),
                          ("## 3.", "Q3: what our agent can do that they cannot")]:
        check(label, needle in text)
    words = len(text.split())
    check("about one page", words <= 1100, f"{words} words")

    print("\n== B. Agent")
    agent_src = (ROOT / "prod_agent" / "agent.py").read_text(encoding="utf-8")
    check("own loop (no framework)", "for step in range(self.max_steps)" in agent_src)
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    check("no agent framework in requirements", not any(f in reqs for f in ("langchain", "llama", "autogen", "crewai")))
    domain_src = (ROOT / "prod_agent" / "domain.py").read_text(encoding="utf-8")
    check("re-reads before writing", "changed_underneath" in domain_src)
    check("currency read from Company, not hardcoded", "default_currency" in domain_src)

    print("\n== C. Harness")
    verifier_src = (ROOT / "harness" / "verifiers" / "team04.py").read_text(encoding="utf-8")
    check("verifiers never read the reply text", "final_answer" not in verifier_src)
    check("verifiers read the database", "finding_from_db" in verifier_src and "ctx.rest" in verifier_src)

    tasks = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "harness" / "tasks" / "team04").glob("*.json")]
    refusals = [t["id"] for t in tasks if t["id"].startswith("refuse_")]
    check("task set present", len(tasks) > 0, f"{len(tasks)} tasks")
    check("at least one refusal task", len(refusals) >= 1, f"{len(refusals)} refusal tasks")

    runs = sorted(p for p in (ROOT / "runs").glob("2026*") if (p / "summary.json").exists()) if (ROOT / "runs").exists() else []
    if not runs:
        check("a harness run exists (python -m harness.runner)", False)
    else:
        latest = runs[-1]
        summary = json.loads((latest / "summary.json").read_text(encoding="utf-8"))
        check(f"latest full run {latest.name}: all approved",
              summary["approved"] == summary["scored_total"] and summary["unevaluated"] == 0,
              f"{summary['approved']}/{summary['scored_total']} approved, {summary['unevaluated']} unevaluated")
        order_ok, missing = True, []
        for d in latest.glob("*/*"):
            r, v = d / "result.json", d / "verdict.json"
            if not (r.exists() and v.exists()):
                missing.append(d.name)
            elif r.stat().st_mtime > v.stat().st_mtime:
                order_ok = False
        check("every run written to disk before scoring", order_ok and not missing,
              f"missing files in {missing}" if missing else "result.json older than verdict.json everywhere")
        refusal_verdicts = [json.loads(p.read_text(encoding="utf-8"))["verdict"]
                            for p in latest.glob("*/refuse_*/verdict.json")]
        check("refusal tasks approved in latest run",
              bool(refusal_verdicts) and all(v == "approve" for v in refusal_verdicts),
              f"{refusal_verdicts.count('approve')}/{len(refusal_verdicts)}")

    print("\n== D. Hand-written tests")
    test_files = list((ROOT / "tests").glob("test_*.py"))
    n_tests = sum(1 for f in test_files for node in ast.walk(ast.parse(f.read_text(encoding="utf-8")))
                  if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"))
    check("hand-written tests exist in tests/", n_tests > 0, f"{n_tests} test functions (10 points each if hand-written)")
    labelled = [f.name for f in test_files if "claude" in f.read_text(encoding="utf-8").lower()]
    check("no AI-authorship label inside tests/", not labelled, ", ".join(labelled))
    offline_skipped = None
    if n_tests:
        env = os.environ.copy()
        if offline:
            env["AGENT_OFFLINE"] = "1"
        with tempfile.TemporaryDirectory() as report_dir:
            report = Path(report_dir) / "report.xml"
            rc = subprocess.run(
                [sys.executable, "-m", "pytest", "tests", "-q", f"--junitxml={report}"],
                cwd=ROOT,
                env=env,
            ).returncode
            if rc != 0:
                check("pytest passes", False, f"pytest exited with code {rc}")
            elif offline:
                try:
                    suite = ET.parse(report).getroot().find("testsuite")
                    if suite is None:
                        raise ValueError("testsuite element missing")
                    tests = int(suite.attrib["tests"])
                    skipped = int(suite.attrib["skipped"])
                except (OSError, ET.ParseError, KeyError, TypeError, ValueError) as exc:
                    check("pytest report readable", False, f"pytest report could not be read: {exc}")
                else:
                    if skipped > 0:
                        offline_skipped = skipped
                        print(
                            f"skip  pytest: {tests - skipped} ran, {skipped} skipped "
                            "(live tenant fixtures; AGENT_OFFLINE=1)"
                        )
                    else:
                        check("offline gate engaged", False, "pytest report recorded zero skipped tests")
            else:
                check("pytest passes", True)

    print("\n== E. Bugs")
    if offline:
        print("skip  bug reports (offline)")
    else:
        from prod_agent.mcp_client import RestClient, Session
        for inst, expected in (("suryodaya", 4), ("keystone", 1)):
            rows = RestClient(Session(inst)).raw("/api/bug-report/mine").get("data", [])
            check(f"bug reports on record: {inst}", len(rows) >= expected, f"{len(rows)} filed")

    print("\n== F. Safe to publish")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8") if (ROOT / ".gitignore").exists() else ""
    check(".env and .tokens/ are git-ignored", ".env" in gitignore and ".tokens" in gitignore)
    leaked = []
    # Built at runtime so this file does not match its own search.
    key_marker, password_marker = "sk-" + "proj-", "!aA" + "1"
    for p in ROOT.rglob("*"):
        if p.is_file() and not any(part in (".git", "runs", ".tokens", "__pycache__") for part in p.parts) \
                and p.name != ".env" and p.suffix in (".py", ".md", ".json", ".txt", ".example"):
            body = p.read_text(encoding="utf-8", errors="ignore")
            if key_marker in body or password_marker in body:
                leaked.append(str(p.relative_to(ROOT)))
    check("no API key or password in committable files", not leaked, ", ".join(leaked))

    if offline:
        if offline_skipped:
            print(f"\nThis is not full submission verification: {offline_skipped} live graded tests and "
                  "section E bug reports were skipped.")
        else:
            print("\nThis is not full submission verification: section E bug reports were skipped.")
    print(f"\n{sum(results)}/{len(results)} checks passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
