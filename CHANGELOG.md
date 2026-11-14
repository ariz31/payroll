# Changelog

## 1.0.0

- Added the PostgreSQL-backed FastAPI service and React workbench for Vercel and self-hosted deployment.
- Implemented employee, terminal, badge and policy administration, signed static and rotating badges, geofenced gate capture, and encrypted offline sync.
- Added scoped three-tier reviews, non-destructive corrections, bulk and automatic verification, and append-only audit history.
- Added versioned 23-column CSV/XLSX exports with employee holds, checksums and signed receipts, and a printable Form 48 draft.
- Added revocable, site-scoped payroll integration credentials and paginated release-eligible totals.
- Added scoped quarantine reconciliation with permanent reasons and optional links to pending shifts.
- Added optional OIDC and retained camera evidence with audited reads and scheduled cleanup.


All notable changes should be recorded here. Versions refer to **documentation/specification** until an application is released.

## [Unreleased]

### Added
- Minimal Vercel-deployable static app shell (`public/`), with responsive navigation and clearly marked placeholder modules.
- Zero-dependency npm build validation, Vercel project configuration and CI verification workflow.
- Vercel deployment instructions (no hosting connection or production URL claimed).
- Initial README and documentation index, with explicit “unimplemented” status.
- PRD, functional specification and prioritized engineering roadmap.
- Architecture, logical schema and non-destructive database integrity requirements.
- Detailed QR token, kiosk/geofence/offline sync and replay analysis.
- Business rules, six reference fixtures and anomaly priority.
- Three-tier approval workflow, permissions and mandatory correction audit.
- Exact 23-column 06_QR_Timekeeper_Log payroll contract, status/hold semantics.
- Proposed FastAPI endpoints and request/response examples.
- Development, deployment, security/privacy, test plan, open-decision register and commercial context.
- Contributor and security reporting guidance.

### Known limitations
- The static preview has a runnable UI and smoke checks, but no React/FastAPI domain application, database migrations, end-to-end feature tests, or verified live Vercel deployment is included.
- Some blueprint requirements have unresolved security, privacy, policy and calculation interpretation decisions. See [Decisions](docs/engineering/DECISIONS_AND_OPEN_QUESTIONS.md).

## Format

When software versions exist, use [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories and semantic versioning appropriate to the project. Do not treat documentation revision dates as released software versions.
