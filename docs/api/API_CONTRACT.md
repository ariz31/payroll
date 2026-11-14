# API contract proposal — v0 (not implemented)

**Status: proposed.** The blueprint does **not** provide endpoint paths, JSON schemas, auth provider or HTTP status conventions. This page offers a reviewable FastAPI REST design for the target capabilities. No routes currently exist.

**Base path:** `/api/v1` (**proposal**). Require HTTPS, authenticated staff/terminal identities, site-scoped authorizations, rate limits, structured audit logging and server-supplied actor/time. Date/times in API use ISO 8601 offset-aware strings; export uses HH:MM.

## 1. Endpoint inventory

| Method | Path | Principal | Purpose |
| --- | --- | --- | --- |
| GET | `/health/live` | Infrastructure | Process liveness; no sensitive data |
| GET | `/health/ready` | Infrastructure | Dependency readiness, restricted |
| GET/POST | `/employees` | Scoped admin | List/create employee |
| GET/PATCH | `/employees/{emp_id}` | Scoped admin | View/effective-date assignment |
| POST | `/badges/issue` | Scoped admin | Issue signed badge |
| POST | `/badges/{badge_id}/revoke` | Scoped admin | Revoke credential |
| GET/POST | `/terminals` | Scoped admin | Enroll/list terminals |
| POST | `/scans` | Enrolled terminal | Submit single scan, return durable receipt |
| POST | `/scans/offline-batches` | Enrolled terminal | Ordered idempotent offline replay |
| GET | `/shifts` | Authorized reviewer | Filter by period/site/employee/status |
| GET | `/shifts/{scan_id}` | Scoped reviewer | Evidence, calculations and review history |
| POST | `/shifts/{scan_id}/endorse` | Foreman | Tier 1 field endorsement |
| POST | `/shifts/{scan_id}/cost-review` | Engineer / Head | Tier 2 cost/OT decision |
| POST | `/shifts/{scan_id}/verify` | Timekeeper | Tier 3 final status, optional adjustments |
| POST | `/shifts/bulk-verify` | Timekeeper | Clean OK only, policy-specific authorization |
| GET/PATCH | `/config` | Admin | Read/update versioned policy |
| GET | `/dashboard` | Reviewer | KPI counts and verified hour sums |
| GET | `/payroll/periods/{yyyy_mm}/preflight` | TK / payroll | Pending count, hold employees, totals |
| POST | `/payroll/exports` | TK / payroll | Create immutable CSV/XLSX revision |
| GET | `/payroll/exports/{export_id}` | TK / auditor | Metadata and authenticated download link |
| GET | `/audit/scans` | Auditor | Read-only filtered journal |
| GET | `/audit/approvals` | Auditor | Read-only review history |

These routes are placeholders for design review, not commitment to OpenAPI compatibility until implemented.

## 2. Single scan (proposed example)

```http
POST /api/v1/scans
Authorization: Device <terminal-bound-credential>
Idempotency-Key: 08b0bf99-757d-481c-a554-b243f01e5bc9
Content-Type: application/json
```

```json
{
  "client_event_id": "08b0bf99-757d-481c-a554-b243f01e5bc9",
  "terminal_id": "QR-SITE09-GATE1",
  "qr_payload": "DYN|EMP-1001|1794500000|<HMAC_16hex>",
  "captured_at": "2026-11-12T07:56:00+08:00",
  "device_sequence": 1001,
  "location_claim": {"latitude": 16.4, "longitude": 120.6, "accuracy_m": 10}
}
```

**Note:** step value, coordinates and signature above are illustrative, **not valid enrolled credentials**. Final schema should avoid exposing signed QR payloads in logs and should enforce maximum payload sizes.

```json
{
  "client_event_id": "08b0bf99-757d-481c-a554-b243f01e5bc9",
  "receipt_id": "evt-server-id",
  "result": "ACCEPTED_IN",
  "message": "Clock-In Recorded",
  "scan_id": "QR-2611-001",
  "received_at": "2026-11-12T07:56:02+08:00",
  "work_date": "2026-11-12",
  "server_review_status": "Pending Review"
}
```

