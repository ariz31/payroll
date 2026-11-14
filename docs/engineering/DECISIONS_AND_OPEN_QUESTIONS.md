# Design decisions, ambiguities and ADR register

**State:** initial open-decision log. The source blueprint gives goals and sample logic, not a fully executable protocol. Unresolved questions are visible here by design.

## 1. Critical decisions before production

| ADR | Priority | Decision required | Why it matters / recommended next step |
| --- | --- | --- | --- |
| ADR-001 | P0 | Canonical timezone/time model | Store full timezone-aware instants; decide DST/UTC offset behavior; HH:MM export only |
| ADR-002 | P0 | Offline trust and delayed dynamic QR validation | 30s tokens expire while offline; select time attestation, max age, quarantine/replay policy |
| ADR-003 | P0 | QR signing format and secrets | Source uses truncated 16hex HMAC; define canonical payload, key derivation, versioning, rotation and rate limits |
| ADR-004 | P0 | Replay and static badge protection | Static printed QR is copyable; dynamic ±1 window is reusable absent replay store |
| ADR-005 | P0 | Gate image lawful basis and lifecycle | “Silent” capture creates privacy risk; require notice, retention, access and alternatives |
| ADR-006 | P0 | Review state machine and auto-verify | How clean OK records traverse/bypass three tiers; who may reopen after export |
| ADR-007 | P0 | Rule for clock-out missing after shift window | Source lacks closing grace and which late sync could update it |
| ADR-008 | P0 | Export employee-hold enforcement | v1 format has no hold column; define downstream signal vs computed period check |
| ADR-009 | P0 | Night differential computation law/policy | Source says night-shift regular hrs, not actual clock-window premium math |
| ADR-010 | P0 | Raw evidence retention vs privacy deletion | Append-only guarantees and data subject rights need legal design |
| ADR-011 | P1 | Badge provisioning payload | Source says profile fields encoded, while stated QR syntax only contains Emp_ID |
| ADR-012 | P1 | Duplicate exact boundary / reentrant punches | 300s inclusive/exclusive, multiple daily shifts, duplicate-out and cross-terminal cases |
| ADR-013 | P1 | Duration ceiling and source modulo 24 | Avoid wrapping 25h shift to 1h; define invalid/outlier handling |
| ADR-014 | P1 | Rounding and break eligibility | Decimal mode, break applicability to short/missing shifts, partial minutes |
| ADR-015 | P1 | Tier authorization and cost code | Approvers per employee/site/project, conflicts, delegation and dispute escalation |
| ADR-016 | P1 | Settings effective time and re-evaluation | Active exceptions only? Historical Verified rows/existing exports must remain auditable |
| ADR-017 | P1 | Platform, auth, hosting, DR and SLOs | No repo tooling exists; select libraries/vendor and environment assumptions |
| ADR-018 | P1 | Government Form 48 acceptance | Layout, signatories, form revision, governing jurisdiction and agency sign-off |
| ADR-019 | P1 | CSV/XLSX absence and formula safety | Blank vs literal NULL, preservation of ID strings, formula mitigation |
| ADR-020 | P2 | KPI definitions and releases | Does Total Scans mean attempts or shifts; confirmed payroll release vs verified metrics |

## 2. Source-consistency notes

### Token payload mismatch (blueprint §3.1)

Text describes a badge encoding Emp_ID, Full_Name, Department, Cost_Code and Assigned_Shift. The formal QR text format names only Emp_ID, Step/STATIC and HMAC. **Not equivalent.** Proposed approach: server lookup of other attributes from Emp_ID; confirm before issuing badges.

### Clock arithmetic (blueprint §3.3)

Formula uses elapsed “mod 24h,” but mod can conceal invalid >24-hour spans. Worked example requires correct midnight crossing. **Proposed**: authoritative absolute instants and explicit validity range; same six fixture outcomes.

### Night premium (blueprint §§3.3, 5)

Source labels night hours as eligible 22:00–07:00 but computes night hours as all regular hours for a `Night Shift`. This is **not** the same as actual clock-window overlap, and no legal rate or jurisdiction is specified. Decide whether `Calc_Night_Hrs` is shift-class hours or legally payable night premium basis; version the schema/logic if changed.

### Duplicate versus replay (blueprint §3.1–3.2)

“Replayed phone screenshots” are to be rejected, while dynamic tokens tolerate ±1 window and static tokens are intrinsically reusable. Ordinary HMAC validation alone cannot identify all replays; define server replay semantics and anti-cloning caveats.

### Geofence versus employee presence (blueprint §3.1)

A fixed kiosk’s GPS geofence does not prove a worker is physically present or identity matched. Define camera/supervisor controls and do not market it as foolproof anti-buddy-punching.

### Approvals and v1 export (blueprint §§4–5)

Three approval tiers exist, but export has one `Timekeeper_Status` field and no tier columns. Internal approvals must be separate auditable events, projected into three final statuses only. `Verified_Timestamp` is required internally but **excluded from v1 export**.

### Payroll hold versus “all rows exported” (§5)

All rows, including pending, must be exported; actual payable sums use Verified rows only and **employee-level audit holds** apply. Export completion does not mean pay clearance.

### Commercial figures (§7)

Source supplies pricing, leakage estimates and eight-day payback, but underlying market/evidence and payback method are not documented. Treat as hypotheses until verified.

## 3. ADR template for future decisions

Create `docs/architecture/adr/NNN-short-title.md` per decision:

```markdown
# ADR-NNN: Short title
Status: Proposed | Accepted | Superseded
Date: YYYY-MM-DD
Owners: Product / Engineering / Privacy / Payroll

## Context
Requirement IDs and source sections; unresolved risk.

## Options considered
Option A/B with tradeoffs.

## Decision
Exact protocol, invariant, threshold or policy and why.

## Consequences
Threat, compatibility, migrations, monitoring, legal sign-off.

## Validation
Tests and evidence required; how to roll back or supersede.
```

Do not close an ADR merely by copying a suggested solution into code; obtain owner approval where payroll or privacy policy is involved.
