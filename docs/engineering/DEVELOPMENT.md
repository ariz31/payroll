# Developer guide and repository bootstrap

**Repository state (2026-11-14):** the repository has a **static HTML/CSS/JavaScript Vercel preview** in `public/`, an npm-based zero-dependency build check and GitHub Actions verification. No React frontend, FastAPI backend, database migrations or functional timekeeping tests exist. The stack below remains a **proposed bootstrap plan**. See [Vercel deployment](VERCEL_DEPLOYMENT.md).

## 1. Target stack (source)

- Frontends: **React 18**, **TypeScript**, **Tailwind CSS**; kiosk uses USB barcode scanner/webcam and Web Audio, workbench provides multi-tier review.
- Service: **Python 3.12**, **FastAPI** (token validation, pairing, rules, workflow, exports).
- Database: **PostgreSQL 16 + pgcrypto** (append-only attempts, write-once raw punches).

Libraries beyond these (e.g., React bundler, Python dependency manager, ORM, Alembic, test framework, object storage, queue broker, XLSX serializer, auth stack) require ADR selection and actual dependency lockfiles.

## 2. Suggested monorepo layout (not yet created)

```text
/
├── README.md
├── docs/
│   ├── product/
│   ├── specs/
│   ├── architecture/
│   ├── api/
│   ├── engineering/
│   └── commercial/
├── apps/
│   ├── kiosk/             # React + TS capture terminal
│   └── workbench/         # React + TS audit/review portal
├── services/
│   └── api/               # FastAPI, Pydantic, domain rules
│       ├── src/
│       └── tests/
├── db/
│   ├── migrations/        # audited schema + trigger migrations
│   └── seed/              # synthetic fixture data
├── tests/
│   ├── integration/
│   ├── e2e/
│   └── contract/
├── infra/                 # deploy manifests when selected
└── .github/workflows/     # CI when tooling exists
```

## Current preview commands

```bash
npm ci
npm run build  # verifies static assets and JavaScript syntax
npm test       # same lightweight smoke verification
python3 -m http.server 4173 --directory public
```

Open http://localhost:4173 to inspect the preview. No environment variables or external services are required. The current app is a temporary static deployment shell, **not a replacement for the React 18/TypeScript target architecture**.

## 3. Initial implementation steps

1. Approve prioritized [open decisions](DECISIONS_AND_OPEN_QUESTIONS.md) on time, devices, crypto, privacy and data retention.
2. Scaffold isolated kiosk, review UI, FastAPI service and PostgreSQL local environment; pin exact dependency versions and commit lockfiles.
3. Implement migrations and test **append-only audit** and **raw punch write-once triggers** first. Add application-level permission checks as defense in depth.
4. Implement terminal enrollment, employee/badge provisioning, signed validation, geofence and scan idempotency.
5. Build pure time engine functions with timezone-aware instants and fixture tests; avoid database-dependent arithmetic where possible.
6. Implement review event state machine and evidence access; prevent direct status writes.
7. Implement CSV v1 exact schema and XLSX with golden-header contract tests before exposing payroll download.
8. Add device offline outbox, signing/encryption, sync receipts and reconciliation.
9. Add rollout/monitoring, DR, key rotation, formal security/privacy review and legal/policy sign-off.

## 4. Local developer workflow (once tooling exists)

A future README should contain **tested commands** for:

- bootstrapping language environments and dependencies,
- starting PostgreSQL and applying versioned migrations,
- seeding synthetic employees/sites and signing test badges,
- running FastAPI and both React apps,
- running lint, typecheck, unit/integration/E2E/security tests,
- previewing exports and verifying the source six-case fixture.

Do not add copied “npm run dev” or “uvicorn” commands as operational facts without the scripts/configuration. Prefer scripted setup with pinned versions, small deterministic synthetic data, and no live employee photos.

## 5. Code organization guidance

- Domain logic separated from HTTP, SQL and UI; tests use pure deterministic event/shift functions.
- Time is **offset-aware**; choose IANA timezone for each site and preserve original capture/receipt instants. Export HH:MM only at boundary.
- Raw journal and decision events are immutable; re-computations create versioned projections.
- Use DB transactions/locks + idempotency keys for scan replay and review concurrency.
- Keys held in managed secrets or approved HSM/KMS, never bundled into React or committed.
- Logs redact QR payloads, signing secrets, raw images and unnecessary personal data.
- Feature flags for static/dynamic badges, camera policy, and auto-verify are versioned and audited.

## 6. Suggested engineering standards

- FastAPI: typed Pydantic models, semantic request validation, structured errors, generated OpenAPI matched to tests.
- TypeScript: strict mode, accessible kiosk feedback, no untyped role checks, robust offline error handling.
- SQL: migrations reviewed by security/DB owner; privileges, triggers and policies tested against UPDATE/DELETE/TRUNCATE attacks.
- Security: rate limits, scoped RBAC, secret rotation, dependency scanning, audit-safe logging.
- Quality: tests for edge cases and property-based invariants; deterministic local clock injection; golden CSV/XLSX snapshots.

## 7. Contribution and release process

See [Contributing](../../CONTRIBUTING.md). Require design review before protocol or schema changes, automated test evidence for new claims, documented downgrade/rollback strategy and a new export version for any breaking column change. Never promote proposed docs to “implemented” until code and tests exist.
