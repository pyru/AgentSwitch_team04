# AGENTS.md

Instructions for AI coding agents working in this repository. Read this before
changing code or running anything.

## Live systems — ask before running

Both the agent and the harness talk to **live shared instances**. There is no local
database, no mock server, and no `--dry-run`. Ask Pravin before running:

- `python -m harness.runner` (any form) — every successful run writes an `AgentMemory`
  row, and fixtures create/update real `WorkOrder` rows on Suryodaya
- `python -m prod_agent ... --apply` — mutates real work orders
- `python -m prod_agent ... --escalate` — raises a **real escalation assigned to a real
  person**. The harness withdraws these after scoring; the CLI does not.

Reading code, offline tests, and inspecting `runs/` output need no confirmation.

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env    # both passwords + OPENAI_API_KEY; .env is git-ignored

python -m pytest tests                              # graded tests — 13 of the 40 hit live tenants
AGENT_OFFLINE=1 python -m pytest tests              # the 27 that need no network
AGENT_TODAY=2026-09-16 python -m pytest tests_ai -v # pin the date or results drift
python scripts/verify_submission.py                 # full pre-submission checklist
python scripts/verify_submission.py --offline       # skip network checks
```

`verify_submission.py` shells out to `pytest tests -q` and exits non-zero on any failed
check. Run it before considering work done. Under `--offline` the graded suite is reported as a
skip with counts rather than a `PASS`, because it no longer verifies the 13 live tests; the run
still fails on a genuine test failure, and it fails if the suite reports **no** skips at all,
since that means the gate never engaged and the tests really did run live.

Agent and harness invocations are documented in each module's docstring
(`prod_agent/__main__.py`, `harness/runner.py`) — this repo uses docstrings instead of a
Makefile.

## Environment

Python 3.11. Plain `pip`, no lockfile. Required in `.env`: `TEAM04_PASSWORD_SURYODAYA`,
`TEAM04_PASSWORD_KEYSTONE`, `OPENAI_API_KEY`. Optional: `OPENAI_MODEL` (default
`gpt-4.1`), `AGENT_TODAY`.

`LLM_PROVIDER` picks where the loop sends its completions. Unset or `openai` is the
default and reads `OPENAI_API_KEY`/`OPENAI_MODEL` as before. `openrouter` routes through
`https://openrouter.ai/api/v1` and requires both `OPENROUTER_API_KEY` and
`OPENROUTER_MODEL` — there is no cross-provider fallback, and no default slug, because
`gpt-4.1` is not a valid OpenRouter id (they are `vendor/model`). A model reached this way
must support tool calling *and* a forced `tool_choice`; without the latter the loop cannot
make it record a finding before the step budget ends. Each run's `start` trace event
records the resolved provider.

**`.env` overrides the process environment**, not the other way round — an exported shell
variable is silently beaten by a non-empty `.env` line (`prod_agent/config.py:20`).

`AGENT_OFFLINE` is the one exception, and it is **shell-only**: putting it in `.env` does nothing.
The root `conftest.py` reads it straight from `os.environ` during collection, which happens before
anything calls `load_dotenv`, precisely so a stray `.env` line cannot silently switch the gate on
or off. Set to exactly `1`, it skips every test that depends on a live-tenant fixture — `surya`,
`suryodaya` or `keystone` — before the fixture can log in. Any other value, including empty, means
"not offline". The gate only applies when pytest actually loads the root `conftest.py`, so
`cd tests && pytest .`, an absolute tests path from an unrelated directory, and `--noconftest` all
bypass it: invoke pytest from the repository root.

## Hard constraints (enforced by scripts/verify_submission.py)

These fail the submission check, not just review:

- **No agent framework.** The loop is hand-rolled; the checker greps `agent.py` for
  `for step in range(self.max_steps)` and fails if langchain/llama/autogen/crewai appears
  in `requirements.txt`.
- **Verifiers grade the database, never the reply text.** The string `final_answer` must
  not appear in `harness/verifiers/team04.py`.
- **Never write to `tests/`.** Those tests must stay human-authored — they are worth 10
  points each, and AI-authored ones score zero. The checker enforces this by failing if
  the string "claude" appears in any `tests/test_*.py` file, so do not add AI-authorship
  labels, attribution, or tool names there either. AI-written tests belong in `tests_ai/`,
  which is ungraded.
- **`GAP_REPORT.md` has a 1100-word cap.**
- Nothing may be hardcoded to one country or currency — read it from `Company`.

## Domain rules that are easy to get wrong

- Downstream impact from a BOM match is **potential**, never confirmed:
  `potentially_blocked_work_orders` with `confidence: potential`. Only a sales order on
  the late order itself is `linked`.
- **Refusing correctly is a success**, not a failure — roughly a third of the task set is
  refusal cases.
- Seat limits are **probed, not assumed**: 403 means a real limit, 404 means an invented
  capability name.
- Harness verdicts are `approve` / `revise` / `unevaluated`. **`unevaluated` never counts
  as a pass** — a verifier returns it when a task's premise has changed, rather than
  guessing.
- **Persist, then verify**: `result.json` is fsync'd to disk before any verifier runs.
  `verify_submission.py` checks mtimes to prove the ordering held.

## Platform quirks

- JSON-RPC errors arrive as **HTTP 200** — every MCP call must inspect the envelope.
  Some endpoints report refusals inside a success envelope.
- Reads are retried on 502/503/504; **writes are never retried**.
- Once any write reports `changed_underneath`, every further write in that run is refused.
- `temperature=0` is only sent for `gpt-4*`/`gpt-3*` models, matched after any `vendor/`
  namespace is stripped so `openai/gpt-4.1` still counts; reasoning models reject it. This
  is an allow-list on purpose: a miss only costs determinism, whereas sending the parameter
  to a model that rejects it raises from an LLM call that has no `try` around it.

## Code style

No linter or formatter is configured, and running `black`/`ruff format` would reformat the
whole repo — don't. Match what's there: double quotes, ~120-char lines, PEP 604 unions and
builtin generics (`dict | None`, `list[dict]`, never `typing.Optional`/`List`), plain dicts
as the data interchange format (no dataclasses or pydantic), stdlib → third-party → local
imports. Comments explain *why the platform behaves oddly*, not what the code does.

## Run output

Agent runs land in `runs/adhoc/<timestamp>-<instance>/`, harness runs in
`runs/<timestamp>/<instance>/<task_id>/`. `runs/` is git-ignored, but a few run
directories are **deliberately committed as grading evidence** — never delete or
regenerate those.
