# Live Run Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local browser console that starts one selected harness task at a time against a live tenant, shows the agent's steps as they happen, then shows the verdict and its evidence — for a screen-shared graded live demo — and browses past runs.

**Architecture:** A new `viewer/` package: a stdlib `ThreadingHTTPServer` bound to `127.0.0.1`, read-only helpers over `runs/`, and a job runner that starts the *existing* CLI (`python -m harness.runner --task X --instance Y --runs-dir runs/demo`) as a subprocess. The page polls the server once a second and tails `trace.jsonl`, which the runner already fsyncs per event. The agent, harness fixtures, verifiers and cleanup are unchanged; the only harness change is an optional `--runs-dir` flag so partial demo runs never become the run `scripts/verify_submission.py` grades.

**Tech Stack:** Python 3.11 stdlib only (`http.server`, `subprocess`, `threading`, `json`, `re`), one static HTML page with vanilla JavaScript, pytest in `tests_ai/`.

**Spec:** No separate spec. Decisions were settled in the 2026-09-30 feasibility review (Opus with Fable + Astra advisors) and are recorded under "Decisions" below.

## Decisions

- **Who drives:** the team, screen-sharing. Graders never reach the server, so it binds to `127.0.0.1` only and credentials never leave this machine.
- **What runs live:** selected harness tasks, one at a time. Full-suite runs stay on the CLI.
- **Out of scope:** multi-turn chat (the agent is single-turn: `prod_agent/agent.py:355-357`), a free-text "ask the agent" box, a stop button, `--apply`/`--escalate` for ad-hoc requests, hosting.
- **No stop button, on purpose:** killing a run mid-way skips `cleanup_escalations` (`harness/runner.py:187-188`) and can leave a real escalation assigned to a real person.
- **Page behaviour is checked by hand, not by an automated browser test:** that would need a JavaScript test toolchain
  this plan keeps out. Races are prevented structurally instead (each response is drawn only if its view is still on
  screen), and Task 5/Task 7 list the manual checks. Added after the plan review by Astra (2026-09-30).
- **Demo output goes to `runs/demo/`:** the checker grades the newest `runs/2026*` root (`scripts/verify_submission.py:65-87`); a one-task run there would fail "all approved" and the refusal check. `runs/demo/` does not match that glob and is already git-ignored by `runs/`.

## Global Constraints

