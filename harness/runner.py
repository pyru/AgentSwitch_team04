"""Run the task set.

    python -m harness.runner                         # all tasks, all instances they declare
    python -m harness.runner --instance keystone --task refuse_unknown_wo
    python -m harness.runner --include-samples

Order per task: task.json -> fixture.json -> trace.jsonl (streamed) -> result.json, all fsync'd,
and only then the verifier runs and writes verdict.json.
"""
import argparse
import datetime as dt
import email.utils
import importlib
import json
import os
import traceback
import urllib.error
import urllib.request
from pathlib import Path

from prod_agent import config, domain
from prod_agent.agent import ProductionAgent
from prod_agent.mcp_client import McpClient, RestClient, Session

from .fixtures import FIXTURES, concurrent_edit
from .verify import Verdict, VerifyContext, normalise

TASK_DIR = Path(__file__).parent / "tasks"


def _new_run_root(base: Path) -> Path:
    # Run output is grading evidence, and reusing a collision silently produces merged artifacts that still parse.
    root = base / dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    root.mkdir(parents=True)
    return root


def _write(path: Path, data) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())


def load_tasks(include_samples: bool) -> list[dict]:
    tasks = []
    for path in sorted(TASK_DIR.rglob("*.json")):
        task = json.loads(path.read_text(encoding="utf-8"))
        task["_path"] = str(path.relative_to(config.ROOT))
        if task.get("sample") and not include_samples:
            continue
        tasks.append(task)
    return tasks


def _load_verifier(ref: str):
    module, _, func = ref.partition(":")
    return getattr(importlib.import_module(module), func)


def _find_by_number(rest: RestClient, entity: str, number: str) -> dict | None:
    hits = [r for r in rest.list(entity, search=number) if r.get("number") == number]
    return rest.get(entity, hits[0]["id"]) if hits else None


def _server_now_utc(base: str) -> dt.datetime:
    """The server's clock (HTTP Date header), so run-start comparisons with updated_at are not skewed by ours."""
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{base}/api/auth/me", method="HEAD"), timeout=30) as resp:
            headers = resp.headers
    except urllib.error.HTTPError as e:  # a 401 still carries the server's Date header
        headers = e.headers
    return email.utils.parsedate_to_datetime(headers["Date"]).astimezone(dt.UTC).replace(tzinfo=None)


def capture_context(rest: RestClient, task: dict) -> dict:
    """Who we are, when the run started (server clock, UTC), and rows as they were before the run."""
    try:
        started = _server_now_utc(rest.session.base)
    except (urllib.error.URLError, KeyError, TypeError, ValueError):
        started = dt.datetime.now(dt.UTC).replace(tzinfo=None)
    started -= dt.timedelta(seconds=2)
    return {
        "me": rest.raw("/api/auth/me")["id"],
        "started_at_utc": started.isoformat(),
        "snapshot": {s["number"]: _find_by_number(rest, s["entity"], s["number"]) for s in task.get("snapshot", [])},
    }


def persist_then_verify(run_dir: Path, result: dict, verify, *, catch: bool = True):
    """Write result.json (fsync'd) first, and only then run the verifier.

    `verify` is a zero-argument callable returning a Verdict or (Verdict, reason), or None.
    A verifier that raises yields UNEVALUATED unless catch=False.
    """
    _write(run_dir / "result.json", result)  # persisted before any scoring
    if verify is None:
        return Verdict.UNEVALUATED, "no verifier"
    try:
        return normalise(verify())
    except Exception:
        if not catch:
            raise
        return Verdict.UNEVALUATED, "verifier raised:\n" + traceback.format_exc()


