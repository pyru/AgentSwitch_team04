# Bugs filed by Team 04

All reports were filed through `POST /api/bug-report` as team04 (Production seat). Full reproduction steps are in each report (`GET /api/bug-report/mine`).

| # | Instance | Report id | Summary | Board | Severity | Status (17 Sep) |
|---|---|---|---|---|---|---|
| B1 | Suryodaya (also Keystone) | f99d53d5-a527-4884-9d91-2407107f0b95 | JobCard and DowntimeEntry unreadable for `manufacturing_user`, although the schema grants read | M1 | Critical | Live, Release 1 |
| B1a | Suryodaya (also Keystone) | 92bb5235-35ed-4ce2-bea2-52acc3b4fc08 | EngineeringChangeOrder unreadable too; same root cause as B1 | S20 | High | Live, Release 1 |
| B2 | Suryodaya (also Keystone) | cda6df5e-d47e-4e5e-9d4f-55a7a88bf1da | `finite_schedule` returns JobCard ids that `JobCard.get` reports as not found | M2 | High | Live, Release 1 |
| B2a | Suryodaya | 0c52d179-4916-4eda-864e-51ae842448a3 | `finite_schedule` exposes downtime and job-card data the entity tools refuse; follow-up to B2 and B4 | S21 | Medium | Live, Release 1 |
| B3 | Suryodaya | 9dd39dd6-69b4-4683-ad62-5302273e6a5d | Admin-only transitions (e.g. WorkOrder cancel) listed in `tools/list` for `manufacturing_user` | M3 | Medium | Live, Release 1 |
| B4 | Suryodaya | 293321e3-7f66-4d13-a645-872ba6cb7052 | `finite_schedule` never attributes downtime or blocking to late orders | M4 | Medium | Live, Release 1 |
| B5 | Keystone | a45d393a-da35-46e5-b0a9-659f38e88141 | Workstation numbers contain the literal format token (`WS-.#####-2026-00001`) | M5 | Medium | Live, Release 1 |
| B5a | Keystone | 32c5715c-4879-4bf1-b881-6ff65d5231c2 | Duplicate of B5; adds serial numbers with an empty `number` | S22 | Medium | Live, Release 1 |
| B6 | Keystone | 4c26c220-0513-4423-8b5c-76eb28c5bbc6 | Cost Analysis page shows ₹ for a US company whose currency is USD | S30 | Medium | Fixed, next release |
| B9 | Suryodaya (also Keystone) | a77321bc-5a2d-4a3d-8106-3f05a7146afc | `check_stock_availability` returns "not found" inside a success response instead of an error | S29 | Medium | Fixed, next release |

