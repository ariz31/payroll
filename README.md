# SiteGuard QR — Workforce Timekeeping & Payroll Audit Handoff

> **Project stage:** Initial deployable preview. The repository now contains a **dependency-free static application shell** in `public/`, with a working Vercel build check. No QR scanning, backend, database, employee records, approvals or payroll exports are implemented.

SiteGuard QR is a proposed tamper-evident QR attendance and timekeeper verification platform for construction sites and government engineering offices. Its purpose is to capture clock-in/clock-out events, preserve original evidence, detect exceptions, route approvals, and prepare a **23-column payroll-ready attendance handoff**. It **does not calculate taxes, generate payslips, or disburse money**.

**Source of requirements:** *SiteGuard QR — Complete Technical & Commercial Blueprint* (7-page specification supplied by the project owner, November 2026). This repository's documentation interprets the blueprint; where its implementation details are unspecified or ambiguous, docs label the choices as **proposed** or **open decisions**.

## Documentation map

| Document | Purpose |
| --- | --- |
| [Documentation index](docs/INDEX.md) | Reading order and documentation status |
| [Product requirements](docs/product/PRD.md) | Users, scope, requirements, acceptance criteria |
| [Functional specification](docs/specs/FUNCTIONAL_SPECIFICATION.md) | End-to-end expected behavior |
| [Business rules](docs/specs/BUSINESS_RULES.md) | Shift pairing, hours, alerts, calculations |
| [QR, kiosk and offline specification](docs/specs/QR_SECURITY_AND_OFFLINE.md) | Badge format, validation, replay, sync |
| [Approval workflow and permissions](docs/specs/WORKFLOW_AND_ROLES.md) | Three-tier review, adjustments, locks |
| [Payroll export contract](docs/specs/PAYROLL_EXPORT.md) | Exact 06_QR_Timekeeper_Log columns and audit holds |
| [Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) | Components, trust boundaries and flows |
| [Data model](docs/architecture/DATA_MODEL.md) | Proposed entities, invariants, example SQL |
| [API contract](docs/api/API_CONTRACT.md) | **Proposed** REST endpoints and payloads |
| [Development guide](docs/engineering/DEVELOPMENT.md) | Suggested project layout and bootstrap plan |
| [Deployment and operations](docs/engineering/DEPLOYMENT_OPERATIONS.md) | Planned environments, monitoring, recovery |
| [Vercel preview deployment](docs/engineering/VERCEL_DEPLOYMENT.md) | Current deployable static site, configuration and deployment steps |
| [Security and privacy](docs/engineering/SECURITY_PRIVACY.md) | Threat model, sensitive snapshots, audit controls |
| [Test strategy and fixtures](docs/engineering/TEST_PLAN.md) | Acceptance matrix and six blueprint examples |
| [Decisions and open questions](docs/engineering/DECISIONS_AND_OPEN_QUESTIONS.md) | Unresolved ambiguities and ADR process |
| [Implementation roadmap](docs/product/ROADMAP.md) | Ordered build phases and definition of done |
| [Commercial overview](docs/commercial/COMMERCIAL_OVERVIEW.md) | Source-provided pricing and pilot assumptions |
| [Contributing](CONTRIBUTING.md) · [Security reporting](SECURITY.md) · [Changelog](CHANGELOG.md) | Repository governance |

## Planned architecture

```text
QR badges (dynamic signed / static signed)
                   |
USB scanner or camera -> React 18 + TypeScript kiosk
                   |           | (sealed local outbox while offline)
                   v           v
           Python 3.12 / FastAPI
           - token + site/terminal validation
           - scan audit and debounce
           - shift pairing + anomaly calculation
           - 3-tier review + payroll gating
                   |
          PostgreSQL 16 + pgcrypto
          append-only scan audit + immutable raw punches
                   |
        CSV / XLSX 06_QR_Timekeeper_Log
                -> downstream payroll/ERP
                  (Verified rows only)
```

The proposed frontend uses Tailwind CSS. The reference workday is 08:00–17:00, and night shift is 22:00–07:00, each with a 60-minute unpaid break. Normal regular hours are capped at 8.00; late threshold is **more than 5 minutes**; high overtime is **more than 2.00 hours**; duplicate-scan debounce is 300 seconds. See [business rules](docs/specs/BUSINESS_RULES.md) for precise treatment.

## Core protections (required, not yet implemented)

1. Keep every accepted, rejected and debounced scan in an append-only raw audit ledger.
2. Do not overwrite or delete raw QR clock-in/clock-out timestamps. Corrections live in `TK_Adjusted_In` / `TK_Adjusted_Out` and require an authenticated timekeeper, explanation and server timestamp.
3. Use HMAC-SHA256-signed dynamic (30-second) or static badge tokens, terminal geofencing, and replay defenses.
4. Preserve ordered, idempotent offline scan ingestion without silently trusting device clocks.
5. Require field endorsement, departmental/project review and final timekeeper verification where applicable.
6. Export every reviewed/pending/disputed record with exact status; **payable hours are summed only for `Verified` rows**. Any employee with a `Pending Review` row in a period is on **AUDIT HOLD** for that period.

## Run the minimal preview

The current Vercel-ready preview is a **static UI**, not the future React/FastAPI application. Its navigation works locally, but attendance and payroll capabilities are intentionally inactive.

```bash
npm ci
npm run build
npm test
# Preview public/index.html using any static server, for example:
python3 -m http.server 4173 --directory public
```

Open `http://localhost:4173`. There are **no application dependencies or environment variables** for this preview. The build validates required assets and JavaScript syntax instead of compiling a framework.

**Deploy:** import [ariz31/payroll](https://github.com/ariz31/payroll) into Vercel. Repository root is the project root; `vercel.json` sets Framework Preset **Other**, Build Command **`npm run build`**, Output Directory **`public`**. A GitHub/Vercel connection is required to create a live deployment. Detailed instructions: [Vercel deployment](docs/engineering/VERCEL_DEPLOYMENT.md).

A recommended future application layout is `apps/kiosk`, `apps/workbench`, `services/api`, `db/migrations`, and `tests`; see [development](docs/engineering/DEVELOPMENT.md).

For implementation work:

1. Review the [PRD](docs/product/PRD.md), [open decisions](docs/engineering/DECISIONS_AND_OPEN_QUESTIONS.md), and [security requirements](docs/engineering/SECURITY_PRIVACY.md).
2. Choose and record decisions on temporal arithmetic, badge provisioning, offline trust, sensitive image handling, and compliance.
3. Implement the event ledger and invariants before UI shortcuts, using the [test plan](docs/engineering/TEST_PLAN.md) as the baseline.
4. Add reproducible setup, migration, test and deployment commands **when real tooling exists**. Never publish example credentials as usable production configuration.

## Scope and caveats

- The blueprint provides target behavior, **not evidence of a deployed or compliant system**. The static Vercel preview is a navigation shell only, not a working timekeeping service.
- GPS verification of a fixed kiosk proves terminal position, **not automatically the worker's identity**; face snapshots and identity checks require privacy review and consent/notice policy.
- Government Form 48 compatibility is a **target output**, not a legal certification. Attendance, overtime, night differential and privacy requirements must be reviewed for the actual jurisdiction, employer and collective/contractual rules.
- The blueprint's commercial leakage estimates, prices and ROI illustration are planning assumptions, not verified outcome guarantees.

## License

**No license has been selected.** Until the owner adds an explicit license, reuse rights are not granted merely because the repository is publicly readable.

---
**Documentation status:** initial product and engineering specification; changes must retain raw-audit guarantees and exact export column names.
