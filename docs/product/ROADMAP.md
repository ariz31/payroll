# Engineering implementation roadmap

**Status:** recommended sequence; no source code is present at documentation baseline. This is a build plan, not evidence of completion.

## Build phases

| Phase | Scope | Exit gate |
| --- | --- | --- |
| 0 — Governance | Resolve ADRs on temporal model, privacy, badge signing, offline trust and legal policy; choose license | Decisions approved; threat model and data classification reviewed |
| 1 — Foundation | Create React/TypeScript frontend(s), FastAPI service, PostgreSQL migrations, auth, CI, local stack | Fresh clone boots; lint/test/migrations reproducible |
| 2 — Immutable evidence | Employee/site/terminal registry, signing/validation, scan ingest, append-only audit, write-once shift punches | DB tamper tests and invalid token tests pass |
| 3 — Time engine | Shift assignment, timezone-aware cross-midnight pairing, debounce, net/OT/night calculations, anomaly priority | All supplied fixture totals and boundary tests pass |
| 4 — Workbench | RBAC, Tier 1/2/3 decisions, adjustment validation, status changes, notes, KPIs | Approval and rejection abuse tests pass |
| 5 — Offline kiosk | Device enrollment, durable encrypted outbox, sequence/hash, idempotent server sync, failure/reconciliation UX | Network partition/reboot/clock drift test suite passes |
| 6 — Payroll handoff | CSV/XLSX exact 23 columns, verified-only total, holds, export receipts, Form 48 proof | Golden file and Finance sign-off |
| 7 — Hardening | Load tests, key rotation, backups/restore, monitoring, privacy notices, pentest, production runbooks | Release checklist passed; pilot data use approved |

**Dependency:** no production pilot should begin before phases 0–7 gates relevant to employee data are met. Commercial 15-day shadow pilot from the blueprint is an external go-to-market timeline, not a software delivery promise.

## Thin vertical slice

A practical first demonstration: one enrolled employee + one terminal → validated signed clock-in/out → immutable scan journal → calculated hours → foreman/engineer/timekeeper approvals → downloadable exact-header CSV. Start with online-only, then add explicit offline trust and camera controls once risk decisions are completed.

## Backlog epics

- E1: Tenant, employees, assignments, projects, cost codes and terminal provisioning.
- E2: Badge issuance, rotation/revocation, signing keys and device credentials.
- E3: Audit ingest, time synchronization, debounce and shift association.
- E4: Clock rules, exceptions, configuration versioning and re-evaluation.
- E5: Workflow, role permission matrix and evidence viewer.
- E6: Offline sync semantics, sequence/hashing and support recovery.
- E7: Payroll exports, audit holds, Form 48 rendering.
- E8: Observability, security, retention and compliance.

## Definition of done for each epic

- Behavior linked to a requirement ID and an approved ADR where needed.
- API schema, data migration and backward-compatibility plan documented.
- Unit, property, integration and negative security tests included.
- No endpoint permits destructive edits to raw evidence.
- Access checks, audit logging, timezone handling and failure paths reviewed.
- User-facing error states and accessibility reviewed.
- Runbook, changelog and documentation updated to reflect **implemented** behavior.

## First milestones to track

1. Decide what an “offline validated scan” means without network or trusted time.
2. Adopt one canonical time model: timestamps with timezone and shift work-date anchor, with HH:MM used only at export boundary.
3. Formalize reviewer routing and its exception/escalation policy.
4. Freeze export v1 and its sample fixture, then generate golden CSV/XLSX files through tests.
5. Obtain legal/privacy review for camera stills, government DTR and biometric-related practices.
