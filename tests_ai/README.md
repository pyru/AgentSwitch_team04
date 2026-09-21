# AI-written regression tests

Everything in this folder was written by an AI assistant — most of it by Claude, some by Codex, as each file's docstring records. It is **not** part of the team's hand-written tests and scores nothing under the course rules. The graded tests are in `tests/`.

Purpose: catch regressions in the agent and changes in the platform (two tests, marked B1 and B3, fail deliberately once those bugs are fixed).

```powershell
$env:AGENT_TODAY = "2026-09-16"
python -m pytest tests_ai -v
```