| B10 | Suryodaya (also Keystone) | af8c5d99-1408-48bb-b3f2-e1274d1d6a18 | Production seat can create, update and delete email `TrustedSender` rows (another app's security control) | — | High | Filed 17 Sep, after cutoff |
| B11 | Suryodaya (also Keystone) | 64772b8a-4d5e-4cbb-b245-a45b7c995f21 | Every `.delete` tool returns `{"deleted": true}` for an id that does not exist | — | Medium | Filed 17 Sep, after cutoff |
| B12 | Suryodaya (also Keystone) | 4a41704c-7308-4611-bf8b-da08a2446fee | `finite_schedule` `recorded_downtime` cites downtime linked to neither the order nor the cause's workstation (follow-up to M4) | — | Medium | Filed 17 Sep, after cutoff |

| B13 | Suryodaya | d7263aae-f93e-4501-b55d-8d62ce126703 | SalesOrder read lost by the Production seat on 20 Sep; `sales_viewer` still granted in `/api/auth/me` but absent from every permission map | — | High | Filed 21 Sep |
| B13a | Keystone | b961b3a9-036f-4617-9793-2c3575588f5f | Same defect, filed separately on Keystone | — | High | Filed 21 Sep |

**B13 detail.** Between 07:52 and 08:35 IST on 2026-09-20, mid-harness-run, `SalesOrder` stopped being
readable from the Production seat on both instances: REST 403 on the collection *and* on 49 distinct ids
taken from `WorkOrder.sales_order_id`, and every `SalesOrder.*` tool disappeared from `tools/list`. The
entity is still in `/api/schemas`, and `/api/auth/me` still grants `sales_viewer` — but no entity's
permission map references that role, so it now grants nothing anywhere. Same class as B1. In the same
window the seat's tool count went 301 -> 310 and the schema entity count 424 -> 428, so a release landed.
Cost: 3 of 30 harness tasks unevaluated and 2 of 40 hand-written tests failing, all customer-impact.

| B14 | Suryodaya + Keystone | a89f99b5-9496-4510-9d96-280409dcafb3 / 7eb3b883-6fd4-4156-aabf-a35a1e8c6480 | Invalid `sort_order` silently accepted and treated as `asc`, while invalid `sort_by` correctly 400s | — | Medium | Filed 21 Sep |
| B15 | Suryodaya | 40e36812-246a-4920-abe5-bf14d76d516d | `BugReport.created_by` is always `"system"`; every other entity records the real user id | — | Medium | Filed 21 Sep |

**B14 detail.** `sort_order=sideways` returns 200 and ascending rows, identical to `sort_order=asc`, on both
instances. `sort_by=nonexistent_field` correctly returns 400, and `limit=-1 / 99999 / abc` and `offset=-5`
all return 422, so this one value is the gap. It matters because "most recent N" on an agent-driven platform
is `sort_by=created_at&sort_order=desc&limit=N`: a wrong enum silently returns the OLDEST rows with no error
the caller can detect.

**B15 detail.** Rows we create on `WorkOrder` (9) and `AgentMemory` (192) carry our real user id in
`created_by`. All 13 of our `BugReport` rows carry `"system"`, with `updated_by` null. Attribution survives
only in the free-text `reporter` column, so anything joining on `created_by` attributes every report in the
tenant to one pseudo-user.

**Closed without filing.** B7 (every team could read every other team's bug reports via the generic
`BugReport` API) was re-tested on 21 Sep and is **fixed**: `/api/BugReport` now returns only our own 13 rows.
B8 (whether `BugReport.create` honours a spoofed `reporter`) remains unconfirmed and is not filed, because
confirming it would write a row attributed to another team into the shared triage queue.

| B16 | Suryodaya | ae363fd5-de93-466e-9cdb-c4503c6f2617 | M3 incomplete: SubcontractOrder page still offers Approve, Reject, Cancel and delete to the Production seat | — | Medium | Filed 21 Sep |
| B17 | Suryodaya | de7b45d3-8b00-4b12-9253-db33df2c1fe3 | SubcontractOrder detail labels `vendor_id` as "Customer", and labels both warehouse fields "Store" | — | Medium | Filed 21 Sep |

**B16 detail.** Filed as a follow-up to M3, not a new defect. M3's fix removed the admin-only transitions
from `tools/list` and that part holds, but the web UI was not covered, so the same permission is still
offered through the other door. Verified unavailable on three doors: `SubcontractOrder.permissions` gives
`manufacturing_user` only read/create/write/submit; our MCP catalogue has only
`SubcontractOrder.approval.submit` (submit *for* approval); and `ApprovalRequest.permissions` omits
`manufacturing_user` entirely, with `/api/ApprovalRequest` and `/api/ApprovalPolicy` both 403.

**B17 detail.** `SubcontractOrder` has no customer field — the value shown as "Customer" is `vendor_id`,
which names the wrong side of the transaction on an order whose whole point is sending material out. The
two fields both rendered "Store" are `vendor_warehouse_id` and `target_warehouse_id`.

**Considered and not filed.** The Keystone agent dashboard tile reads "SCHEDULED TASKS 0" beside a list of
2 (both `AgentTask` rows are `paused`, confirmed over REST) — real but cosmetic, and likely to be triaged
into the known Keystone AgentTask item. The Keystone dashboard's "TOOL CALLS 96" happens to equal
Suryodaya's `AgentTask` row count; almost certainly coincidence, and we will not file a cross-tenant claim
we cannot substantiate.

Distinct defects: about 15 (B1a, B2a and B5a are follow-ups or duplicates).

Status from the class Bug Board, 17 Sep: the first 10 reports were all accepted; 8 live in Release 1 (17 Sep 2026, 18:40 IST), 2 fixed and shipping in the next release. Re-tested live on both instances the same day. B10-B12 were filed after the 14:35 cutoff, so they are queued for the next release and carry no board id yet.
