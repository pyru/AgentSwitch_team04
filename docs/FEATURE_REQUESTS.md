# Feature requests filed by Team 04

Platform capabilities AgentSwitch does not have, found while building the Production seat's agent. These
are **not defects** — nothing listed here is broken. Each one is a gap identified in
[GAP_REPORT.md](../GAP_REPORT.md) §2 ("Yours: platform work") and filed through `POST /api/bug-report`,
the same intake as the in-app Report a problem button, for the Bug Board's **Carbon upgrade** list.

All five were filed on Suryodaya on 23 September 2026 and measured live that day.

| # | Report id | Capability | Page |
|---|---|---|---|
| FR1 | `ca9070af-b93d-495d-9ba3-42deb5775f25` | Capacity-aware projected finish dates | Manufacturing/Schedule |
| FR2 | `e5259852-4638-41c0-95e7-86cf213b7002` | A dry run for schedule changes | Manufacturing/Schedule |
| FR3 | `35174f29-09ef-4719-a030-3e2cbfeaea71` | Re-date a submitted work order without cancelling | Manufacturing/AllWorkOrders |
| FR4 | `64427056-9598-4ade-8e8e-b36a0d3e9809` | Populate the order-dependency link | Manufacturing/AllWorkOrders |
| FR5 | `9e068472-0b65-4484-9d1a-61aa6af5778d` | A manufacturing-scoped read for stock and expected receipts | Manufacturing/MaterialPlan |

## Why these five, and why filed this way

`BugReport` has no type, kind or category field — its only classification columns are `status`
(`new/triaged/fixed/wont_fix`) and `delivery` (`filed/local`). Classification is therefore done by whoever
triages the description, so each report opens with an explicit label:

> FEATURE REQUEST — Carbon parity, not a defect. For the Carbon upgrade list.

Without that line a feature request risks landing in the Bugs lane's "Not being built (feature requests)"
bucket, which is closed, rather than the Carbon upgrade wish-list, which is queued.

Each follows the same four beats: what Carbon does, what AgentSwitch has today (measured, with the actual
values), why an agent cannot close it by orchestration over the current API, and the smallest change that
would unblock it.

## Evidence behind each, as measured 23 Sep 2026

- **FR1** — `finite_schedule.capacity_basis` reports `work_calendar_modelled: false`,
  `labour_capacity_modelled: false`, `initial_setup_modelled: false`; `changeover_minutes_modelled` is now
  `true`. All **61 open orders return the same `projected_finish`, 2026-09-23**, so the projection carries
  no per-order information.
- **FR2** — no simulate/replan/what-if/pegging tool in the seat's catalogue. `reschedule_jobs` takes
  `work_order_id, job_card_id, planned_start_date, planned_end_date, planned_start, planned_end, rollup` —
  **no `dry_run`**. `demand_forecast` exists but is item-level demand, not schedule simulation.
- **FR3** — dates lock after submit for `manufacturing_user`; cancel is admin-only and correctly hidden
  since M3. The approval mechanism already exists via **N204** (delivery/due-date changes wait for approval
  and cannot be approved by the requesting seat).
- **FR4** — `WorkOrder.supplies_work_order_id` exists on the schema but is populated on **0 of 143** work
  orders on Suryodaya. Downstream impact therefore comes from a reverse BOM walk, which yields *possible*
  consumers; the agent reports them as `potentially_blocked_work_orders` with `confidence: potential`.
- **FR5** — `StockEntry`, `StockLedger`, `PurchaseOrder` and `Employee` all return 403. `SalesOrder` is
  **no longer** in this list: it was restored on 22 Sep per **N140**, so customer exposure is answerable and
  this is the last gap blocking a complete answer. Operator contact is deliberately **not** requested —
  names via `people_directory` (N146) are sufficient.

## Related

- Defects are tracked separately in [BUGS_FILED.md](BUGS_FILED.md) — 30 reports, ~20 distinct, 19 Live on
  the board.
- The analysis these came from is [GAP_REPORT.md](../GAP_REPORT.md) §2.
