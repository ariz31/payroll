# Development

Start with the [README](../../README.md) for the local Docker and application commands.

| Path | Contents |
| --- | --- |
| `frontend/` | React workbench and terminal kiosk, Web Crypto/IndexedDB outbox, service worker |
| `app.py`, `siteguard/` | FastAPI, authentication, registry, scan ingestion, timekeeping, reviews and exports |
| `db/migrations/` | Ordered PostgreSQL DDL and limited runtime role grants |
| `tests/` | Immutable-evidence, concurrency, workflow, contract and browser tests |

Rebuild changes with `npm run build` and serve with `uvicorn app:app --reload`. The browser calls the same origin for the API and static assets. Build artifacts in `public/` are generated from the frontend sources.

## Verification

```bash
npm ci
npm test
npm run build
pip install -r requirements-e2e.txt
python -m playwright install chromium
export TEST_POSTGRES_URL="$MIGRATION_DATABASE_URL"
python -m unittest discover -s tests -v
PYTHONPATH=. python tests/browser_workflow.py
```

The tests use synthetic employees and create their own temporary PostgreSQL databases. `CHROMIUM_EXECUTABLE` can point to an installed compatible Chromium binary. The browser smoke test listens on localhost port 4187. CI provisions PostgreSQL 16 and runs the TypeScript, unit, API, database, browser, and export checks on pull requests.

## Changes

Add forward migrations rather than editing a migration already applied. `python -m siteguard migrate --runtime-role siteguard` applies outstanding SQL files and reapplies the role grant files in order. Update the API contract and test fixtures when changing a public route or payroll behavior.
