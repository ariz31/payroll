# Verification strategy, test matrix and seed fixtures

The [automated tests](../../tests) exercise the six reference cases, PostgreSQL invariants, concurrency, permissions, offline ingestion, OIDC validation, retention, and payroll artifact contracts. The Chromium scenario covers the kiosk, offline reload, all three review roles, CSV download and print view. The broader register below includes field tests and recovery checks for deployment.

## 1. Test layers

| Layer | Focus | Gate |
| --- | --- | --- |
| Pure unit / property | Time arithmetic, rounding, anomaly precedence, shift anchor | Every commit |
| DB integration | Append-only scan journal; raw write-once; adjustment CHECK; FK/unique and concurrent pairing | Every merge |
| Service integration | Signature/auth, geofence, role checks, time drift, idempotent ingest, approval state machine | Every merge |
| Device/offline fault | Durable outbox, reboot, network flap, replay, clock drift, storage full, partial acknowledgments | Before pilot |
| E2E | Kiosk → Tier 1/2/3 → export → hold check | Before release |
| Contract/golden | 23-column CSV/XLSX exact order/format, totals and Power Query compatibility | Every schema change |
| Security/privacy | Access isolation, evidence access, unauthorized export, insider/terminal threat | Before production |
| Load/recovery | Rush-hour gate latency, queues, backup restore, incident drills | Before pilot/production |

## 2. Required six reference cases, pay period 2026-11

Use synthetic records, not real worker attendance. `Work_Date` uses shift start date.

| ID | Scan_ID / person | Inputs | Expected result |
| --- | --- | --- | --- |
| T-001 | QR-2611-001 / EMP-1001 Elena Reyes | Day 07:56–17:04, duplicate 07:58 | Duplicate audit `IGNORED_DEBOUNCE`; 8.00 reg, 0.13 OT; 0.00 night; OK, Verified |
| T-002 | QR-2611-002 / EMP-1002 Marcus Vance | Night Nov 12 21:58 → Nov 13 07:03 | Work_Date Nov 12; 8.00 reg, 0.08 OT, 8.00 night; OK, Verified |
| T-003 | QR-2611-003 / EMP-1003 Sofia Chen | Day 08:01–NULL; TK adjusted out 17:00; explained and verified | Raw out remains NULL; effective out 17:00; 7.98 reg, 0 OT; OK, Verified; audit actor/time/note exists |
| T-004 | QR-2611-004 / EMP-1004 David Kalu | Day 08:00–20:30 | 8.00 reg, 3.50 OT; HIGH OT (>2h); Disputed / Rejected, excluded from payable |
| T-005 | QR-2611-005 / EMP-1005 Liam Navarro | Day 08:19–17:15 | 7.93 reg, 0 OT; LATE (>5m); Pending Review, employee AUDIT HOLD |
| T-006 | QR-2611-006 / EMP-1006 Rosa Mendoza | Night 22:00–NULL past shift closure | 0.00 all hours; MISSING QR OUT; Pending Review, employee AUDIT HOLD |

Fixture-specific names and dates are source data; department and terminal assignments are **not** specified by blueprint, so tests should choose clearly synthetic values and should not claim to reproduce an exact full export row from the source.

**Golden aggregate assertions:**
- `Verified_Regular_Hrs = 23.98` (8.00 + 8.00 + 7.98).
- `Verified_OT_Hrs = 0.21` (0.13 + 0.08).
- `Verified_Night_Hrs = 8.00`.
- `Pending_Count = 2`; `Audit_Hold_Emp_IDs = ["EMP-1005","EMP-1006"]`.
- `QR-2611-004` excluded; all six source shift rows **still exported** with status.

## 3. Boundary and security test register

