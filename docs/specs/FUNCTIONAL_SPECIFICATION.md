# Functional specification

Blueprint-derived requirements (SiteGuard QR §§2–6). See the [operator guide](../engineering/OPERATIONS_GUIDE.md) for current behavior.

## 1. User journeys

### A. Initial setup and provisioning

**Preconditions:** admin is authenticated; site and terminal have approved location/config; employee is active.

1. Admin creates/updates employee with `Emp_ID`, `Full_Name`, `Department`, `Cost_Code`, `Assigned_Shift`, site association.
2. Admin selects **Dynamic** (rotating signed) or **Static** (signed laminated badge) mode and issues a uniquely identifiable credential.
3. Terminal enrollment binds `QR_Terminal_ID` to site, device credentials, configured geofence and current policy.
4. Revoked badge or inactive employee cannot create accepted punches; rejected attempts remain audited.
5. Every provisioning/revocation/config change records actor and time (proposed implementation detail).

**Acceptance:** inactive/revoked badge is rejected, badge text never alone grants timekeeping authority, and a worker cannot be accepted at an unauthorized site.

### B. Online gate scan

1. Terminal receives input from USB barcode scanner or webcam decoder.
2. Immediate pending feedback; client sends signed badge data, authenticated terminal identity, unique client event ID, measured device time and optional permitted image evidence.
3. Server validates token, badge/employee status, terminal/geofence, time window/replay, sequence and 300-second debounce.
4. Every attempt is journaled with accepted, ignored or rejected outcome.
5. Accepted arrival/departure is paired to a work date and evaluated; kiosk returns **Clock-In Recorded** or **Clock-Out Recorded**.
6. Other kiosk results: **Duplicate Tap Ignored**, **Rejected**, or **Offline Captured & Sealed** (offline means stored locally, **not** yet accepted by server).

**Acceptance:** median/percentile response latency measured against blueprint’s sub-second feedback target; no success banner before durable server acknowledgment for online mode.

### C. Offline gate scan

1. On loss of connectivity, terminal displays offline status and enqueues a sealed, ordered record (device ID, monotonically increasing sequence, unique event ID, capture evidence, hash).
2. Client retains queue through reload/device restart and clearly signals storage full, clock drift or integrity failure.
3. On reconnection, client uploads batches in sequence; server idempotently acknowledges each and applies authoritative validation/pairing.
4. Rejected/quarantined replayed scans remain visible to authorized operators for reconciliation; kiosk does not silently claim payroll approval.

**Acceptance:** re-upload cannot create duplicate attendance; offline failure cannot silently discard or reorder evidence. Detailed [offline requirements](QR_SECURITY_AND_OFFLINE.md).

### D. Exception and verification

1. Rule engine classifies each shift by **highest-priority** anomaly: MISSING QR OUT; MISSING QR IN; LATE (>5m); HIGH OT (>2h); OK.
2. Exceptions enter **Pending Review**. Clean OK rows may be bulk approved (default `auto_verify_ok_scans = FALSE`) or auto-verified if enabled.
3. Foreman attests crew/field context, engineer/department head reviews OT and cost code, central timekeeper finalizes.
4. Timekeeper corrections enter `TK_Adjusted_In` / `TK_Adjusted_Out`, never raw fields. Requires `Verified_By_TK`, meaningful `TK_Verification_Notes` and server `Verified_Timestamp`.
5. Final disposition is **Verified** or **Disputed / Rejected**; history retained. A rejected attempt is not synonymous with a shift with status Disputed.

**Acceptance:** forbidden role transitions, reasonless overrides and raw-punch edits fail in API and database tests.

### E. Payroll-period handoff

1. Select active pay period (YYYY-MM). Show pending row count before export.
2. Produce exact-header `06_QR_Timekeeper_Log` CSV/XLSX, including **Verified**, **Pending Review** and **Disputed / Rejected** rows.
3. Display/record AUDIT HOLD for **any employee** with pending rows in active period.
4. Downstream Power Query/ERP includes hours only for Verified rows, excludes Disputed and does not release held employees.
5. Printable DTR Form 48 is a separate target, subject to verified layout and employer/jurisdiction sign-off.

