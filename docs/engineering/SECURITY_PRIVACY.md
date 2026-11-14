# Security, privacy and audit requirements

The controls below describe the threat model and rollout requirements from blueprint §§1–5. See the [operator guide](OPERATIONS_GUIDE.md) and [architecture](../architecture/SYSTEM_ARCHITECTURE.md) for deployed controls and configuration.

## 1. Assets and trust assumptions

**Sensitive assets:** employee identity/assignments, attendance and location context, reviewer decisions, gate images, project cost codes, QR signing keys, device secrets, export files and audit evidence.

**Adversaries / failure classes:** badge cloning and sharing, dynamic-code screenshot replay, kiosk compromise, terminal geolocation spoofing, device time manipulation, offline event editing/dropping, insider review abuse, developer/migration bypass of raw triggers, unauthorized exports, exposed image URLs, CSV formula injection and denial-of-service at gate rush hour.

| Risk | Required protection / test |
| --- | --- |
| Unsigned or stale QR | HMAC-SHA256 verification, active status, time-window/replay tests |
| Badge photo/clone | Static credential revocation and extra identity controls; no promise of cryptographic prevention |
| Terminal spoof or relocation | Authenticated enrollment + geofence attestation strategy and movement audit |
| Lost offline events | Sealed durable ordered outbox + reconciliation, idempotency and alerting |
| Tampered raw punches | DB write-once triggers + restricted DB roles + immutable scan journal |
| Unauthorized adjustment | Tiered role checks, authenticated actor, non-empty notes, server timestamp |
| Double payroll count | Idempotent event ingest, per-period approval gate, exact export statuses |
| Reviewer self-approval / out-of-scope access | RBAC + org/site/cost-code scoping, immutable decision trail |
| Exposed photo / personal data | Data minimization, encrypted isolated storage, short-lived scoped access and access log |
| Malicious CSV cells | Spreadsheet formula-injection protection + round-trip contract tests |
| Secret leaked in frontend | No signing/private secrets in browser bundle or public repo |
| Bypassed integrity on schema migration | Role separation, signed/reviewed migrations, restoration/audit policy |

## 2. Cryptographic protocol review required

Source dynamic format: `DYN|<Emp_ID>|<Step>|<HMAC_16hex>`, static: `STC|<Emp_ID>|STATIC|<HMAC_16hex>`. Source describes 30-second dynamic rotation, HMAC-SHA256 and ±1 step. **16 hexadecimal characters represent a 64-bit truncated HMAC tag**; assess online/offline attack resistance, key scope, verification rate limits and rotation. Define versioned canonical message/encoding, separation of static vs dynamic keys, secret generation/rotation, timing-safe comparison, badge revocation and screenshot replay handling.

A TOTP-like code is not inherently one-time: accepting a ±1 step allows reuse without server-side/terminal-bound replay defenses. Static printed badges necessarily permit visual copying; be explicit about residual risk and compensating physical/policy measures.

## 3. Evidence immutability

- Store every tap (including rejected/duplicate) in append-only `qr_raw_scan_audit`.
- Once raw punch set, database rejects change/delete even if API request bypasses UI.
- Use non-destructive `TK_Adjusted_In`/`TK_Adjusted_Out` fields with immutable decision event history.
- Any final Disputed / Rejected status or populated adjustment needs central TK identity, meaningful notes and server timestamp.
- Export records and receipts should be versioned, checksummed and bound to immutable input snapshot. Preserve reasons for corrections and reopens.

“Immutable” is a business integrity design goal; true resistance to privileged database/root operators requires additional infrastructure controls such as off-system immutable backups or external hash anchoring. Do not claim WORM/tamper-proof guarantees based solely on a normal trigger.

## 4. Privacy-by-design decisions

The blueprint proposes **silent gate camera stills (~15 KB)** and badge image comparison. Capturing a person without adequate notice or lawful basis can create privacy and employment risk. Before enabling:

1. Establish a lawful basis/purpose, transparent notice, access rights and appropriate consultation with legal/privacy experts.
2. Determine whether face comparison is human review vs automated biometric identification; do not silently add automated face recognition.
3. Limit capture to necessary events, minimize image resolution/retention, encrypt and separate evidence storage.
4. Authorize and audit every access; protect against guessable URLs, broad admin access and unencrypted backup exposure.
5. Define deletion/retention/legal-hold rules, rights request procedures, incident reporting and third-party processor contracts.
6. Review workforce monitoring implications for the jurisdiction and government agency.
7. Provide accessible alternative workflow for camera outage and special circumstances, approved by policy.

Geofence checks should primarily verify **registered terminal** location and site authorization. Do not represent them as proof of an employee’s actual GPS position.

## 5. Authentication and authorization

- Human operators: strong authentication (prefer enterprise SSO with MFA where available), session management, scoped RBAC, server-side authorization for every read and write.
- Devices: separate enrolled terminal credentials; use rotation/revocation and anti-replay; do not share one kiosk API key across the fleet.
- Database: app user cannot drop triggers, disable audit, truncate, directly issue final statuses or alter schema; migrations use distinct privileged identity.
- Exports: authorize by role and selected org/site, log download and delivery, expire signed URLs, prevent cross-tenant access.
- Break-glass: exceptional, time-limited, logged and independently reviewed; never a silent bypass of verification notes.

## 6. Secure implementation checklist

- [ ] Validate inputs, bound payload size, parameterize SQL, check attachment content-type and malicious image payloads.
- [ ] Restrict CORS and CSRF/session boundaries; enforce TLS and appropriate headers; sanitize logs.
- [ ] Use constant-time HMAC compare; source keys from secret manager; version and rotate keys.
- [ ] Log terminal, actor, purpose, time, outcome and correlation ID without leaking raw secrets/images.
- [ ] Define data retention and privacy controls; include test data generator and purge of accidental real data.
- [ ] Rate-limit token verification; monitor replay/badges and unusual location patterns.
- [ ] Perform security tests for role bypass, race conditions, direct SQL privilege misuse and offline tamper.
- [ ] Review supply chain/SBOM and maintain patch cadence, incident response and backup recovery.
- [ ] Review Form 48 output and actual pay rules with qualified jurisdictional stakeholders.

## 7. Compliance and claims

The blueprint markets “tamper-evident,” “anti-buddy punching,” Form 48 and government adoption. Treat these as intended controls/market positioning, **not formal independent audit certification**. Never infer that signed QR plus silent photo fully prevents fraud. Employment/privacy laws, timekeeping rounding, overtime approval and night premium must be checked for each actual country and employer.
