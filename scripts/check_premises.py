"""Check each harness task's premise against the live tenants, with no model call and no write.

    python scripts/check_premises.py                    # every task, on every instance it declares
    python scripts/check_premises.py --platform-set     # only the tasks the platform runs
    python scripts/check_premises.py --instance keystone --task keystone_why_late_wo3

A premise that has gone (an order completed, a permission withdrawn) makes a task score unevaluated, which is a 0 on
the platform, and today the only way to find out is to spend a run. This reads only: it logs in, runs the read-only
fixture pickers, and calls each verifier as if the run had done nothing. A verifier checks its premise before it
grades (harness/verifiers/team04.py); one that reads the finding first would report a gone premise as "holds".
The verdict says which:

  holds    revise: none of the premises the verifier checks has gone, and it found nothing done, as it should
  GONE     unevaluated: the task would score 0 now; fix or swap it before submitting
  skip     the task's fixture writes work orders, so it cannot be checked without writing
  OTHER    approve for a run that did nothing (the task no longer tests anything), or an error; printed in full

A premise no verifier checks cannot show up here: escalation_raised_for never checks that an assignee exists, so
that task reads "holds" even on an instance where no escalation could be assigned.

It reads the shared tenants, so it needs their passwords in .env like any run. It writes nothing there.
Exits 1 if any checked premise is GONE or OTHER.

Written with Claude (AI-assisted).
"""
import argparse
import json
import sys
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness import runner  # noqa: E402
from harness.fixtures import FIXTURES, WRITING_FIXTURES  # noqa: E402
from harness.verify import Verdict, VerifyContext, normalise  # noqa: E402
from prod_agent import config  # noqa: E402
from prod_agent.mcp_client import McpClient, RestClient, Session  # noqa: E402

def classify(verdict: Verdict, reason: str) -> str:
    # Revise is what a run that did nothing deserves; escalation_raised_for says so before it looks for a finding.
    if verdict is Verdict.REVISE:
        return "holds"
    if verdict is Verdict.UNEVALUATED and not reason.startswith("verifier returned"):
        return "GONE"
    return "OTHER"


def check(task: dict, instance: str, session: Session, work: Path) -> tuple[str, str]:
    if task.get("fixture") in WRITING_FIXTURES:
        return "skip", f"fixture {task['fixture']} writes work orders"
    fixture = FIXTURES[task["fixture"]](McpClient(session)) if task.get("fixture") else None
    rest = RestClient(session)
    context = runner.capture_context(rest, task)
    run_dir = work / instance / task["id"]
    run_dir.mkdir(parents=True)
    # A run id no finding carries, so the verifier sees a run that recorded nothing.
    (run_dir / "result.json").write_text(json.dumps({"run_id": f"premise-check-{uuid.uuid4()}"}), encoding="utf-8")
    (run_dir / "trace.jsonl").write_text("", encoding="utf-8")
    ctx = VerifyContext(rest=rest, instance=instance, task=task, run_dir=run_dir, fixture=fixture, context=context)
    verdict, reason = normalise(runner._load_verifier(task["verifier"])(ctx))
    return classify(verdict, reason), reason


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--instance", choices=sorted(config.INSTANCES) + ["all"], default="all")
    ap.add_argument("--task", action="append", help="task id (repeatable)")
    ap.add_argument("--platform-set", action="store_true", help='only tasks marked "platform": true')
    args = ap.parse_args(argv)

    tasks = [t for t in runner.load_tasks(False) if not args.task or t["id"] in args.task]
    if args.platform_set:
        tasks = [t for t in tasks if runner.platform_instances(t)]
    instances = sorted(config.INSTANCES) if args.instance == "all" else [args.instance]

    def runs_on(task: dict, instance: str) -> bool:
        if args.platform_set:
            return instance in runner.platform_instances(task)
        return instance in task.get("instances", sorted(config.INSTANCES))

    counts: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as tmp:
        for instance in instances:
            session = Session(instance)
            for task in (t for t in tasks if runs_on(t, instance)):
                try:
                    status, reason = check(task, instance, session, Path(tmp))
                except Exception as e:  # one unreadable premise must not hide the rest
                    status, reason = "OTHER", f"{type(e).__name__}: {e}"
                counts[status] = counts.get(status, 0) + 1
                note = "" if status == "holds" else f"  {reason}"
                tag = " [platform]" if instance in runner.platform_instances(task) else ""
                print(f"{status:5}  {instance:10} {task['id']}{tag}{note}", flush=True)
    print("\n" + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    return 1 if counts.get("GONE") or counts.get("OTHER") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
