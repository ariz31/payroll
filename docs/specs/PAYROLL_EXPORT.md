# Payroll handoff: 06_QR_Timekeeper_Log v1

**Status:** **exact 23-column schema is required** by blueprint §5. Serialization policies below are proposed unless specified.

## 1. Purpose and gating

The exported file is an **attendance verification input**, not a payslip or wage engine. UI shows the **exact Pending Review row count** before export. Export **all** rows with current `Timekeeper_Status`; downstream Power Query / ERP must:

- Sum payable `Calc_Reg_Hrs`, `Calc_OT_Hrs` and `Calc_Night_Hrs` only when `Timekeeper_Status = "Verified"`.
- Exclude `Disputed / Rejected` rows from payable totals.
- Place **AUDIT HOLD** on every `Emp_ID` with **any** `Pending Review` row in the **active Pay_Period**, even if that employee has other Verified rows. Do not release that employee’s pay until resolved through approved procedure.

The source requires hold **behavior** but does not include an “Audit_Hold” column. Keep hold metadata in UI/receipt/companion report or downstream recomputation; **do not add a 24th column** to the v1 schema.

## 2. Exact column order and format

| # | Column | Type / source rule |
| --- | --- | --- |
| 1 | `Scan_ID` | Unique shift identifier, e.g., `QR-2611-001` |
| 2 | `Pay_Period` | String `YYYY-MM` |
| 3 | `Work_Date` | Shift-start date `YYYY-MM-DD` |
| 4 | `Emp_ID` | Unique employee ID string |
| 5 | `Full_Name` | Legal name string |
| 6 | `Department` | Organizational department/trade string |
| 7 | `QR_Terminal_ID` | Recorded terminal ID string |
| 8 | `Shift_Type` | Exact: `Day Shift` or `Night Shift` |
| 9 | `Raw_QR_Time_In` | Immutable raw time `HH:MM`, blank if absent |
| 10 | `Raw_QR_Time_Out` | Immutable raw time `HH:MM`, blank if absent |
| 11 | `Break_Mins` | Integer, default `60` |
| 12 | `TK_Adjusted_In` | Timekeeper override `HH:MM`, else blank |
| 13 | `TK_Adjusted_Out` | Timekeeper override `HH:MM`, else blank |
| 14 | `Effective_In` | Adjusted in if present else raw in; `HH:MM` / blank |
| 15 | `Effective_Out` | Adjusted out if present else raw out; `HH:MM` / blank |
| 16 | `Net_Worked_Hrs` | Net after unpaid break, decimal 2 places |
| 17 | `Calc_Reg_Hrs` | `min(8.00, Net_Worked_Hrs)`, decimal 2 places |
| 18 | `Calc_OT_Hrs` | `max(0.00, Net_Worked_Hrs - 8.00)`, decimal 2 places |
| 19 | `Calc_Night_Hrs` | Source formula night-shift eligible regular hours, decimal 2 places |
| 20 | `QR_Anomaly_Alert` | `OK` / `MISSING QR OUT` / `MISSING QR IN` / `LATE (>5m)` / `HIGH OT (>2h)` |
| 21 | `Timekeeper_Status` | `Verified` / `Pending Review` / `Disputed / Rejected` |
| 22 | `Verified_By_TK` | Authenticated timekeeper username/ID; blank until applicable |
| 23 | `TK_Verification_Notes` | Review/override/rejection justification string; blank when not applicable |

**Machine-checkable v1 header** (one line, exact case and order):

```csv
Scan_ID,Pay_Period,Work_Date,Emp_ID,Full_Name,Department,QR_Terminal_ID,Shift_Type,Raw_QR_Time_In,Raw_QR_Time_Out,Break_Mins,TK_Adjusted_In,TK_Adjusted_Out,Effective_In,Effective_Out,Net_Worked_Hrs,Calc_Reg_Hrs,Calc_OT_Hrs,Calc_Night_Hrs,QR_Anomaly_Alert,Timekeeper_Status,Verified_By_TK,TK_Verification_Notes
```

## 3. Proposed CSV/XLSX serialization contract

- CSV: UTF-8, RFC 4180-style quoting/escaping; literal comma/newline/quote protected, LF or CRLF consistently selected.
- Dates local ISO `YYYY-MM-DD`; times zero-padded 24h `HH:MM`; decimal invariant dot separator and exactly 2 places (e.g., `0.08`).
- Absence represented as **empty cell**, not text `NULL`, unless owner chooses alternative. Example raw missing out in Sofia Chen case is blank, while adjusted out is `17:00`.
- Protect against CSV/spreadsheet formula injection for user-controlled names/notes. Do not change semantic values silently; choose a documented safe encoding/import strategy and round-trip tests.
- XLSX: lock header/order and number/text formatting to avoid Excel eating leading zeros in IDs; preserve date/time metadata. Timezone can be described in workbook metadata/receipt but cannot add a v1 column.
- Deterministic order (proposed: Work_Date, Emp_ID, Scan_ID) and snapshot/export ID; stored artifact checksum and counts to prove which state was exported.
- No `Verified_Timestamp`, `Cost_Code`, photo URL, extra “hold” flag or raw event diagnostics in the required flat table. Put such data in separately versioned reports/metadata if required.

## 4. Overnight and adjustments

For night shift crossing midnight, raw/effective time fields are displayed as local HH:MM, but elapsed hour computation must use full internally stored date+time instants and **Work_Date anchored at shift start**. Time-only exported fields alone cannot unambiguously reconstruct multiple nights.

Adjustments do not alter `Raw_QR_Time_In` or `Raw_QR_Time_Out`. For QR-2611-003: raw in `08:01`, raw out blank, adjusted out `17:00`, effective out `17:00`, calculated regular `7.98`, Verified with mandatory notes.

## 5. Worked period 2026-11

The six source cases are enumerated in [Business rules](BUSINESS_RULES.md) and [Tests](../engineering/TEST_PLAN.md). Only QR-2611-001 / 002 / 003 count as verified for provided totals:

| Aggregate | Reference value |
| --- | ---: |
| Verified regular hours | **23.98** |
| Verified overtime hours | **0.21** |
| Verified night hours | **8.00** |
| Excluded disputed row | QR-2611-004 (EMP-1004) |
| Employees on audit hold | EMP-1005, EMP-1006 |
| Pending shift rows | **2** |

**Important:** the 23-column schema lacks a separate “payroll release” marker; even if a Verified row exists for a held employee, downstream systems must independently apply the **employee-level hold** across that period.

## 6. Export preflight / acceptance

- [ ] Header exactly matches the one-line v1 string above; exactly 23 cells in every row.
- [ ] No data loss in Unicode names, notes, empty timestamps, or unusual leading-zero IDs.
- [ ] Validate enum values, Work_Date and pay period format, regular/OT/night rounding and shift type.
- [ ] Show exact Pending Review count and hold employee list before handoff.
- [ ] Record creation actor/time, export revision, digest, row counts by state and active config version in a separate receipt.
- [ ] Recompute verified totals separately; assert reference fixture = 23.98 / 0.21 / 8.00.
- [ ] Re-exporting after a resolution produces new immutable export revision rather than overwriting prior evidence.
- [ ] Coordinate with payroll consumer on import locale, formula safety, hold gating and legal wages interpretation.

## 7. Form 48

The blueprint lists a printable Civil Service Form No. 48 generator as a target. Form layout, signatory declarations, official approval, attendance conversion and jurisdiction-specific requirements have **not** been supplied. Build only after owner/agency compliance review; keep it a separate output contract.
