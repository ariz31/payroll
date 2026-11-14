# Changelog

All notable changes should be recorded here. Versions refer to **documentation/specification** until an application is released.

## [Unreleased]

### Added
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
- No application runtime, database migrations, test suite, CI or production deployment is included.
- Some blueprint requirements have unresolved security, privacy, policy and calculation interpretation decisions. See [Decisions](docs/engineering/DECISIONS_AND_OPEN_QUESTIONS.md).

## Format

When software versions exist, use [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) categories and semantic versioning appropriate to the project. Do not treat documentation revision dates as released software versions.
