# Gap Report — Production Seat (Team 04)

**Team:** Ramesh, Nishanth, Pravin Gadekar  **Measured:** 16–17 Sep 2026, re-checked read-only 21 Sep, on Suryodaya (India) and Keystone (US)
**Request:** *"This work order is late. Find out why, tell me what it blocks downstream, and reschedule what you can."*
**Evidence labels:** *documented* = Carbon's docs or source · *observed* = seen live · *inferred* = suggested, not proven · *untested* = not safely exercised

## Why Carbon

[Carbon](https://carbon.ms) is an AI-native, open-source manufacturing system (ERP, MES and quality on one data model) that ships an **MCP server** over its production data, so the bar for our agent is public. We reviewed its scheduling and MCP docs and source, not a trial.

## What changed on 21 September

The seat catalogue moved from 301 to 310 tools on both instances (*observed*). It gained `QualityIssue.*` and `tools.search`; it lost `SalesOrder.*` reads and `TrustedSender.*` (the control we reported as B10).

**SalesOrder reads left the seat.** `WorkOrder.sales_order_id` is still populated (65 of 125 on Suryodaya, 17 of 77 on Keystone) but nothing resolves it, so **customer exposure can no longer be traced**. The agent degrades safely: it probes `SalesOrder.get` first and names the entity in `not_visible` (`prod_agent/domain.py:396`); the verifier returns `unevaluated` rather than guessing (`harness/verifiers/team04.py:346`). Whether the withdrawal is deliberate is **unknown**, and worth asking.

## 1. What Carbon does that we do not

| Capability | Carbon (*documented*) | AgentSwitch today (*observed*) | Gap assessment |
|---|---|---|---|
| **Capacity-aware scheduling** | Places operations within work-centre hours, subtracts maintenance downtime, reserves qualified operators | Unchanged: all 61 open orders project `projected_finish` = today, and `capacity_basis` still reports work calendars, labour and setup as not modelled. Downtime did not appear to move the projection (*inferred*), so the 17 Sep fix we relayed is unconfirmed | **Platform defect, model gap** |
| **Specific delay reasons** | Operation-level reasons: waiting behind a named job, a work centre, or an operator | Better, not fixed. New codes `material_short` (8 causes, with shortage lines) and `subcontract_pending` (43 across 33 orders, naming the subcontract order and status). But `due_date_passed` still sits on 56 of 57 late orders and `blocking` is empty on all 160 causes, so none names a blocking job. The reported `generic_late_cause_rate` of 0.0175 counts only `work_content_exceeds_due_date` as generic, overstating the gain | **Narrowed; named-blocker gap remains** |
| **What-if and replanning** | Non-persistent forecast of projected completion; whole-location replan that reports newly late jobs | `tools.search` still finds nothing for simulate, replan, pegging or dependency. `reschedule_jobs` (new) moves a planned window with no dry-run, rolling a moved operation onto its parent job unless `rollup: false`; its `result` is unconstrained, so the schema does not say whether newly late jobs come back (*untested*) | **Platform capability missing** |
| **Shared-material allocation** | Shortfall calculated across active jobs in priority order | Unchanged. Stock is checked one order at a time; `StockEntry` and `StockLedger` stay outside the seat | **Seat limit plus scoped-service gap** |
| **Order dependencies** | Predecessors within a job; knock-on lateness after a replan | The link we said was missing now exists, but `supplies_work_order_id` is populated on 0 of 125 orders on Suryodaya and 0 of 77 on Keystone | **Link exists, data absent** |

**Access bugs, now fixed.** Job cards, downtime entries and engineering changes were refused although the schema granted them. We filed bugs, the platform opened them on 17 Sep, and the agent now uses all three.

## 2. Which gaps an agent can close with the tools we already have

**Ours: orchestration over the current API**

- **Why it is late.** Join the work order with its job cards (the operation it is stuck at), recorded downtime, pending engineering changes, quality issues, material requests, subcontract orders, inspections and stock check. The result is *candidate* causes, separating blockers with no known date (an unsent subcontract, an open engineering change) from contributing ones.
- **What it blocks.** Walk BOMs in reverse to find *potential* consuming orders, never presented as confirmed blocks. Customer exposure is now only an unresolvable sales-order id plus an escalation.
- **Reschedule what it can.** Draft orders accept new dates (*observed*); submitted orders refuse them (*observed*); in-progress and stopped orders, and `reschedule_jobs`, are *untested*. The agent re-reads before writing, changes only what the state allows, confirms, and escalates the rest.

**Yours: platform work**

| Required capability | Why the agent cannot safely rebuild it | Classification |
|---|---|---|
| Capacity-aware projected dates | Re-reading records cannot reproduce a scheduler | Platform defect and model gap |
| What-if analysis and replanning | Nothing previews a change without saving it | Platform capability missing |
| Re-dating submitted orders | Dates lock after submit; only an admin can cancel | Platform capability missing |
| Cross-order dependency (pegging) | A BOM match shows possible demand, not confirmed supply | Link present, data absent |
| Shared-material allocation | Stock ledgers are outside the seat | Seat limit plus scoped-service gap |
| Customer exposure, material receipt dates, operator contact | `SalesOrder`, `PurchaseOrder` and `Employee` are outside the seat | Seat limit; escalate |

## 3. What an agent can do that Carbon's product cannot

Carbon exposes MCP too, so we claim no exclusive capability — and the claim narrowed on 21 Sep, because `finite_schedule` now joins capacity and material evidence itself, which we had listed as our advantage. What remains is **orchestration with evidence discipline**: one pass through the whole request, which Carbon leaves to a person; a Carbon date change does not replan itself, so its result must be re-read.

**Worked example: WO-2026-00048** (*observed* 16 Sep; stopped, 202 days past due)

- **Rules out material:** its material request was received and stock is sufficient.
- **Finds the blocker:** subcontract orders SCO-2026-00030 and SCO-2026-00076 are still in draft, so the outside work was never sent.
- **States the exposure:** sales order SO-2026-00092, Kirloskar Pumps, INR 494,476.64, promised 7 March 2026 — **no longer reproducible** since 21 Sep; it now names the id and escalates.
- **Decides what not to do:** it commits no date while the subcontract is unsent.

It works in a book other teams are changing: if an order changes between proposal and write, it keeps the other edit, stops writing and escalates. On Keystone it reads currency (USD) from the platform. Where no escalation assignee exists, it says so rather than claiming a handover.

*Carbon review and re-check: Pravin Gadekar. Observations: Team 04.*
