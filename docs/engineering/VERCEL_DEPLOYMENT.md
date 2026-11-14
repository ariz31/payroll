# Deploy SiteGuard QR on Vercel

The repository uses Vercel’s FastAPI framework and builds the React interface into `public/`. Vercel serves the static assets and routes `/api/v1/*` to `app.py`. PostgreSQL persists attendance across function invocations.

## Configure PostgreSQL

1. Create a dedicated PostgreSQL 16+ database. A hosted provider such as [Neon on Vercel](https://vercel.com/docs/postgres) can supply connection strings.
2. Create a login role for the application with a strong password and ordinary login access. Use a separate owner connection for schema migrations. Avoid giving the runtime role membership in the migration owner role.
3. Run migrations and create the first administrator from a trusted terminal with the production database owner URL set in the environment.

   ```bash
   pip install -r requirements.txt
   python -m siteguard migrate --runtime-role siteguard
   python -m siteguard bootstrap --organization your-org --name "Your Organization" --login admin
   ```

Reserve one database per environment. Use a TLS connection string for the runtime. On installations with burst traffic, use a transactional pool endpoint for the limited runtime role, keeping the migration connection direct. Assign the project and database regions near one another.

## Configure Vercel

Open the linked [payroll project](https://vercel.com/arizs-projects-65ffe174/payroll). The root of the repository is the root directory. Clear old overrides for the framework, static output directory, install command, or build command so this repository’s FastAPI settings can take effect.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Runtime connection string for the application role |
| `SITEGUARD_SECRET` | Independent random value of at least 32 bytes for signing and encryption. Generate it with `openssl rand -hex 48` |
| `SITEGUARD_ORIGIN` | Canonical HTTPS origin when using custom-domain restrictions or SSO |
| `CRON_SECRET` | Independent random secret for the daily cleanup function |
| `SITEGUARD_EVIDENCE_ENABLED` | Set to `true` when approved sites should offer camera evidence |
| `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET` | Trusted issuer and confidential client configuration for optional SSO |
| `SITEGUARD_PREVIOUS_SECRETS` | Comma-separated previous signing roots during a planned rotation |

Keep `MIGRATION_DATABASE_URL` with the operator running migrations. Configure production and preview with separate application secrets and separate databases. Deployment Protection can stay enabled when all users and gate browsers have the associated Vercel access. Teams that use a managed workforce domain should arrange access to that domain with the Vercel project owner.

Deploy `main` after setting environment variables. Vercel's [FastAPI documentation](https://vercel.com/docs/frameworks/backend/fastapi) covers routing, build and static file behavior. Its [environment settings](https://vercel.com/docs/environment-variables) take effect on a new deployment.

## Smoke check after deployment

1. Open the deployment’s canonical URL in an authorized browser. Confirm the Sign in page loads.
2. Check `GET /api/v1/health/live` for `{"status":"ok"}` and `GET /api/v1/health/ready` for `{"status":"ready"}`. A Vercel access page indicates Deployment Protection. A SiteGuard readiness error points to the runtime database, missing migrations, or signing configuration.
3. Use a synthetic account and badge to complete a shift, review it, and download both export formats. Confirm a pending employee remains on hold.
4. Check Vercel function logs for database, scan, and export failures and verify that daily retention runs with the configured `CRON_SECRET`.

On self-hosted installations, schedule `python -m siteguard purge-expired-images` with the runtime configuration. See [deployment operations](DEPLOYMENT_OPERATIONS.md) for launch and recovery.