| ID | Test | Expected invariant |
| --- | --- | --- |
| T-007 | Day arrival exactly 08:05 | Not late |
| T-008 | Day arrival 08:05:01 | LATE (>5m) |
| T-009 | OT exactly 2.00 | Not HIGH OT |
| T-010 | OT 2.01 | HIGH OT (>2h) |
| T-011 | Duplicate tap under 300 seconds | Separate audited IGNORED_DEBOUNCE; only one punch |
| T-012 | Tap at exactly 300 seconds | Policy **open**; freeze decision with test |
| T-013 | Dynamic 30s window ±1 | Accept valid in allowed windows; reject beyond; replay policy explicit |
| T-014 | Invalid HMAC / unknown Emp_ID / revoked badge | Audited rejection; raw punch unchanged |
| T-015 | Forged terminal / wrong site / geofence fail | Audited rejection; no punch |
| T-016 | Raw punch UPDATE, overwrite, NULL and DELETE | DB must reject |
| T-017 | Raw scan journal UPDATE/DELETE/TRUNCATE by app role | DB must reject |
| T-018 | Adjustment with no notes / actor / server time | Reject API + DB |
| T-019 | Final Disputed row with no justification | Reject API + DB |
| T-020 | Foreman attempting TK final/override | 403 and audit |
| T-021 | Cross-site / cross-project reviewer | 403; no data leak |
| T-022 | Two concurrent first punches | Exactly one accepted paired raw in; journal each attempt |
| T-023 | Duplicate transport retry same client event ID | Same receipt; no duplicate effect |
| T-024 | Offline network failure at partial batch ACK | Unacknowledged events retry safely |
| T-025 | Kiosk restart / low storage / altered hash chain | Durable queue or conspicuous quarantined failure |
| T-026 | Bad device clock and stale dynamic token replay | Approved quarantine/validation policy; no false acceptance |
| T-027 | Night shift month rollover / leap day / DST | Correct shift-start Work_Date; no time-only mispairing |
| T-028 | Missing out before shift closes | Not flagged prematurely |
| T-029 | Late and high OT together | Primary is LATE; secondary detail may persist |
| T-030 | Change config after final approval | Do not silently alter historical final/export evidence |
| T-031 | Export formula-style malicious name/notes | Safe spreadsheet import, correct round-trip |
| T-032 | Export Unicode, comma, quote, newline, empty time | Exactly 23 values per row; faithful data |
| T-033 | Pending employee also has Verified row | Employee-level hold blocks release |
| T-034 | CSV vs XLSX for same snapshot | Same semantic rows/status/totals |
| T-035 | Image access via unprivileged role | Denied + audit access |
| T-036 | Restore from backup and verify hashes | Raw evidence integrity and receipt consistency retained |

## 4. Suggested test data model

```json
{
  "pay_period": "2026-11",
  "site_timezone": "Asia/Manila",
  "day_shift": {"start": "08:00", "end": "17:00", "break_mins": 60},
  "night_shift": {"start": "22:00", "end": "07:00", "break_mins": 60},
  "late_grace_minutes": 5,
  "debounce_seconds": 300,
  "high_ot_hours": 2.00,
  "auto_verify_ok_scans": false,
  "expected_verified_totals": {"regular": 23.98, "ot": 0.21, "night": 8.00},
  "expected_audit_holds": ["EMP-1005", "EMP-1006"]
}
```

Timezone above is an **example test configuration**, not sourced site location. Fixture tests should inject a controlled clock and versioned policy.

## 5. Data integrity properties

For every persisted shift:
- raw values never change once set; recomputation only affects derived/versioned fields;
- no adjustment exists without corresponding authenticated audit event;
- no final rejection lacks actor, note and server timestamp;
- net and calculated hours are non-negative; regular ≤ 8.00;
- `Net_Worked_Hrs ≈ Calc_Reg_Hrs + Calc_OT_Hrs` to within rounding tolerance;
- no employee's Pending Review period can be marked “payroll release ready”;
- one client event ID has one server receipt; separate duplicate taps remain separate raw audit attempts;
- all exports use 23 exact headers.

## 6. Test evidence and release

Define repeatable CI jobs and record command/output when tooling exists; do not describe any tests as passing until they are actually run. For a release, provide migration result, fixture golden files, threat-test report, load summary, restore drill, privacy sign-off and a traceability sheet linking FR IDs to automated tests.
