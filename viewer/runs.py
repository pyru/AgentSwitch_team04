"""Read-only access to harness run output. Nothing in this module writes to disk."""
import json
import re
from pathlib import Path

ROOT_NAME = re.compile(r"\d{8}-\d{6}(-\d{6})?")
IDENT = re.compile(r"[a-z0-9_]+")
RUN_FILES = ("task", "fixture", "context", "result", "verdict", "interference", "cleanup")


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def list_run_roots(base: Path) -> list[dict]:
    """Newest first. A root with no summary.json is still running, or stopped before the end."""
    if not base.is_dir():
        return []
    out = []
    for root in sorted((p for p in base.iterdir() if p.is_dir() and ROOT_NAME.fullmatch(p.name)), reverse=True):
        tasks = []
        for task_dir in sorted(p for p in root.glob("*/*") if p.is_dir()):
            verdict = _load(task_dir / "verdict.json")
            tasks.append({"instance": task_dir.parent.name, "task_id": task_dir.name,
                          "verdict": verdict.get("verdict") if isinstance(verdict, dict) else None})
        summary = _load(root / "summary.json")
        entry = {"name": root.name, "complete": isinstance(summary, dict), "tasks": tasks}
        if entry["complete"]:
            entry.update({k: summary.get(k) for k in ("approved", "revise", "unevaluated", "scored_total")})
        out.append(entry)
    return out


def resolve_task_dir(base: Path, root: str, instance: str, task_id: str, instances: set[str]) -> Path | None:
    # Names are checked against the run layout before any path is built, so a request can never leave base.
    if not (ROOT_NAME.fullmatch(root) and instance in instances and IDENT.fullmatch(task_id)):
        return None
    path = base / root / instance / task_id
    return path if path.is_dir() else None


def read_trace(path: Path, offset: int = 0) -> tuple[list[dict], int]:
    """Events after byte `offset`. A line still being written (no newline yet) is left for the next read."""
    try:
        with path.open("rb") as f:
            f.seek(max(0, offset))
            chunk = f.read()
    except FileNotFoundError:
        return [], offset
    end = chunk.rfind(b"\n") + 1
    events = [json.loads(line) for line in chunk[:end].splitlines() if line.strip()]
    return events, max(0, offset) + end


def load_task_run(task_dir: Path) -> dict:
    run = {name: _load(task_dir / f"{name}.json") for name in RUN_FILES}
    run["trace"] = read_trace(task_dir / "trace.jsonl")[0]
    result, verdict = task_dir / "result.json", task_dir / "verdict.json"
    # The same proof scripts/verify_submission.py asks for: the result was on disk before it was scored.
    run["persisted_before_verdict"] = (result.stat().st_mtime <= verdict.stat().st_mtime
                                       if result.exists() and verdict.exists() else None)
    return run
