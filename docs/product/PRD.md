# Product requirements document (PRD)

**Product:** SiteGuard QR — Time-In/Time-Out and Timekeeper Verification System  
**Version:** 0.1 documentation baseline · **Status:** planned · **Source:** supplied blueprint §§1–6.

## 1. Product problem and goal

Construction sites and government engineering offices need reliable attendance evidence where fingerprints and continuous connectivity may be unsuitable. This product aims to reduce unverified scans, missing punches, unauthorized overtime and manual consolidation by providing signed badge capture, audit-grade preservation, exception review and a payroll-ready handoff.

**Success condition:** every exported attendance record is traceable back to immutable scan events and its approval history; payroll consumers can include only verified hours and block employees with unresolved period exceptions.

## 2. Users, jobs, and boundaries

| Persona | Primary job |
| --- | --- |
| Employee | Present an assigned QR badge at a registered gate; receive feedback |
| Site foreman (Tier 1) | Attest crew presence, field conditions and explanations |
| Project engineer / department head (Tier 2) | Validate cost code and overtime justification |
| Central timekeeper (Tier 3) | Compare evidence, correct effective punch times without overwriting raw, finalize |
| Admin | Configure sites, schedules, devices, thresholds, employees and permissions |
| Payroll integrator / auditor | Download machine-readable period data and inspect verification/hold state |

**In scope (required):** dynamic/static signed QR badges; fixed-terminal geofence; photo evidence target; USB/webcam kiosk; audio/visual feedback; offline outbox; 300-second duplicate suppression; paired overnight shifts; anomaly queue; immutable raw timestamps; three-tier review; bulk verify; 23-column CSV/XLSX; Form 48 print target; employee-level audit holds.

**Out of scope:** tax withholding, statutory contribution computation, salary rates, pay runs, payslips, bank disbursements, and automatic legal certification of attendance or Form 48. SSO and enterprise ERP integration appear as commercial tier targets and need their own design.

## 3. Functional requirements with acceptance targets

| ID | Priority | Requirement and acceptance |
| --- | --- | --- |
| FR-001 | P0 | Register active employees with Emp_ID, name, department, shift and project cost code; only active assignments accepted |
| FR-002 | P0 | Validate signed dynamic 30s (±1 window) or signed static badges; reject invalid/expired credentials and preserve rejection evidence |
| FR-003 | P0 | Bind each accepted scan to an approved terminal/site; evaluate terminal geofence using configured coordinates |
| FR-004 | P0 | Journal accepted, rejected and debounced attempts with immutable timestamps and causality |
| FR-005 | P0 | Suppress accidental scans within 300 seconds without changing matched punches; emit IGNORED_DEBOUNCE audit action |
| FR-006 | P0 | Pair start/end of overnight shifts under shift-start Work_Date; prevent negative/unbounded durations |
| FR-007 | P0 | Queue sealed offline events in stable order; retry idempotently; reconcile server timestamps and clock integrity |
| FR-008 | P0 | Compute effective in/out, net/regular/OT/night hours and anomaly priority from configured rules |
| FR-009 | P0 | Queue missing, late, high OT and clean scans; apply manual/bulk or configured auto-verify policy |
| FR-010 | P0 | Enforce three departmental review tiers and authenticated final timekeeper disposition |
| FR-011 | P0 | Preserve raw punch fields; overrides require actor, non-empty reason and server-side verified timestamp |
| FR-012 | P0 | Export exact 23-column 06_QR_Timekeeper_Log CSV/XLSX including pending and disputed statuses |
| FR-013 | P0 | Exclude disputed rows from payable aggregation; audit-hold any employee with active-period pending rows |
| FR-014 | P1 | Workbench KPI cards: total scans, verified, pending, disputed/rejected, missing outs, verified regular/OT hours |
| FR-015 | P1 | Printable Civil Service Form 48 DTR target, subject to jurisdiction/form review |
| FR-016 | P1 | Evidence image capture and badge comparison with data minimization and controlled access |
| FR-017 | P1 | Admin panel persisted in system_config and re-evaluation of active exception queues on updates |
| FR-018 | P1 | Signed, queryable verification/export audit history and operational reporting |
| FR-019 | P2 | SSO, ERP/Payroll API, private/on-premise deployment |

P0 denotes necessary for a trustworthy initial handoff, not “already available.” Unknown operational details remain tracked in the decision log.

## 4. Nonfunctional requirements

| ID | Required property | Measure / qualification |
| --- | --- | --- |
| NFR-01 | Data integrity | Raw punch fields and raw audit cannot be edited/deleted through UI, API or privileged application role; DB tests cover triggers |
| NFR-02 | Resilience | Offline outbox retains events across refresh/restart and retries safely, with explicit storage exhaustion/failure state |
| NFR-03 | Idempotence | Replayed event IDs do not create duplicate punches or duplicate ledger entries |
| NFR-04 | Performance | Blueprint targets sub-second feedback at kiosk; measure on target hardware/network, do not promise exact SLO until benchmarked |
| NFR-05 | Security | Server validates authority, signatures, time windows, tenant/site scope and every approval transition |
| NFR-06 | Privacy | Snapshot processing, retention, notice, access, consent/legal basis and incident response approved before real employee data |
| NFR-07 | Observability | Alert on ingestion failures, queue backlog, clock skew, export errors and unauthorized write attempts |
| NFR-08 | Reproducibility | Automated migration/test/deploy pipeline and fixture-based calculations before production |
| NFR-09 | Interoperability | Stable CSV header/order, locale-independent dates/decimals and Power Query import semantics |

## 5. Critical workflows

1. **Provision:** administrator registers worker, assignment, site, registered terminal and badge mode.
2. **Scan:** terminal presents signed token; validation and immutable audit happen before accepted punch mutation.
3. **Pair:** shift engine associates in/out to single anchored Work_Date; optional offline reconciliation.
4. **Classify:** compute hours and highest-priority anomaly; enqueue review if needed.
5. **Review:** foreman → engineer/head → central timekeeper; reason and immutable decision history mandatory.
6. **Handoff:** export all statuses, show pending count, mark employee audit holds, downstream totals from Verified only.

## 6. Initial release acceptance

- Six supplied reference scenarios pass with exact rounding and expected status/holds (see [Test plan](../engineering/TEST_PLAN.md)).
- Malformed/replayed/expired tokens and geofence violations cannot mutate paired hours.
- Every correction/dispute records authenticated actor, meaningful notes and server timestamp without modifying original evidence.
- Forbidden transitions are rejected at **both API and database enforcement levels**.
- Online/offline duplicate delivery yields equivalent ledger and attendance state.
- The export header/order matches [Payroll export](../specs/PAYROLL_EXPORT.md) exactly, with same totals for CSV and XLSX.
- Security/privacy reviewers sign off on actual data processing and deployments before a live rollout.

## 7. Unresolved policy questions

Clock-out event attribution, overnight duration ceiling, screenshot replays, role scope, clock trust, multi-site workers, period cutoff, daylight-saving treatment, photo retention, and jurisdiction-specific night differential remain explicit design decisions. See [Decisions and open questions](../engineering/DECISIONS_AND_OPEN_QUESTIONS.md).
