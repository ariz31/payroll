# SiteGuard QR API v1

FastAPI publishes the machine-readable schema at `/api/openapi.json` and the interactive reference at `/api/docs`. Business routes use the `/api/v1` prefix. Staff authenticate with a same-origin session cookie. Browser writes require a matching `Origin`. Enrolled kiosks authenticate with `Authorization: Device <credential>`.

| Capability | Routes under `/api/v1` |
| --- | --- |
| Liveness and readiness | `GET /health/live`, `GET /health/ready` |
| Identity | `GET /auth/options`, `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`, OIDC `/auth/oidc/start` and `/auth/oidc/callback` |
| Sites and accounts | `GET /sites`, `PUT /sites/{site_id}`, `GET /users`, `PUT /users/{login}` |
| Roster and evidence | `GET /employees`, `GET/PUT /employees/{employee_id}`, `PUT /employees/{employee_id}/badge-image` |
| Badges | `GET /badges`, `POST /badges/issue`, `POST /badges/{badge_id}/revoke`, `GET /badges/{badge_id}/code`, `GET /badges/mine` |
| Terminals and scans | `GET /terminals`, `PUT /terminals/{code}`, `POST /terminals/{code}/rotate`, `POST /terminals/session`, `POST /scans`, `POST /scans/offline-batches` |
| Policy and verification | `GET/PUT /config`, `GET /dashboard`, `GET /shifts`, `GET /shifts/{id}`, `POST /shifts/{id}/review`, `POST /shifts/bulk-verify`, `GET /shifts/{id}/evidence/{kind}` |
| Exports and printable DTR | `GET /payroll/periods/{period}/preflight`, `GET/POST /payroll/exports`, `GET /payroll/exports/{id}`, `GET /payroll/periods/{period}/dtr/{employee}` |
| Audit | `GET /audit/scans`, `POST /audit/scans/{id}/reconcile`, `GET /audit/approvals`, `GET /audit/control` |

## Scan capture

The terminal session returns a signed lease, enrollment generation, sequence and chain head. Each capture supplies an event UUID, sequence, generation, epoch milliseconds, GPS in microdegrees and accuracy millimetres, direction, QR, optional JPEG, lease, and previous hash. The device computes the SHA-256 of the JSON array in [the canonical terminal implementation](../../frontend/outbox.mjs) and signs that hex hash using the credential as the HMAC-SHA256 key. Supply up to 20 events to the batch endpoint. Every committed result returns a receipt and whether the server chain advanced. Retrying an identical event returns its original receipt. Reusing the ID for different evidence returns HTTP 409.

## Reviews

Send `request_id`, `version`, `action` and `notes` to the review route. Final decisions also accept `adjusted_in` or `adjusted_out` in ISO 8601 with offsets. The API maps role/state violations and stale versions to 403 or 409. A request ID can be reused to retry the corresponding action. The database writes the actor, prior and resulting state, reason, and server time.

## Exports

Send `period`, `format`, the optional `site`, `expected_pending_count`, and the `snapshot_key` from preflight. Stale data returns HTTP 409. The export record stores the site scope, signed receipt, digest, status counts, policy versions, and pending employee IDs. Add `?download=true` to the authorized export resource to retrieve the original artifact.
