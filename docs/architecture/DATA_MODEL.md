# PostgreSQL data model

The versioned files in [db/migrations](../../db/migrations) are the schema source of truth.

| Tables | Responsibility |
| --- | --- |
| `organizations`, `sites`, `staff`, `sessions`, `oidc_links` | Organization/site boundaries, human accounts, and identity |
| `employees`, `assignments`, `badges`, `terminals` | Roster, active site membership, credentials, and gate enrollment |
| `policy_versions` | Append-only policy definitions. Version 0 uses source defaults |
| `scan_audit`, `dynamic_uses`, `scan_reconciliations` | Scan receipts, event chain details, outcomes, replay protection and append-only quarantine decisions |
| `shifts`, `approval_audit` | Work-date pairing, raw and adjusted instants, reviewer transitions, and prior/resulting states |
| `scan_evidence`, `profile_evidence` | Encrypted image bytes and expiry timestamps |
| `payroll_exports`, `control_audit` | Immutable period revisions, provisioning, evidence-access and download trail |

A shift has one site and one employee/work-date key. It retains the site timezone, employee display and authorization attributes, shift type, and terminal from the first associated scan. Future roster and site edits apply to new shifts. Review scopes for an existing shift use its retained values. Active policy updates recalculate unfinished rows and return them to field review.

`scan_audit` stores terminal receipt and QR digests, device and server timestamps, geofence measurements, and result. Its mutable artifacts live separately. Raw shift instants are write-once and require accepted evidence for the same shift. Final verification requires a complete effective pair. The application role can call the transition procedure but has no direct update grant on stage or adjusted timestamps.

The work date is stored as a civil date, and punches as timezone-aware instants. Exports convert those instants to local `HH:MM` at the boundary. Store and restore immutable revisions with the database backups.