def run_one(task: dict, instance: str, root: Path) -> dict:
    run_dir = root / instance / task["id"]
    run_dir.mkdir(parents=True, exist_ok=False)
    _write(run_dir / "task.json", task)

    fixture, context, error, mcp = None, None, None, None
    try:
        session = Session(instance)
        mcp = McpClient(session)
        if task.get("fixture"):
            fixture = FIXTURES[task["fixture"]](mcp)
        _write(run_dir / "fixture.json", fixture)
        context = capture_context(RestClient(session), task)
        _write(run_dir / "context.json", context)

        trace_file = (run_dir / "trace.jsonl").open("x", encoding="utf-8")

        def trace(event):
            trace_file.write(json.dumps(event, default=str) + "\n")
            trace_file.flush()
            os.fsync(trace_file.fileno())

        write_ids = set((fixture or {}).get("write_ids", []))
        interference: list[dict] = []

        def approve(p):
            if p["work_order_id"] not in write_ids:  # harness approves fixture rows only
                return False
            already_edited = any(i["id"] == p["work_order_id"] for i in interference)
            if task.get("interference") == "edit_dates_before_apply" and not already_edited:
                edit = concurrent_edit(McpClient(Session(instance)), p["work_order_id"])
                interference.append(edit)
                _write(run_dir / "interference.json", interference)  # on disk before the agent's write attempt
                trace({"type": "interference", **edit})
            return True

        prompt = task["prompt"].format(**{f"{role}_number": v["number"] for role, v in (fixture or {}).items()
                                          if isinstance(v, dict) and "number" in v})
        agent = ProductionAgent(
            mcp, apply_mode=task.get("mode") == "apply", allowed_write_ids=write_ids, approve=approve,
            escalate_mode=bool(task.get("escalate")), session_title=f"{config.HARNESS_MARKER} task {task['id']}",
            trace=trace, max_steps=task.get("max_steps", 20))
        result = agent.run(prompt)
        trace_file.close()
    except Exception:
        error = traceback.format_exc()
        result = {"run_id": None, "stop_reason": "harness_error", "error": error}
    result["instance"], result["task_id"] = instance, task["id"]

    def verify():
        ctx = VerifyContext(rest=RestClient(Session(instance)), instance=instance, task=task,
                            run_dir=run_dir, fixture=fixture, context=context)
        return _load_verifier(task["verifier"])(ctx)

    if error:
        verdict, reason = persist_then_verify(run_dir, result, None)
        reason = "run failed before verification"
    elif not task.get("verifier"):
        verdict, reason = persist_then_verify(run_dir, result, None)
        reason = "no verifier declared"
    else:
        verdict, reason = persist_then_verify(run_dir, result, verify)
    record = {"task_id": task["id"], "instance": instance, "verdict": verdict.value, "reason": reason,
              "sample": bool(task.get("sample")), "run_id": result.get("run_id"),
              "seconds": result.get("seconds")}
    _write(run_dir / "verdict.json", record)
    if mcp is not None and result.get("escalations"):
        _write(run_dir / "cleanup.json", cleanup_escalations(mcp, result))
    return record


def cleanup_escalations(mcp: McpClient, result: dict) -> dict:
    """After scoring, withdraw escalations the harness caused so no person is left chasing a test."""
    done = {"withdrawn": [], "session_closed": None, "errors": []}
    for esc in result.get("escalations") or []:
        if esc.get("raised") and esc.get("escalation_id"):
            try:
                domain.withdraw_escalation(mcp, esc["escalation_id"], "team04 harness test run: withdrawn after scoring")
                done["withdrawn"].append(esc.get("number"))
            except Exception as e:  # cleanup must never change a verdict
                done["errors"].append(f"{esc.get('number')}: {e}")
    if result.get("agent_session_id"):
        try:
            mcp.call("AgentSession.close.active.closed", {"id": result["agent_session_id"]})
            done["session_closed"] = result["agent_session_id"]
        except Exception as e:
            done["errors"].append(f"session: {e}")
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--instance", choices=sorted(config.INSTANCES) + ["all"], default="all")
    ap.add_argument("--task", action="append", help="task id (repeatable)")
    ap.add_argument("--include-samples", action="store_true")
    args = ap.parse_args()

    tasks = [t for t in load_tasks(args.include_samples) if not args.task or t["id"] in args.task]
    root = _new_run_root(config.ROOT / "runs")
    records = []
    for task in tasks:
        instances = task.get("instances", sorted(config.INSTANCES))
        for instance in instances:
            if args.instance not in ("all", instance):
                continue
            rec = run_one(task, instance, root)
            records.append(rec)
            print(f"{rec['verdict']:12} {instance:10} {task['id']}  {rec['reason'][:100]}")

    scored = [r for r in records if not r["sample"]]
    summary = {"runs": records, "approved": sum(r["verdict"] == "approve" for r in scored),
               "revise": sum(r["verdict"] == "revise" for r in scored),
               "unevaluated": sum(r["verdict"] == "unevaluated" for r in scored), "scored_total": len(scored)}
    if records:
        _write(root / "summary.json", summary)
    print(f"\n{summary['approved']}/{summary['scored_total']} approved "
          f"({summary['unevaluated']} unevaluated, never a pass). Runs in {root}")


if __name__ == "__main__":
    main()
