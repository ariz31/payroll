# Timekeeping business rules and acceptance examples

**Status:** normative interpretation of source blueprint §§2–3 and §6, with flagged unresolved cases.

## 1. Reference configuration

| Rule | Default |
| --- | --- |
| Day shift | 08:00–17:00 local (60-minute unpaid break) |
| Night shift | 22:00–07:00 next day (60-minute unpaid break) |
| Regular cap | 8.00 hours per workday |
| Late Day Shift | effective in strictly **later** than 08:05 |
| Duplicate scan debounce | within 300 seconds; log `IGNORED_DEBOUNCE` |
| High overtime | calculated OT strictly **greater than** 2.00 |
| Dynamic token step | 30 seconds with ±1 step drift |
| Clean OK verification | bulk/manual by default; auto if explicitly enabled |

All thresholds are admin-configurable and stored in versioned settings. Boundary comparison is strict: arriving at **08:05:00** is not late; 2.00 OT is not “HIGH OT.”

## 2. Time anchoring

- A shift has `Work_Date` equal to the **local date when the assigned shift begins** (for night 22:00–07:00, not next-day out date).
- Pair night departure on following calendar morning to prior shift. Blueprint case: in **2026-11-12 21:58**, out **2026-11-13 07:03** ⇒ Work_Date **2026-11-12**.
- Store source instants with timezone; do not infer actual day solely from exported HH:MM.
- Reject/quarantine ambiguous, negative, physically implausible or >24h spans **until an approved policy exists**. Blueprint presents modulo-24 arithmetic; blindly applying modulo would make 25h appear as 1h, so this is an important open decision.

## 3. Effective punches

```text
Effective_In  = TK_Adjusted_In  if present else Raw_QR_Time_In
Effective_Out = TK_Adjusted_Out if present else Raw_QR_Time_Out
If either effective punch is absent:
    Net_Worked_Hrs = Calc_Reg_Hrs = Calc_OT_Hrs = Calc_Night_Hrs = 0.00
Else:
    elapsed_hours = actual elapsed time between full effective instants
    Net_Worked_Hrs = max(0.00, elapsed_hours - Break_Mins/60)
    Calc_Reg_Hrs   = min(8.00, Net_Worked_Hrs)
    Calc_OT_Hrs    = max(0.00, Net_Worked_Hrs - 8.00)
    Calc_Night_Hrs = Calc_Reg_Hrs if Shift_Type == "Night Shift" and Net_Worked_Hrs > 0
                     else 0.00
```

The full-instant elapsed time is a **proposed safe implementation** of the blueprint’s `((Effective_Out - Effective_In) mod 24h)` formula. It must preserve source expected examples while avoiding accidental modulo loss. No rounding intermediate calculations before final 2-decimal export (e.g., 8 minutes = 0.1333... → 0.13).

**Important:** the source’s `Calc_Night_Hrs` is a simplified **night-shift regular-hours** classification (entire regular component for a Night Shift). It is **not a validated jurisdiction-specific calculation of hours actually within 22:00–07:00**. For payroll night differential or overtime premium computation, obtain policy/legal sign-off and version the calculation.

## 4. Anomaly priority

Return exactly **one primary** `QR_Anomaly_Alert` per shift, using this precedence:

| Priority | Label | Predicate | Default state |
| --- | --- | --- | --- |
| 1 | `MISSING QR OUT` | Effective_In set, Effective_Out absent **after shift window closes** | Pending Review |
| 2 | `MISSING QR IN` | Effective_Out set, no paired effective arrival | Pending Review |
| 3 | `LATE (>5m)` | Day Shift effective arrival later than scheduled 08:00 + 5m | Pending Review |
| 4 | `HIGH OT (>2h)` | `Calc_OT_Hrs > 2.00` | Pending Review |
| 5 | `OK` | Paired, within normal tolerances | Bulk/manual Verified or automatic if enabled |

Missing clock-out should not be flagged before an approved shift-closure threshold. Multiple underlying anomalies may be retained internally, but the 23-column export has **only one primary string**. If late and high OT simultaneously, the primary is LATE (priority 3), unless the product owner changes precedence.

## 5. Six blueprint reference fixtures (period 2026-11)

| Scan | Employee | Local in → out | Override | Net / regular / OT / night | Alert, final state |
| --- | --- | --- | --- | --- | --- |
| QR-2611-001 | EMP-1001 Elena Reyes | 07:56 → 17:04 (07:58 ignored duplicate) | — | 8.13 / 8.00 / 0.13 / 0.00 | OK, Verified |
| QR-2611-002 | EMP-1002 Marcus Vance | Nov 12 21:58 → Nov 13 07:03 | — | 8.08 / 8.00 / 0.08 / 8.00 | OK, Verified; Work_Date Nov 12 |
| QR-2611-003 | EMP-1003 Sofia Chen | 08:01 → missing | adjusted out 17:00 | 7.98 / 7.98 / 0.00 / 0.00 | OK, Verified with justified override |
| QR-2611-004 | EMP-1004 David Kalu | 08:00 → 20:30 | — | 11.50 / 8.00 / 3.50 / 0.00 | HIGH OT (>2h), Disputed / Rejected |
| QR-2611-005 | EMP-1005 Liam Navarro | 08:19 → 17:15 | — | 7.93 / 7.93 / 0.00 / 0.00 | LATE (>5m), Pending Review / AUDIT HOLD |
| QR-2611-006 | EMP-1006 Rosa Mendoza | 22:00 → missing | — | 0.00 / 0.00 / 0.00 / 0.00 | MISSING QR OUT, Pending Review / AUDIT HOLD |

Rounded hours shown to two decimals. 07:58 ignored event is **not** a second clock-in. Record QR-2611-003 must retain `Raw_QR_Time_Out = NULL` even after `TK_Adjusted_Out = 17:00`.

**Verified payroll totals** (001–003 only): Regular **23.98**, OT **0.21**, Night **8.00**. 004 is excluded as disputed. EMP-1005 and EMP-1006 are on hold.

## 6. Edge cases beyond source (must define and test)

- Late at exactly 5m, OT exactly 2h, debounce exactly 300s (inclusive/exclusive boundary), token at 30s rollover.
- In/out less than break length, duplicate out, reentrant in, cross-terminal and cross-site attempts.
- Overnight out on next day, DST fold/gap, timezone changes, payroll month rollover and leap day.
- Scan arrives after review/export; offline records delayed for days; edited terminal clock; lost queue sequence.
- Foreman override requests vs central TK final authority; policy changes after a shift is finalized.
- Night shift outside nominal window; breaks that cross night premium boundary; split shifts/multiple shifts in one Work_Date.
- Missing QR OUT shift closing rule: no specific extra wait defined by source.

## 7. Recalculation policy (proposed)

Derived values change when approved overrides, active assignment or effective settings change; keep immutable before/after snapshots and source config version. Mark affected active approvals stale and require re-review rather than silently changing a Verified payroll row. Never recompute an already-exported historical file in place; issue a new export revision.