- No new dependencies. Nothing added to `requirements.txt`. No Node toolchain (a `node_modules/` tree would be swept by the checker's secret scan, `scripts/verify_submission.py:146-152`).
- Never write to `tests/`. New tests go in `tests_ai/`, with the folder's docstring header convention.
- Never modify, delete or regenerate committed run dirs (`runs/20260916-114054`, `runs/20260917-100224`, `runs/20260917-110938`). The viewer only reads them.
- The server never loads `.env`; only the runner subprocess does (it inherits the environment and reads `.env` itself).
- Subprocesses get an argument list, never a shell string. Task ids and instances come only from the task-file allowlist.
- Code style (AGENTS.md): double quotes, ~120-char lines, PEP 604 unions, builtin generics, plain dicts, stdlib → third-party → local imports, comments explain *why*. No `black`/`ruff format`.
- Commit messages: sentence-case imperative like the existing history ("Give every run its own directory…"); no AI attribution.
- **Running `python -m harness.runner` or clicking "Start run" hits live tenants: ask Pravin first, every time.** All tests below are offline.

## File Structure

| File | Responsibility |
|---|---|
| `harness/runner.py` (modify) | Add `--runs-dir`; fix the docstring's wrong example task id |
| `viewer/__init__.py` (create) | Package marker, empty |
| `viewer/runs.py` (create) | Read-only: list run roots, resolve a task dir safely, load one task run, tail a trace |
| `viewer/jobs.py` (create) | Validate a start request, run one harness subprocess at a time, report status |
| `viewer/server.py` (create) | HTTP routes, host/origin/token checks |
| `viewer/static/index.html` (create) | The page |
| `viewer/__main__.py` (create) | `python -m viewer [--port]` |
| `tests_ai/test_runs_dir_flag.py` (create) | `--runs-dir` behaviour |
| `tests_ai/test_viewer.py` (create) | `runs.py`, `jobs.py`, `server.py` |
| `README.md`, `AGENTS.md` (modify) | Usage, demo runbook, live-system warning |

---

### Task 1: `--runs-dir` flag on the harness runner

**Files:**
- Modify: `harness/runner.py:1-9` (docstring), `harness/runner.py:211-219` (`main`)
- Test: `tests_ai/test_runs_dir_flag.py`

**Interfaces:**
- Produces: `python -m harness.runner --runs-dir PATH` creates the run root at `PATH/<timestamp>`; default stays `config.ROOT / "runs"`.

- [ ] **Step 1: Write the failing tests**

```python
"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-09-30).

Ungraded. Prove --runs-dir moves a run root without changing the default the submission checker reads.
The graded, hand-written tests live in tests/.
"""
import sys

from harness import runner
from prod_agent import config


def _record(task, instance, root):
    return {"task_id": task["id"], "instance": instance, "verdict": "approve", "reason": "ok",
            "sample": False, "run_id": "r1", "seconds": 1.0}


def test_runs_dir_puts_the_run_root_and_summary_under_the_given_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "load_tasks", lambda include_samples: [{"id": "refuse_x", "instances": ["suryodaya"]}])
    monkeypatch.setattr(runner, "run_one", _record)
    demo = tmp_path / "demo"
    monkeypatch.setattr(sys, "argv", ["runner", "--task", "refuse_x", "--runs-dir", str(demo)])

    runner.main()

    roots = [p for p in demo.iterdir() if p.is_dir()]
    assert len(roots) == 1
    assert (roots[0] / "summary.json").exists()


def test_default_runs_dir_is_still_the_directory_the_checker_reads(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setattr(runner, "load_tasks", lambda include_samples: [])
    monkeypatch.setattr(runner, "_new_run_root", lambda base: seen.append(base) or tmp_path)
    monkeypatch.setattr(sys, "argv", ["runner"])

    runner.main()

    assert seen == [config.ROOT / "runs"]
```

- [ ] **Step 2: Run to verify the first test fails**

Run: `python -m pytest tests_ai/test_runs_dir_flag.py -v`
Expected: `test_runs_dir_puts…` FAILS with `SystemExit: 2` (argparse: unrecognized arguments: --runs-dir). The default test passes already — it is a guard against the flag changing the default.

- [ ] **Step 3: Implement**

In `main()`:

```python
    ap.add_argument("--include-samples", action="store_true")
    # Partial runs (a live demo of a few tasks) go elsewhere: the checker grades the newest runs/2026* root.
    ap.add_argument("--runs-dir", type=Path, default=config.ROOT / "runs")
    args = ap.parse_args()

    tasks = [t for t in load_tasks(args.include_samples) if not args.task or t["id"] in args.task]
    root = _new_run_root(args.runs_dir)
```

Replace the docstring's usage block (the example id `refuse_unknown_wo` does not exist):

```python
"""Run the task set.

    python -m harness.runner                         # all tasks, all instances they declare
    python -m harness.runner --instance keystone --task refuse_unknown_work_order
    python -m harness.runner --include-samples
    python -m harness.runner --task why_late_wo48_subcontract --runs-dir runs/demo   # kept out of the checker's view

Order per task: task.json -> fixture.json -> trace.jsonl (streamed) -> result.json, all fsync'd,
and only then the verifier runs and writes verdict.json.
"""
```

- [ ] **Step 4: Run to verify both pass**

Run: `python -m pytest tests_ai/test_runs_dir_flag.py tests_ai/test_run_dirs.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add harness/runner.py tests_ai/test_runs_dir_flag.py
git commit -m "Let a partial harness run write outside the directory the checker grades"
```

---

### Task 2: Read-only run access (`viewer/runs.py`)

**Files:**
- Create: `viewer/__init__.py` (empty), `viewer/runs.py`
- Test: `tests_ai/test_viewer.py` (created here; Tasks 3–4 append to it)

**Interfaces:**
- Produces:
  - `ROOT_NAME: re.Pattern` — run root names, `\d{8}-\d{6}(-\d{6})?`
  - `list_run_roots(base: Path) -> list[dict]` — newest first; each `{"name", "complete": bool, "tasks": [{"instance", "task_id", "verdict": str | None}], and when complete "approved", "revise", "unevaluated", "scored_total"}`
  - `resolve_task_dir(base: Path, root: str, instance: str, task_id: str, instances: set[str]) -> Path | None`
  - `load_task_run(task_dir: Path) -> dict` — keys `task, fixture, context, result, verdict, interference, cleanup` (parsed JSON or `None`), `trace: list[dict]`, `persisted_before_verdict: bool | None`
  - `read_trace(path: Path, offset: int = 0) -> tuple[list[dict], int]`

- [ ] **Step 1: Write the failing tests**

```python
"""AI-WRITTEN REGRESSION TESTS (written by Claude, 2026-09-30).

Ungraded. Cover the local run console (viewer/) without a network, a model or a live tenant.
The graded, hand-written tests live in tests/.
"""
import json
import os

import pytest

from viewer import runs

ROOT = "20260930-101500-000001"


def _task_dir(base, root, instance, task, verdict=None, trace=()):
    d = base / root / instance / task
    d.mkdir(parents=True)
    (d / "result.json").write_text(json.dumps({"run_id": "r1"}), encoding="utf-8")
    (d / "trace.jsonl").write_text("".join(json.dumps(e) + "\n" for e in trace), encoding="utf-8")
    if verdict:
        (d / "verdict.json").write_text(json.dumps({"verdict": verdict, "reason": "because"}), encoding="utf-8")
    return d


def test_task_without_a_verdict_is_listed_as_unscored_never_approved(tmp_path):
    _task_dir(tmp_path, ROOT, "suryodaya", "refuse_x", verdict="approve")
    _task_dir(tmp_path, ROOT, "keystone", "refuse_x")

    [root] = runs.list_run_roots(tmp_path)

    assert root["complete"] is False
    assert {t["instance"]: t["verdict"] for t in root["tasks"]} == {"keystone": None, "suryodaya": "approve"}


def test_listing_skips_adhoc_demo_and_other_folders_and_reads_the_summary(tmp_path):
    for name in ("adhoc", "demo", "notes"):
        (tmp_path / name).mkdir()
    full = tmp_path / "20260917-110938"
    full.mkdir()
    (full / "summary.json").write_text(json.dumps({"approved": 30, "revise": 0, "unevaluated": 0,
                                                   "scored_total": 30}), encoding="utf-8")

    [root] = runs.list_run_roots(tmp_path)

    assert root["name"] == "20260917-110938"
    assert root["complete"] is True
    assert (root["approved"], root["scored_total"]) == (30, 30)


def test_newest_run_is_listed_first(tmp_path):
    for name in ("20260916-114054", ROOT):
        (tmp_path / name).mkdir()

    assert [r["name"] for r in runs.list_run_roots(tmp_path)] == [ROOT, "20260916-114054"]


def test_missing_base_lists_nothing(tmp_path):
    assert runs.list_run_roots(tmp_path / "demo") == []


def test_trace_read_leaves_a_half_written_line_for_the_next_read(tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_bytes(b'{"type": "start"}\n{"type": "ll')

    events, offset = runs.read_trace(path)
    assert events == [{"type": "start"}]

    with path.open("ab") as f:
        f.write(b'm", "step": 0}\n')
    events, offset = runs.read_trace(path, offset)
    assert events == [{"type": "llm", "step": 0}]
    assert runs.read_trace(path, offset) == ([], offset)


def test_missing_trace_reads_as_no_events(tmp_path):
    assert runs.read_trace(tmp_path / "trace.jsonl", 5) == ([], 5)


@pytest.mark.parametrize("root,instance,task", [
    ("../etc", "suryodaya", "refuse_x"),
    (ROOT, "elsewhere", "refuse_x"),
    (ROOT, "suryodaya", "../../.env"),
    (ROOT, "suryodaya", "missing_task"),
])
def test_task_dir_refuses_anything_outside_the_run_layout(tmp_path, root, instance, task):
    _task_dir(tmp_path, ROOT, "suryodaya", "refuse_x")

    assert runs.resolve_task_dir(tmp_path, root, instance, task, {"suryodaya", "keystone"}) is None


def test_task_dir_resolves_a_real_run(tmp_path):
    d = _task_dir(tmp_path, ROOT, "suryodaya", "refuse_x")

    assert runs.resolve_task_dir(tmp_path, ROOT, "suryodaya", "refuse_x", {"suryodaya", "keystone"}) == d


def test_task_run_reports_the_same_write_ordering_the_checker_requires(tmp_path):
    d = _task_dir(tmp_path, ROOT, "suryodaya", "refuse_x", verdict="approve", trace=[{"type": "start"}])
    os.utime(d / "result.json", (1000, 1000))
    os.utime(d / "verdict.json", (2000, 2000))

    run = runs.load_task_run(d)
    assert run["persisted_before_verdict"] is True
    assert run["verdict"]["verdict"] == "approve"
    assert run["trace"] == [{"type": "start"}]
    assert run["fixture"] is None

    os.utime(d / "result.json", (3000, 3000))
    assert runs.load_task_run(d)["persisted_before_verdict"] is False
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests_ai/test_viewer.py -v`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'viewer'`.

- [ ] **Step 3: Implement** — create empty `viewer/__init__.py`, then `viewer/runs.py`:

```python
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
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests_ai/test_viewer.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add viewer/__init__.py viewer/runs.py tests_ai/test_viewer.py
git commit -m "Read harness runs for a local console without writing to them"
```

---

### Task 3: One harness run at a time (`viewer/jobs.py`)

**Files:**
- Create: `viewer/jobs.py`
- Test: append to `tests_ai/test_viewer.py`

**Interfaces:**
- Consumes: `harness.runner.load_tasks(include_samples: bool) -> list[dict]` (task dicts with `id`, optional `instances`); the Task 1 `--runs-dir` flag.
- Produces:
  - `class JobError(Exception)`
  - `JobRunner(tasks: list[dict], demo_base: Path, popen=subprocess.Popen)`
  - `JobRunner.tasks: dict[str, dict]` (by id), `JobRunner.instances_for(task_id: str) -> list[str]`
  - `JobRunner.start(task_id: str, instance: str, confirm: str) -> dict` — raises `JobError`
  - `JobRunner.status() -> dict | None` — `{"job_id": int, "task_id", "instance", "started", "running": bool, "exit_code": int | None, "run_root": str | None, "log": str}`. `job_id` counts up from 1 per console process; the page uses it to tell one run from the next.

- [ ] **Step 1: Write the failing tests** (append; add `import sys`, `from pathlib import Path`, `from types import SimpleNamespace` to the imports, and `from prod_agent import config`, `from viewer.jobs import JobError, JobRunner` after `from viewer import runs`)

```python
TASKS = [{"id": "refuse_x", "instances": ["keystone", "suryodaya"]}, {"id": "why_late", "instances": ["suryodaya"]}]


def fake_popen(procs):
    """Stands in for subprocess.Popen: records the call and creates the run root the real runner would."""
    def popen(cmd, **kwargs):
        proc = SimpleNamespace(cmd=cmd, kwargs=kwargs, code=None)
        proc.poll = lambda: proc.code
        Path(cmd[cmd.index("--runs-dir") + 1], f"20260930-12000{len(procs)}-000001").mkdir()
        procs.append(proc)
        return proc
    return popen


def test_start_runs_the_harness_cli_into_the_demo_directory(tmp_path):
    procs, demo = [], tmp_path / "demo"
    jobs = JobRunner(TASKS, demo, popen=fake_popen(procs))

    status = jobs.start("refuse_x", "keystone", "keystone/refuse_x")

    [proc] = procs
    assert proc.cmd == [sys.executable, "-m", "harness.runner", "--task", "refuse_x", "--instance", "keystone",
                        "--runs-dir", str(demo)]
    assert proc.kwargs["cwd"] == config.ROOT
    assert proc.kwargs["start_new_session"] is True
    assert status["running"] is True
    assert status["run_root"] == "20260930-120000-000001"


@pytest.mark.parametrize("task,instance,confirm", [
    ("not_a_task", "suryodaya", "suryodaya/not_a_task"),
    ("why_late", "keystone", "keystone/why_late"),
    ("refuse_x", "suryodaya", "yes"),
    ("refuse_x", "suryodaya", ""),
])
def test_start_refuses_anything_not_on_the_allowlist_or_not_confirmed(tmp_path, task, instance, confirm):
    procs = []
    jobs = JobRunner(TASKS, tmp_path / "demo", popen=fake_popen(procs))

    with pytest.raises(JobError):
        jobs.start(task, instance, confirm)
    assert procs == []


def test_only_one_run_at_a_time(tmp_path):
    procs = []
    jobs = JobRunner(TASKS, tmp_path / "demo", popen=fake_popen(procs))
    jobs.start("refuse_x", "suryodaya", "suryodaya/refuse_x")

    with pytest.raises(JobError, match="in progress"):
        jobs.start("why_late", "suryodaya", "suryodaya/why_late")

    procs[0].code = 0
    assert jobs.status()["exit_code"] == 0
    jobs.start("why_late", "suryodaya", "suryodaya/why_late")
    assert len(procs) == 2
    assert jobs.status()["run_root"] == "20260930-120001-000001"
    assert jobs.status()["job_id"] == 2


def test_no_status_before_any_run(tmp_path):
    assert JobRunner(TASKS, tmp_path / "demo").status() is None


def test_task_without_declared_instances_runs_on_every_instance(tmp_path):
    jobs = JobRunner([{"id": "plain"}], tmp_path / "demo")
    assert jobs.instances_for("plain") == sorted(config.INSTANCES)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests_ai/test_viewer.py -v`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'viewer.jobs'`.

- [ ] **Step 3: Implement** `viewer/jobs.py`:

```python
"""One harness run at a time, started through the same CLI a person would type."""
import datetime as dt
import subprocess
import sys
import threading
from pathlib import Path

from prod_agent import config


class JobError(Exception):
    pass


class JobRunner:
    def __init__(self, tasks: list[dict], demo_base: Path, popen=subprocess.Popen):
        self.tasks = {t["id"]: t for t in tasks}
        self.demo_base = demo_base
        self._popen = popen
        self._lock = threading.Lock()
        self._next_id = 0
        self.current: dict | None = None

    def instances_for(self, task_id: str) -> list[str]:
        return self.tasks[task_id].get("instances", sorted(config.INSTANCES))

    def start(self, task_id: str, instance: str, confirm: str) -> dict:
        if task_id not in self.tasks:
            raise JobError(f"unknown task {task_id!r}")
        if instance not in self.instances_for(task_id):
            raise JobError(f"task {task_id} does not run on {instance!r}")
        if confirm != f"{instance}/{task_id}":
            raise JobError("confirmation text does not match")
        with self._lock:
            # Two runs share the fixture work orders on the tenant and would trip changed_underneath on each other.
            if self.current is not None and self.current["proc"].poll() is None:
                raise JobError("a run is already in progress")
            self.demo_base.mkdir(parents=True, exist_ok=True)
            before = {p.name for p in self.demo_base.iterdir()}
            started = dt.datetime.now()
            log_path = self.demo_base / f"console-{started:%Y%m%d-%H%M%S}.log"
            # An argument list, never a shell string: task and instance only ever come from the allowlist above.
            cmd = [sys.executable, "-m", "harness.runner", "--task", task_id, "--instance", instance,
                   "--runs-dir", str(self.demo_base)]
            with log_path.open("w", encoding="utf-8") as log:
                # A new session keeps Ctrl-C on the console from killing the run before it withdraws its escalations.
                proc = self._popen(cmd, cwd=config.ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
            self._next_id += 1
            self.current = {"job_id": self._next_id, "task_id": task_id, "instance": instance, "proc": proc,
                            "before": before,
                            "log": str(log_path), "started": started.isoformat(timespec="seconds")}
        return self.status()

    def status(self) -> dict | None:
        if self.current is None:
            return None
        cur = self.current
        new = sorted(p.name for p in self.demo_base.iterdir() if p.is_dir() and p.name not in cur["before"])
        code = cur["proc"].poll()
        return {"job_id": cur["job_id"], "task_id": cur["task_id"], "instance": cur["instance"],
                "started": cur["started"],
                "running": code is None, "exit_code": code, "run_root": new[-1] if new else None,
                "log": cur["log"]}
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests_ai/test_viewer.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add viewer/jobs.py tests_ai/test_viewer.py
git commit -m "Start one confirmed harness task at a time from the console"
```

---

### Task 4: HTTP server (`viewer/server.py`)

**Files:**
- Create: `viewer/server.py`
- Test: append to `tests_ai/test_viewer.py`

**Interfaces:**
- Consumes: everything from Tasks 2–3.
- Produces: `make_server(port: int, bases: dict[str, Path], jobs: JobRunner) -> ThreadingHTTPServer` with a `.token: str` attribute. `port=0` picks a free port. Routes:
  - `GET /` — `viewer/static/index.html` with `{{TOKEN}}` replaced
  - `GET /api/tasks` — `[{"id", "instances", "mode", "escalate", "fixture"}]`
  - `GET /api/runs?base=committed|demo` — `list_run_roots`
  - `GET /api/run?base=&root=&instance=&task=` — `load_task_run`
  - `GET /api/trace?base=&root=&instance=&task=&offset=` — `{"events", "offset"}`
  - `GET /api/jobs/current` — `JobRunner.status()`
  - `POST /api/jobs` with JSON `{"task_id", "instance", "confirm"}` and header `X-Console-Token` — `JobRunner.start`
  - Every request with a `Host` other than `127.0.0.1:<port>` / `localhost:<port>` → 403. POST with a foreign `Origin` or wrong token → 403. `JobError`/bad input → 400. Unknown path or unresolved run → 404.

- [ ] **Step 1: Write the failing tests** (append; add `import threading`, `import urllib.error`, `import urllib.request` to the imports and `from viewer.server import make_server` after the `viewer.jobs` import). Task 5 creates the page; until then create a one-line stub `viewer/static/index.html` containing `<script>const TOKEN = "{{TOKEN}}";</script>` so `GET /` has something to serve.

```python
@pytest.fixture
def console(tmp_path):
    committed = tmp_path / "runs"
    _task_dir(committed, ROOT, "suryodaya", "refuse_x", verdict="approve", trace=[{"type": "start"}])
    procs = []
    jobs = JobRunner(TASKS, tmp_path / "demo", popen=fake_popen(procs))
    server = make_server(0, {"committed": committed, "demo": tmp_path / "demo"}, jobs)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    server.procs = procs
    yield server
    server.shutdown()
    server.server_close()


def _call(server, path, body=None, headers=None):
    url = f"http://127.0.0.1:{server.server_address[1]}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")


def test_page_carries_the_session_token(console):
    status, page = _call(console, "/")
    assert status == 200
    assert console.token in page and "{{TOKEN}}" not in page


def test_past_runs_and_one_task_run_are_served(console):
    status, body = _call(console, "/api/runs?base=committed")
    assert status == 200
    assert json.loads(body)[0]["tasks"][0]["verdict"] == "approve"

    status, body = _call(console, f"/api/run?base=committed&root={ROOT}&instance=suryodaya&task=refuse_x")
    assert status == 200
    assert json.loads(body)["trace"] == [{"type": "start"}]


def test_a_path_outside_the_run_layout_is_not_found(console):
    status, _ = _call(console, "/api/run?base=committed&root=..&instance=suryodaya&task=refuse_x")
    assert status == 404


def test_a_foreign_host_header_is_refused(console):
    status, _ = _call(console, "/api/tasks", headers={"Host": "evil.test"})
    assert status == 403


def test_starting_a_run_needs_the_token_and_a_local_origin(console):
    body = {"task_id": "refuse_x", "instance": "suryodaya", "confirm": "suryodaya/refuse_x"}
    assert _call(console, "/api/jobs", body)[0] == 403
    assert _call(console, "/api/jobs", body, {"X-Console-Token": console.token, "Origin": "https://evil.test"})[0] == 403
    assert console.procs == []


def test_a_confirmed_start_runs_once_and_a_mismatched_one_is_refused(console):
    headers = {"X-Console-Token": console.token, "Content-Type": "application/json"}
    bad = {"task_id": "refuse_x", "instance": "suryodaya", "confirm": "yes"}
    assert _call(console, "/api/jobs", bad, headers)[0] == 400

    good = dict(bad, confirm="suryodaya/refuse_x")
    status, body = _call(console, "/api/jobs", good, headers)
    assert status == 200
    assert json.loads(body)["running"] is True
    assert len(console.procs) == 1
    assert json.loads(_call(console, "/api/jobs/current")[1])["task_id"] == "refuse_x"
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests_ai/test_viewer.py -v`
Expected: collection ERROR, `ModuleNotFoundError: No module named 'viewer.server'`.

- [ ] **Step 3: Implement** `viewer/server.py`:

```python
"""Local run console: browse harness runs and start one selected task at a time.

Binds to 127.0.0.1 only. Starting a run executes python -m harness.runner against a live tenant, exactly as
the CLI does, so AGENTS.md's "ask before running" applies to every click.
"""
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from prod_agent import config

from . import runs
from .jobs import JobError, JobRunner

HOST = "127.0.0.1"
STATIC = Path(__file__).parent / "static"


def make_server(port: int, bases: dict[str, Path], jobs: JobRunner) -> ThreadingHTTPServer:
    token = secrets.token_hex(16)
    instances = set(config.INSTANCES)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # the page polls every second; keep the terminal readable
            pass

        def _send(self, status: int, body, content_type: str = "application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _local(self) -> set[str]:
            port = self.server.server_address[1]
            return {f"127.0.0.1:{port}", f"localhost:{port}"}

        def do_GET(self):
            # Another site can reach 127.0.0.1 through DNS rebinding; the Host header is what it cannot choose.
            if self.headers.get("Host") not in self._local():
                return self._send(403, {"error": "forbidden host"})
            url = urlparse(self.path)
            q = {k: v[0] for k, v in parse_qs(url.query).items()}
            try:
                if url.path == "/":
                    page = (STATIC / "index.html").read_text(encoding="utf-8").replace("{{TOKEN}}", token)
                    return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
                if url.path == "/api/tasks":
                    return self._send(200, [{"id": t["id"], "instances": jobs.instances_for(t["id"]),
                                             "mode": t.get("mode"), "escalate": bool(t.get("escalate")),
                                             "fixture": t.get("fixture")} for t in jobs.tasks.values()])
                if url.path == "/api/jobs/current":
                    return self._send(200, jobs.status())
                if url.path == "/api/runs" and q.get("base") in bases:
                    return self._send(200, runs.list_run_roots(bases[q["base"]]))
                if url.path in ("/api/run", "/api/trace") and q.get("base") in bases:
                    task_dir = runs.resolve_task_dir(bases[q["base"]], q.get("root", ""), q.get("instance", ""),
                                                     q.get("task", ""), instances)
                    if task_dir is not None and url.path == "/api/run":
                        return self._send(200, runs.load_task_run(task_dir))
                    if task_dir is not None:
                        events, offset = runs.read_trace(task_dir / "trace.jsonl", int(q.get("offset", "0")))
                        return self._send(200, {"events": events, "offset": offset})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            origin = self.headers.get("Origin")
            if self.headers.get("Host") not in self._local() \
                    or (origin is not None and origin.removeprefix("http://") not in self._local()) \
                    or not secrets.compare_digest(self.headers.get("X-Console-Token", ""), token):
                return self._send(403, {"error": "forbidden"})
            if urlparse(self.path).path != "/api/jobs":
                return self._send(404, {"error": "not found"})
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
                if not isinstance(body, dict):
                    raise ValueError("expected a JSON object")
                return self._send(200, jobs.start(str(body.get("task_id", "")), str(body.get("instance", "")),
                                                  str(body.get("confirm", ""))))
            except (JobError, ValueError) as e:
                return self._send(400, {"error": str(e)})

    server = ThreadingHTTPServer((HOST, port), Handler)
    server.token = token
    return server
```

- [ ] **Step 4: Run to verify they pass**

Run: `python -m pytest tests_ai/test_viewer.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add viewer/server.py viewer/static/index.html tests_ai/test_viewer.py
git commit -m "Serve the console on localhost only, with a token on the one route that starts a run"
```

---

### Task 5: The page and the entry point

**Files:**
- Create: `viewer/static/index.html` (replaces the Task 4 stub), `viewer/__main__.py`

**Interfaces:**
- Consumes: the Task 4 routes; `harness.runner.load_tasks`.
- Produces: `python -m viewer [--port 8765]`.

- [ ] **Step 1: Write `viewer/__main__.py`**

```python
"""python -m viewer [--port 8765]: local run console for the harness. See viewer/server.py."""
import argparse

from harness.runner import load_tasks
from prod_agent import config

from .jobs import JobRunner
from .server import HOST, make_server


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    runs_dir = config.ROOT / "runs"
    jobs = JobRunner(load_tasks(include_samples=False), runs_dir / "demo")
    server = make_server(args.port, {"committed": runs_dir, "demo": runs_dir / "demo"}, jobs)
    print(f"Console on http://{HOST}:{args.port}  (Ctrl-C stops the console; a run in progress finishes on its own)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `viewer/static/index.html`.** All run data is inserted with `textContent`, never `innerHTML`, because trace text comes from the model and the tenant. Three behaviours matter for a live demo and are built in: responses for a view no longer on screen are dropped (`view`/`follow` identity); errors are visible (setup failures in `result.error`, the end event's `error`, tool errors, refused starts, a lost server connection); and a page refresh during a run re-attaches to it.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>team04 run console</title>
<style>
:root { --bg: #fbfbfa; --fg: #1b1b1b; --muted: #6b6b6b; --line: #dcdcd8; --panel: #f2f2ef;
        --ok: #1a7f4b; --bad: #b3261e; --tool: #8a5a00; --llm: #3e63c4; }
@media (prefers-color-scheme: dark) {
  :root { --bg: #151515; --fg: #ececec; --muted: #9b9b9b; --line: #333; --panel: #1e1e1e;
          --ok: #5cc28b; --bad: #f28b82; --tool: #e0b04a; --llm: #8fa8ff; }
}
body { margin: 0; background: var(--bg); color: var(--fg); font: 15px/1.45 system-ui, sans-serif; }
main { display: grid; grid-template-columns: 340px 1fr; gap: 16px; padding: 16px; max-width: 1400px; margin: auto; }
section { background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px; margin-bottom: 16px; }
h2 { font-size: 13px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); margin: 0 0 8px; }
select, input, button { font: inherit; width: 100%; margin: 4px 0; padding: 6px; box-sizing: border-box; }
ul { list-style: none; padding-left: 0; } ul ul { padding-left: 12px; font-size: 13px; }
ul ul li { cursor: pointer; }
.muted { color: var(--muted); font-size: 13px; }
.approve { color: var(--ok); } .revise, .unevaluated { color: var(--bad); }
.ev { border-left: 3px solid var(--line); padding: 4px 8px; margin: 6px 0; white-space: pre-wrap;
      word-break: break-word; font: 13px/1.4 ui-monospace, monospace; }
.ev.llm { border-color: var(--llm); } .ev.tool { border-color: var(--tool); }
.ev.end { border-color: var(--ok); } .ev.exception { border-color: var(--bad); }
.error { color: var(--bad); white-space: pre-wrap; }
details pre { white-space: pre-wrap; word-break: break-word; margin: 4px 0 0; }
#conn { background: var(--bad); color: var(--bg); padding: 8px 16px; margin: 0; }
@media (max-width: 800px) { main { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<p id="conn" hidden>Disconnected from the console server. Retrying every second.</p>
<main>
  <div>
    <section>
      <h2>Run a task live</h2>
      <select id="task"></select>
      <select id="instance"></select>
      <p id="task-info" class="muted"></p>
      <label class="muted">Type <code id="confirm-hint"></code> to confirm. This writes to the live tenant.
        <input id="confirm" autocomplete="off"></label>
      <button id="start">Start run</button>
      <p id="job" class="muted"></p>
      <button id="follow" hidden>Follow current run</button>
    </section>
    <section>
      <h2>Past runs</h2>
      <select id="base">
        <option value="committed">Full runs (runs/)</option>
        <option value="demo">Demo runs (runs/demo/)</option>
      </select>
      <ul id="runs"></ul>
    </section>
  </div>
  <section>
    <h2 id="detail-title">Select a run</h2>
    <div id="verdict"></div>
    <div id="events"></div>
  </section>
</main>
<script>
const TOKEN = "{{TOKEN}}";
const $ = id => document.getElementById(id);
let tasks = [];
// Every change of what the detail pane shows replaces `follow` (or bumps `view` for history), and a response
// is drawn only if its view is still the one on screen. Without this, a slow poll can paint a live run's
// steps into a past run that was clicked meanwhile.
let view = 0;
let follow = null;  // {jobId, offset} while the detail pane follows a live run

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}
async function get(url) {
  const r = await fetch(url);  // a network failure throws a TypeError with no status
  if (!r.ok) {
    const err = new Error((await r.json().catch(() => ({}))).error || String(r.status));
    err.status = r.status;
    throw err;
  }
  return r.json();
}
const q = params => new URLSearchParams(params).toString();
const parsed = s => { try { return JSON.parse(s); } catch { return s; } };

function setConn(ok) {
  $("conn").hidden = ok;
}
function details(label, value) {
  const d = el("details");
  d.append(el("summary", "", label), el("pre", "", JSON.stringify(value, null, 1)));
  return d;
}
function eventNode(ev) {
  const box = el("div", "ev " + ev.type);
  if (ev.type === "start") {
    box.append(el("div", "", `start  ${ev.instance}  ${ev.provider || ""} ${ev.model}\n${ev.request}`));
  } else if (ev.type === "llm") {
    box.append(el("div", "", ev.tool_calls.length
      ? `step ${ev.step}  model calls: ${ev.tool_calls.map(c => c.name).join(", ")}`
      : `step ${ev.step}  model answers:\n${ev.content || ""}`));
  } else if (ev.type === "tool") {
    box.append(el("div", ev.error ? "error" : "", `step ${ev.step}  ${ev.name}  ${ev.seconds}s`
      + (ev.error ? `  ERROR ${ev.error}` : "")));
    box.append(details("arguments", parsed(ev.arguments)), details("result", ev.result));
  } else if (ev.type === "end") {
    box.append(el("div", "", `end  ${ev.stop_reason}`));
    if (ev.error) box.append(el("pre", "error", ev.error));
    box.append(details("finding", ev.finding));
  } else if (ev.type === "exception") {
    box.append(el("pre", "error", `${ev.tool}: ${ev.traceback}`));
  } else {
    box.append(details(ev.type, ev));
  }
  return box;
}
function addEvents(events) {
  for (const ev of events) $("events").append(eventNode(ev));
}
function showVerdict(run) {
  const box = $("verdict"), v = run.verdict;
  box.replaceChildren(el("p", v ? v.verdict : "unevaluated",
    v ? `${v.verdict}: ${v.reason}` : "No verdict: not scored, never a pass."));
  box.append(el("p", "muted", `result.json on disk before verdict.json: ${run.persisted_before_verdict ?? "n/a"}`));
  // A setup failure (bad credentials, tenant down) still exits 0; its cause is only in result.error.
  if (run.result && run.result.error) box.append(el("pre", "error", run.result.error));
  if (run.cleanup && run.cleanup.errors && run.cleanup.errors.length) {
    box.append(el("p", "error", "Cleanup errors: an escalation may still be open. Check it by hand."));
  }
  for (const k of ["interference", "cleanup"]) {
    if (run[k]) box.append(details(k, run[k]));
  }
}
async function showRun(base, root, instance, task) {
  follow = null;
  const mine = ++view;
  try {
    const run = await get("/api/run?" + q({base, root, instance, task}));
    if (mine !== view) return;
    $("detail-title").textContent = `${root} / ${instance} / ${task}`;
    $("events").replaceChildren();
    addEvents(run.trace);
    showVerdict(run);
  } catch (e) {
    if (mine === view) $("verdict").replaceChildren(el("p", "error", `Could not load this run: ${e.message}`));
  }
}
async function loadRuns() {
  const base = $("base").value, list = $("runs");
  let roots;
  try {
    roots = await get("/api/runs?" + q({base}));
  } catch (e) {
    list.replaceChildren(el("li", "error", `Could not list runs: ${e.message}`));
    return;
  }
  list.replaceChildren();
  for (const r of roots) {
    const li = el("li", "", r.complete ? `${r.name}  ${r.approved}/${r.scored_total} approved` : `${r.name}  incomplete`);
    const ul = el("ul");
    for (const t of r.tasks) {
      const item = el("li", t.verdict || "unevaluated", `${t.verdict || "no verdict"}  ${t.instance}  ${t.task_id}`);
      item.onclick = () => showRun(base, r.name, t.instance, t.task_id);
      ul.append(item);
    }
    li.append(ul);
    list.append(li);
  }
}
function updateHint() { $("confirm-hint").textContent = `${$("instance").value}/${$("task").value}`; }
function fillInstances() {
  const t = tasks.find(t => t.id === $("task").value);
  $("instance").replaceChildren(...t.instances.map(i => el("option", "", i)));
  $("task-info").textContent = `mode ${t.mode || "dry_run"}` + (t.fixture ? ", writes fixture work orders" : "")
    + (t.escalate ? ", may escalate (withdrawn after scoring)" : "");
  updateHint();
}
function attach(job) {
  ++view;
  follow = {jobId: job.job_id, offset: 0};
  $("events").replaceChildren();
  $("verdict").replaceChildren();
  $("detail-title").textContent = `live: ${job.instance} / ${job.task_id}`;
}
async function start() {
  const body = {task_id: $("task").value, instance: $("instance").value, confirm: $("confirm").value};
  let r, data;
  try {
    r = await fetch("/api/jobs", {method: "POST", body: JSON.stringify(body),
      headers: {"Content-Type": "application/json", "X-Console-Token": TOKEN}});
    data = await r.json();
  } catch (e) {
    $("job").textContent = `Could not reach the console server: ${e.message}`;
    return;
  }
  if (!r.ok) { $("job").textContent = `Refused: ${data.error}`; return; }
  $("confirm").value = "";
  attach(data);
}
async function followCurrent() {
  try {
    const job = await get("/api/jobs/current");
    if (job && job.running) attach(job);
  } catch (e) {
    setConn(false);
  }
}
async function poll() {
  let job;
  try {
    job = await get("/api/jobs/current");
    setConn(true);
  } catch (e) {
    setConn(false);
    setTimeout(poll, 1000);
    return;
  }
  $("job").textContent = !job ? "" : `${job.task_id} on ${job.instance}: `
    + (job.running ? "running" : `finished, exit ${job.exit_code}`) + `  (log: ${job.log})`;
  const f = follow;
  $("follow").hidden = !(job && job.running && !(f && f.jobId === job.job_id));
  if (f && job && f.jobId === job.job_id) {
    // Status first, then the trace: once the job reads as finished, the trace read after it is complete.
    const where = {base: "demo", root: job.run_root || "", instance: job.instance, task: job.task_id};
    try {
      const t = await get("/api/trace?" + q({...where, offset: f.offset}));
      if (f === follow) {
        addEvents(t.events);
        f.offset = t.offset;
        if (!job.running) {
          const run = await get("/api/run?" + q(where));
          if (f === follow) { follow = null; showVerdict(run); loadRuns(); }
        }
      }
    } catch (e) {
      if (!e.status) setConn(false);
      // A 404 is expected until the harness creates the task directory. Once the job has ended it means the run
      // never got that far, and the only record of why is the console log.
      else if (!job.running && f === follow) {
        follow = null;
        $("verdict").replaceChildren(el("p", "error", `The run ended without a task directory. See ${job.log}`));
      }
    }
  }
  setTimeout(poll, 1000);
}
(async () => {
  $("task").onchange = fillInstances;
  $("instance").onchange = updateHint;
  $("start").onclick = start;
  $("follow").onclick = followCurrent;
  $("base").onchange = loadRuns;
  try {
    tasks = await get("/api/tasks");
  } catch (e) {
    setConn(false);
    return;
  }
  $("task").replaceChildren(...tasks.map(t => el("option", "", t.id)));
  fillInstances();
  loadRuns();
  await followCurrent();  // a refresh during a run picks the live view back up
  poll();
})();
</script>
</body>
</html>
```

- [ ] **Step 3: Offline tests still pass**

Run: `python -m pytest tests_ai/test_viewer.py tests_ai/test_runs_dir_flag.py -v`
Expected: all PASS (`test_page_carries_the_session_token` now serves the real page).

- [ ] **Step 4: Manual smoke test on committed evidence — no live run**

Run: `python -m viewer`, open `http://127.0.0.1:8765`. Do **not** press Start.
Check:
- "Full runs" lists `20260917-110938  30/30 approved` first, then the two older runs.
- Clicking `suryodaya concurrent_edit_before_write` shows the step timeline, `approve`, `result.json on disk before verdict.json: true`, and the `interference` and `cleanup` blocks.
- A task in the older runs with no `verdict.json` (if any) shows "no verdict", never approve.
- "Demo runs" is empty.
- Tool events have collapsed `arguments` and `result`; expanding one shows the full JSON.
- Click two past runs quickly one after the other: the pane ends on the second, never a mix.
- Stop the console (Ctrl-C) with the page open: the red "Disconnected" banner appears within a second; restart it and the banner clears.
- Resize to phone width: panels stack, no horizontal scroll.
- Dark mode (OS setting): text stays readable.

- [ ] **Step 5: Commit**

```bash
git add viewer/__main__.py viewer/static/index.html
git commit -m "Add the console page: a live step timeline, the verdict and past runs"
```

---

### Task 6: Docs

**Files:**
- Modify: `README.md` (new section after the harness section, and the Layout table), `AGENTS.md` ("Live systems" list and "Run output")

- [ ] **Step 1: README — add a section after the harness section**

```markdown
## Live run console

```bash
python -m viewer            # http://127.0.0.1:8765
```

A local page for the screen-shared live demo. Pick a harness task and an instance, type the confirmation it
asks for, and watch the agent's steps arrive, then the verdict and the evidence behind it (the finding in the
database, the write ordering, interference and cleanup). It also browses past runs.

- It starts the same command you would type: `python -m harness.runner --task <id> --instance <name>
  --runs-dir runs/demo`. Every click is a live run against a shared tenant.
- Demo runs land in `runs/demo/`, never `runs/2026*`, so a partial run cannot become the run
  `scripts/verify_submission.py` grades.
- One run at a time, only tasks from `harness/tasks/team04/`, no `--apply`/`--escalate` outside what a task declares.
- There is no stop button: a killed run skips the escalation withdrawal. Ctrl-C stops the page, not the run.
- Localhost only. It is not built to be shared or hosted.

**Before the demo**

- One console process only, and no `python -m harness.runner` from a terminal while it runs: the one-run guard
  lives in the console's memory and shared fixture rows would collide.
- Never restart the console while a run is in progress. The run keeps going, but the new console forgets it;
  wait for the log in `runs/demo/` to end.
- Check provider, model and date without showing `.env` on screen (`.env` beats exported variables):
  `grep -E '^(LLM_PROVIDER|OPENAI_MODEL|OPENROUTER_MODEL|AGENT_TODAY)=' .env`. The trace's `start` event shows
  the provider and model actually used.
- After an escalation task, read the `cleanup` block. A failed withdrawal does not change the verdict, so the
  page flags it; withdraw that escalation by hand.

**Demo order** (agent time from the 17 Sep run): `refuse_unknown_work_order` on keystone (~15 s) →
`why_late_wo48_subcontract` (~70 s) → `concurrent_edit_before_write` (~100 s; writes fixture rows, escalation
withdrawn after scoring). Show `escalate_blocked_wo48` (~190 s) from past runs instead of live. If a tenant is
down, walk through `runs/20260917-110938` in the same page.
```

Add to the Layout table: `| viewer/ | local live-run console (python -m viewer) |`.

- [ ] **Step 2: AGENTS.md** — in "Live systems — ask before running", add:

```markdown
- `python -m viewer` is safe to start, but its **Start run** button runs `python -m harness.runner` —
  same rule, ask first
```

In "Run output", add: "`runs/demo/` holds console runs; the checker never reads it."

- [ ] **Step 3: Commit**

```bash
git add README.md AGENTS.md
git commit -m "Document the live run console and its demo order"
```

---

### Task 7: Verification and a live rehearsal

- [ ] **Step 1: Submission checker, offline**

Run: `python scripts/verify_submission.py --offline` (it runs the graded suite itself, with `AGENT_OFFLINE=1`)
Expected: exit 0; every listed check `PASS` except the lines it prints as `skip` (the live graded tests and
section E bug reports); the "latest full run" line still names `20260917-110938` (30/30 approved). If it names
anything else, a run landed in `runs/` — stop and find out why.

- [ ] **Step 2: New tests**

Run: `python -m pytest tests_ai/test_viewer.py tests_ai/test_runs_dir_flag.py tests_ai/test_run_dirs.py -v`
Expected: all PASS.

- [ ] **Step 3: Trace secrets spot check**

Run: `grep -rilE "password|bearer|access_token" runs/20260917-110938`
Expected: no output (checked 2026-09-30, clean). The page shows traces on a shared screen, so re-check after any change to what the agent traces.

- [ ] **Step 4: Live rehearsal — ASK PRAVIN FIRST**

With approval: `python -m viewer`, start `refuse_unknown_work_order` on `keystone` (dry run, no fixture; writes one AgentMemory row and an AgentSession). Expect: status reads "running" at once; steps appear as the harness emits them (login, fixtures and context
capture come first); verdict `approve`; a new root under "Demo runs". While it runs, also check: refresh the
page (the live timeline comes back); click a past run, then "Follow current run" (live view resumes, nothing
from the live run leaked into the past run).

Then rerun `python scripts/verify_submission.py --offline` — the latest full run must still be `20260917-110938`.

- [ ] **Step 5: Request review**

Use superpowers:requesting-code-review on the branch diff against `main` before opening a PR.