**Acceptance:** unresolved pending employees appear on hold, rejected hours are not paid, and all exported rows retain statuses.

## 2. Kiosk UX (target)

| Situation | Banner | Side effect |
| --- | --- | --- |
| Valid first arrival | Clock-In Recorded | Immutable arrival stored; scan audited |
| Valid later departure | Clock-Out Recorded | Immutable departure stored; paired |
| Same badge double-tap within 300s | Duplicate Tap Ignored | Audit only; paired shift unchanged |
| Connectivity unavailable, queue succeeds | Offline Captured & Sealed | Durable outbox only |
| Signature/expiry/geofence/device failure | Rejected | Audit failure; no punch mutation |
| Offline store full or tampered | Capture Failed — Contact Supervisor (**proposed**) | No deceptive acknowledgment |

Audio chimes, accessible text/icons and clear privacy notice are required design concerns. Do not publicly disclose detailed rejection criteria that enable token guessing.

## 3. Timekeeper workbench (target)

**Views:** KPI dashboard; sortable anomaly queue; shift detail with immutable raw punches and optional evidence; tiered review inbox; justified adjustments; configuration screen; export preview/holds/receipts; audit explorer (proposed decomposition).

**KPI definitions (reference):** Total Scans (specify accepted vs all attempts in ADR), Verified shifts, Pending Review shifts, Disputed / Rejected shifts, Missing QR Clock-Outs, Verified Regular Hrs and Verified OT Hrs. Verified hour counters must exclude unverified/rejected rows.

**Filters (proposed):** pay period, site, project/cost code, department, employee, shift, anomaly, status, reviewer tier and date. All list endpoints must be scoped by permission.

## 4. Configuration registry

| Config key (proposed internal label) | Blueprint default | Effect |
| --- | --- | --- |
| `day_shift_start` / `day_shift_end` | 08:00 / 17:00 | Day shift boundary |
| `night_shift_start` / `night_shift_end` | 22:00 / 07:00 | Overnight shift boundary |
| `break_mins` | 60 | Unpaid deduction |
| `regular_daily_cap_hours` | 8.00 | Regular hour cap |
| `late_grace_minutes` | 5 | >5m Day Shift alert |
| `debounce_seconds` | 300 | Ignore accidental taps |
| `high_ot_hours` | 2.00 | >2h OT alert |
| `dynamic_qr_step_seconds` | 30 | HMAC rotating token cadence |
| `dynamic_qr_drift_windows` | 1 | ±1 window |
| `qr_mode` | Dynamic + geofence | Admin may switch to static signed |
| `auto_verify_ok_scans` | false | Bulk/manual clean verification default |
| `site_geofence_radius_m` | **unspecified** | Decide per site before usage |
| `missing_out_grace_minutes` | **unspecified** | Decide closing rule before usage |

Store settings with effective dates/version and audit. Reevaluate **active** exception queues when thresholds change; do not silently override already finalized approvals.

## 5. Error handling and safeguards

- Bad QR, device mismatch, geofence failure, stale dynamic token and revoked badge → audited rejection; no punch changes.
- Missing arrival/departure → pending exception under correct timing; not a fabricated punch.
- Concurrent scan race → lock/idempotency; only one raw in/out set.
- Multiple conflicting badges/terminals → quarantine for adjudication (proposed).
- Camera permission unavailable → site policy determines accept/deny; must disclose outcome (open decision).
- Invalid edit, zero notes or unapproved reviewer → 4xx validation error; audit failed attempt where appropriate.
- Export with pending records → **not silent**; show count, include records/status, mark holds (do not falsely call exported file payroll-cleared).

## 6. Exclusions and source ambiguities

The blueprint does not provide actual page layouts, endpoint names, DB migration files, regulatory pay rates, storage retention periods, process for more than one shift/day, threshold timezone policy or image-consent wording. These are pending design choices, not implicit promises.
