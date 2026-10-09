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

Submitting on AgentSwitch ("Our harness" → Submit for a run) runs `agentswitch-harness.toml`
against a throwaway copy of the instance, so it does not touch the shared book, but it spends
the team's **one run every 3 days**: never submit without being asked.

## Commands

```bash
pip install -r requirements.txt
cp .env.example .env    # both passwords + OPENAI_API_KEY; .env is git-ignored

python -m pytest tests                              # graded tests — 13 of the 40 hit live tenants
AGENT_OFFLINE=1 python -m pytest tests              # the 27 that need no network
AGENT_TODAY=2026-09-16 python -m pytest tests_ai -v # pin the date or results drift
python scripts/verify_submission.py                 # full pre-submission checklist
python scripts/verify_submission.py --offline       # skip network checks
python scripts/check_results.py                     # results.json in the platform runner's format
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

Python 3.11, but the runtime code (`prod_agent/`, `harness/`) must also run on **3.10**: the
platform's harness runner does not say which Python it uses, and `datetime.UTC` (3.11+) once
broke every finding there. `tests_ai/test_python_floor.py` guards it; tests and
`scripts/verify_submission.py` may use 3.11 (`tomllib`). Plain `pip`, no lockfile. Required in `.env`: `TEAM04_PASSWORD_SURYODAYA`,
`TEAM04_PASSWORD_KEYSTONE`, `OPENAI_API_KEY`. Optional: `OPENAI_MODEL` (default
`gpt-4.1`), `AGENT_TODAY`.

`LLM_PROVIDER` picks where the loop sends its completions. Unset or `openai` is the
default and reads `OPENAI_API_KEY`/`OPENAI_MODEL` as before. `openrouter` routes through
`https://openrouter.ai/api/v1` and requires both `OPENROUTER_API_KEY` and
`OPENROUTER_MODEL` — there is no cross-provider fallback, and no default slug, because
`gpt-4.1` is not a valid OpenRouter id (they are `vendor/model`). A model reached this way
must support tool calling and should accept a forced `tool_choice`: if it rejects one, the
loop falls back to `required` and then `auto` for the rest of the run, which makes recording a
finding likely rather than guaranteed. Each run's `start` trace event records the resolved
provider.

**`.env` overrides the process environment**, not the other way round — an exported shell
variable is silently beaten by a non-empty `.env` line (`prod_agent/config.py:55`).

`AGENTSWITCH_TOKEN`, `AGENTSWITCH_BASE_URL` and `AGENTSWITCH_INSTANCE` belong to the platform's
harness runner and are shell-only, read from `os.environ` like `AGENT_OFFLINE` below. With
`AGENTSWITCH_TOKEN` set the code is in **platform mode**: `.env` is not read at all (the
runner's `OPENAI_*` win), `Session` uses the given token and base URL for that one instance
(no login, no `.tokens/`), `LLM_PROVIDER` is ignored, and `harness.runner` runs a preflight,
keeps a 27-minute budget (`HARNESS_BUDGET_MINUTES` overrides) and rewrites `results.json`
after every task. Unset them before running tests; `tests_ai/conftest.py` clears them for
the AI-written tests.

`AGENT_OFFLINE` is the other exception, and it is **shell-only**: putting it in `.env` does nothing.
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
