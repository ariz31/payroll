# QR credential, kiosk, geofence and offline sync specification

Signed token formats and defaults come from blueprint §§2–3. The [API contract](../api/API_CONTRACT.md) defines the implemented wire payload; the [decision register](../engineering/DECISIONS_AND_OPEN_QUESTIONS.md) records the trust model, clock and retention defaults.

## 1. Credential formats (source)

| Mode | Text grammar | Source behavior |
| --- | --- | --- |
| Dynamic | `DYN|<Emp_ID>|<Step>|<HMAC_16hex>` | HMAC-SHA256, rotating every 30s; accept current ±1 step, reject stale/invalid tokens |
| Static | `STC|<Emp_ID>|STATIC|<HMAC_16hex>` | Signed badge for hard-hat decals / PVC cards; subject to issuer revocation and terminal checks |

The source also mentions employee name, department, cost code and shift in badge provisioning but **the stated token grammar contains only Emp_ID, Step/mode and authenticator**. Proposed resolution: store sensitive attributes server-side and resolve from authenticated Emp_ID; do not embed full employee profile in printable QR without approval. Exact key derivation, canonicalization, tag encoding, rotation and replay storage require an ADR.

The named `HMAC_16hex` is a 16-hex-character (64-bit) truncated tag. Whether this is sufficient for the deployment threat model must be assessed; default to stronger non-truncated/more robust identifiers only with a versioned protocol decision, not silently breaking specified badges. Never ship signing keys in web client code.

## 2. Validation sequence

1. Parse payload with strict size/charset/field count and version rules.
2. Authenticate enrolled terminal separately from QR. Bind terminal to authorized site.
3. Resolve badge/employee, active status, assignment, revocation/key version and allowed mode.
4. Verify HMAC using constant-time comparison and approved secret management. For dynamic mode, validate 30s steps with ±1 drift.
5. Check replay and geofence policy, then 300-second **accepted punch** debounce; journal every attempt and outcome.
6. Only after server-side validation may raw in/out be set; reject or quarantine otherwise.
7. Return generic enough errors to limit enumeration; log detailed reason privately.

**Threats not solved by a valid QR alone:** photographed static badge reuse, dynamic token relaying, stolen phones, compromised terminal, credential sharing and collusive buddy punching. A silent gate photo helps review but does not cryptographically prove identity.

## 3. Terminal geofence

**Source rule:** record `QR_Terminal_ID` and compare terminal GPS location to configured perimeter using Haversine distance. Example IDs: `QR-SITE09-GATE1`, `QR-DPWH-CAMP2`, `QR-LGU-HALL`.

**Proposed policy:** register trusted fixed coordinates and an approved site radius; do not rely solely on spoofable browser geolocation for terminal identity. Distinguish enrolled fixed-location attestation from live location claim. A geofence match proves only reported/attested **terminal location**, not worker physical presence; define offline exception handling.

Haversine sketch (Earth radius as implementation constant):
```text
a = sin²((lat2 - lat1)/2)
  + cos(lat1) * cos(lat2) * sin²((lon2 - lon1)/2)
distance = 2 * R * asin(min(1, sqrt(a)))
accept if distance <= configured_radius_m AND terminal/site enrollment valid
```

Angles in radians; test boundary, coordinate normalization, mocked GPS and spoof resistance.

## 4. Gate camera evidence

Blueprint proposes a **silent ~15 KB front-camera frame** per scan, used by central TK to compare against registered badge images. This is a product target, **not permission to capture covertly**. Before implementation obtain a lawful basis, prominent employee notice, employer policy, storage limits, access controls, incident response, and review of applicable privacy/employment laws. Sensitive images should be segregated from CSV/XLSX; raw images and their access should be audited. Compressing to 15 KB is a target, not an excuse to store unusable or misleading evidence.

Proposed options if camera unavailable: block, accept-with-warning or supervisor attestation; choose per site policy in an ADR and surface it in the kiosk. Do not silently discard the failure.

## 5. Offline zero-signal protocol

**Source:** local sealed event queue with monotonic IDs (e.g., `SEQ-001`), cryptographic hashes and replay to PostgreSQL on reconnect while preserving debounce/pairing. **Proposed wire design:**

```json
{
  "terminal_id": "QR-SITE09-GATE1",
  "batch_id": "device-batch-uuid",
  "events": [
    {
      "client_event_id": "uuid-v7-or-random",
      "sequence": 1,
      "qr_payload": "<captured-token-or-protected-reference>",
      "captured_local_at": "2026-11-12T21:58:00+08:00",
      "device_time_source": "system-clock",
      "previous_event_hash": "<hash-or-genesis>",
      "event_hash": "<canonical-content-hash>",
      "device_authenticator": "<device-bound-signature-or-mac>"
    }
  ]
}
```

The exact payload fields and what constitutes “sealed” depend on an approved design. At a minimum: local encryption-at-rest with device-bound keys where feasible, signed/hash-chained order, outbox transactions, sequence-monotonicity checks, storage-capacity alerts, isolated kiosk auth, stable event IDs and server deduplication.

**Critical issue:** a dynamic QR token may expire before delayed sync. Server cannot simply reject all previously captured valid offline credentials nor blindly accept arbitrary client timestamps. Define attested capture time and offline trust window, device clock skew policy, replay scope and anti-tamper behavior **before claiming offline security compliance**. Offline capture must never be called Verified until server validation and workflow succeed.

## 6. Exact-once effect / at-least-once transport

- Client retries at least once until each event is durably acknowledged.
- Server implements idempotent effects keyed by enrolled terminal + client event ID; duplicate upload returns the same accepted/ignored/rejected receipt.
- Terminal scan debouncing and transport idempotency are **different**: two taps within 300s become distinct audited attempts with one IGNORED_DEBOUNCE, while resending one event never creates an additional audit row.
- Keep original device capture time and server receipt time; store accepted work-time derivation and any uncertainty/quarantine flags separately.
- Missing sequence numbers, tampered hash chain or clocks beyond tolerance enter operational incident queue, not silent acceptance.
- Clear local record only after a verified server receipt and safe acknowledgment persistence.

## 7. Status vocabulary

| Internal capture outcome | Kiosk text | Creates punch? |
| --- | --- | --- |
| `ACCEPTED_IN` | Clock-In Recorded | Yes |
| `ACCEPTED_OUT` | Clock-Out Recorded | Yes |
| `IGNORED_DEBOUNCE` | Duplicate Tap Ignored | No |
| `OFFLINE_QUEUED` (local only) | Offline Captured & Sealed | Not yet |
| `REJECTED_INVALID_TOKEN` | Rejected | No |
| `REJECTED_GEOFENCE` / other rejection (proposed) | Rejected | No |
| `QUARANTINED_TIME_OR_SEQUENCE` (proposed) | Needs supervisor review | No pending resolution |

**Open:** static badge replay policy, time attribution for delayed uploads, hardware clock attestation, offline duration limit, same-employee multi-terminal scans, and snapshot availability. Record decisions in [ADRs](../engineering/DECISIONS_AND_OPEN_QUESTIONS.md).
