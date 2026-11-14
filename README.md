# SiteGuard QR

SiteGuard QR records attendance at registered gates, routes shift exceptions through three approval tiers, and prepares the 23-column `06_QR_Timekeeper_Log` payroll handoff.

- **Gate kiosk.** USB scanner and camera input, signed static and rotating badges, terminal geofencing, and an encrypted offline outbox.
- **Verification.** Day and overnight shifts, anomaly detection, foreman and engineer review, timekeeper decisions, and justified corrections with raw punches retained.
- **Payroll.** CSV and XLSX with all attendance statuses, verified-hour totals, organization-wide employee holds, signed export receipts, a read-only payroll API, and a printable daily time record draft.
- **Administration.** Site and terminal enrollment, employee assignments, user scope, badge revocation, policy versions, and audit history.

## Run locally

Install Node.js 22+, Python 3.12, and Docker with Compose.

```bash
cp .env.example .env
# Generate a value with openssl rand -hex 48 and set SITEGUARD_SECRET in .env.
set -a
. ./.env
set +a
docker compose up -d --wait db
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
npm ci
npm run build
python -m siteguard migrate --runtime-role siteguard
python -m siteguard bootstrap --organization pilot --name "SiteGuard Pilot" --login admin
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) and sign in as the administrator created by the bootstrap command. Use the [operator guide](docs/engineering/OPERATIONS_GUIDE.md) to configure a site, enroll a gate, issue a worker badge, and complete a payroll period. Use HTTPS outside localhost for camera, location, and offline storage.

## Verify the build

```bash
npm test
npm run build
TEST_POSTGRES_URL="$MIGRATION_DATABASE_URL" python -m unittest discover -s tests -v
```

The PostgreSQL tests create and remove isolated databases and roles. Use a dedicated development or CI PostgreSQL instance. [Browser verification](docs/engineering/DEVELOPMENT.md) covers the offline kiosk, review chain, export download, and printable record.

## Deploy

Use the [Vercel setup guide](docs/engineering/VERCEL_DEPLOYMENT.md) for hosted PostgreSQL, runtime secrets, migrations, and readiness checks. The app also runs behind a TLS reverse proxy with Uvicorn and PostgreSQL.

Gate evidence is opt-in per site. The daily time record uses the Form 48 layout as a draft and leaves unrecorded lunch punches and undertime for agency completion. Payroll consumers must apply employee holds when they import the attendance table. See the [deployment checklist](docs/engineering/DEPLOYMENT_OPERATIONS.md) and [decisions](docs/engineering/DECISIONS_AND_OPEN_QUESTIONS.md).

## Specifications

| Topic | Document |
| --- | --- |
| Requirements and behavior | [Documentation index](docs/INDEX.md) · [PRD](docs/product/PRD.md) · [Functional specification](docs/specs/FUNCTIONAL_SPECIFICATION.md) |
| Attendance and security | [Timekeeping rules](docs/specs/BUSINESS_RULES.md) · [QR and offline protocol](docs/specs/QR_SECURITY_AND_OFFLINE.md) · [Security and privacy](docs/engineering/SECURITY_PRIVACY.md) |
| Approvals and handoff | [Workflow and roles](docs/specs/WORKFLOW_AND_ROLES.md) · [Payroll export contract](docs/specs/PAYROLL_EXPORT.md) |
| Engineering | [API](docs/api/API_CONTRACT.md) · [Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) · [Test plan](docs/engineering/TEST_PLAN.md) |
| Governance | [Contributing](CONTRIBUTING.md) · [Security reporting](SECURITY.md) · [Changelog](CHANGELOG.md) |

Source requirements come from the *SiteGuard QR Complete Technical & Commercial Blueprint*. See the [decision register](docs/engineering/DECISIONS_AND_OPEN_QUESTIONS.md) for defaults selected during implementation and policies that require operator or agency approval. The repository currently has no selected license.
