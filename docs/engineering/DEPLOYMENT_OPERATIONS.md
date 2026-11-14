# Deployment operations

The supported layouts are the [Vercel project](VERCEL_DEPLOYMENT.md) with hosted PostgreSQL and a self-hosted FastAPI process behind a TLS reverse proxy with PostgreSQL. Release the frontend and API together.

| Environment | Database | Purpose |
| --- | --- | --- |
| Local and CI | Isolated PostgreSQL 16 | Synthetic fixtures, migration and browser checks |
| Preview | Separate staging database | Site workflow, device and recovery testing |
| Production | Dedicated database with backups | Authorized workforce attendance |

## Before field rollout

- Pick the canonical URL, database region, users, role scopes, and the approved site coordinates and radius. Record device custody and enrollment.
- Run migrations using the owner connection. Confirm that the application uses the separately granted runtime role.
- Complete a full synthetic shift on gate hardware, including GPS, camera or USB scanner, a browser restart while offline, and reconnect. Measure response latency at the actual gate.
- Verify backup restore and compare record counts, punch references, export hashes, and sample approvals against the source environment.
- Confirm the camera notice, retention, and workforce procedure with the responsible organization. Have payroll test imports, hold gating, and any agency-specific attendance form before using real employee data.

## Routine checks

Monitor `/api/v1/health/ready` from an authorized probe. Track quarantined/rejected events and device backlog in the workbench. Review function 5xx, PostgreSQL connectivity, and Vercel cron logs. Check retention cleanup with `/api/v1/internal/daily` or the local cleanup command. Keep old signing roots according to the [security guide](SECURITY_PRIVACY.md).

## Recovery

When an outage starts, use the terminal’s queued count and last known lease. After reconnect, compare server receipts and quarantined events. A supplied manual correction follows the same three review tiers and preserves originals. Roll back the application deployment if its code fails and the previous code is compatible with the forward-only database migration. Restore backups into an isolated environment first, verify immutable references and checksums, then promote through the database provider’s recovery procedure.