**Rules:** a persisted rejected attempt can return `REJECTED_INVALID_TOKEN`; an accepted duplicate tap returns `IGNORED_DEBOUNCE`; network retries with same event ID return original receipt. “Offline Captured & Sealed” is primarily **client-side** until server acknowledges persisted event.

## 3. Offline batch response (proposed)

Client sends enrolled terminal ID, batch ID and array of ordered sealed events with hashes/authenticators. Server responds **per event**, not blanket success:

```json
{
  "batch_id": "device-batch-uuid",
  "receipts": [
    {"client_event_id": "event-1", "sequence": 1, "outcome": "ACCEPTED_IN", "receipt_id": "s1"},
    {"client_event_id": "event-2", "sequence": 2, "outcome": "IGNORED_DEBOUNCE", "receipt_id": "s2"},
    {"client_event_id": "event-3", "sequence": 3, "outcome": "QUARANTINED_TIME_OR_SEQUENCE", "receipt_id": "s3"}
  ],
  "last_contiguous_sequence_acked": 2
}
```

Pending/quarantined handling and attestation are **open decisions**; receipt 3 must not be interpreted as acceptance or deletion permission from local outbox.

## 4. Final timekeeper review (proposed)

```http
POST /api/v1/shifts/QR-2611-003/verify
Authorization: Bearer <staff-session>
If-Match: "shift-version-4"
Content-Type: application/json
```

```json
{
  "decision": "Verified",
  "tk_adjusted_out": "2026-11-12T17:00:00+08:00",
  "notes": "Turnstile and foreman verification confirm departure at 17:00"
}
```

Server populates `Verified_By_TK` from authenticated principal and `Verified_Timestamp` from server clock. Require upstream stage, notes for any adjustment or dispute, concurrency version, and forbid raw punch writes.

```json
{
  "scan_id": "QR-2611-003",
  "timekeeper_status": "Verified",
  "raw_qr_time_out": null,
  "tk_adjusted_out": "2026-11-12T17:00:00+08:00",
  "effective_out": "2026-11-12T17:00:00+08:00",
  "verified_by_tk": "tk-operator-id",
  "verified_timestamp": "2026-11-14T09:00:00+08:00",
  "version": 5
}
```

## 5. Payroll export endpoints

```json
{
  "pay_period": "2026-11",
  "format": "csv",
  "expected_pending_count": 2
}
```

Export receipt should include immutable `export_id`, generated time, row counts, counts per status, employee audit-hold IDs, checksum, config version, file MIME type and download mechanism. Never embed an editable “exported flag” in the v1 23-column table.

## 6. Errors, scopes, and compatibility

| HTTP | Proposed code | Meaning |
| --- | --- | --- |
| 400/422 | `INVALID_INPUT` | Malformed fields, illegal enum, invalid timestamp |
| 401 | `UNAUTHENTICATED` | Missing/expired terminal or user auth |
| 403 | `FORBIDDEN_SCOPE` | Disallowed employee/site/tier/terminal |
| 404 | `NOT_FOUND` | Unknown scoped record (avoid enumeration) |
| 409 | `CONFLICT_VERSION` | Stale review / concurrent update |
| 409 | `INVALID_TRANSITION` | Earlier tier required / finalized |
| 413 | `PAYLOAD_TOO_LARGE` | Oversize token/batch/snapshot |
| 429 | `RATE_LIMITED` | Device/user over budget |
| 503 | `DEPENDENCY_UNAVAILABLE` | Persistence unavailable; no false “recorded” receipt |

A signed QR validation failure is **business rejection** and should have an audited receipt; distinguish it from transport errors. Establish request IDs, structured error envelopes, pagination and schema validation when implementing FastAPI/Pydantic. Publish generated OpenAPI only once actual routes exist.

## 7. Open API decisions

Authentication strategy (OAuth/OIDC, device mTLS/JWT), tenant scoping, bulk-verify bypass, time source for delayed events, location attestation, evidence upload mechanism, status naming, timekeeper concurrency tokens and export download authorization must be approved before a stable v1 release.
