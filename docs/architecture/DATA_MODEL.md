# Data model and integrity specification

**Status:** **proposed logical schema**, based on entities and invariants required by the blueprint. No database or migrations yet exist. Examples are implementation guidance, not applied DDL.

## Core entities

| Entity / table | Key fields | Purpose |
| --- | --- | --- |
| `employees` | `emp_id` PK, legal_name, department, active | Employee master (PII) |
| `projects` / `cost_codes` | project_id, cost_code, org/site scope | Overtime and cost authorization |
| `employee_assignments` | emp_id, shift_template_id, site_id, cost_code, effective dates | Effective-dated work assignments |
| `shift_templates` | local_start, local_end, break_mins, timezone, regular_cap | Configurable day/night rules |
| `sites` | site_id, timezone, geofence latitude/longitude/radius | Site policy |
| `terminals` | terminal_id, site_id, enrollment status, GPS claim, key id | Trusted kiosks |
| `badges` | badge_id, emp_id, mode, key version, issued/revoked dates | Dynamic and static signing material reference |
| `system_config` | key, typed value, effective_at, version, actor | Audited settings (blueprint requires persistence) |
| `qr_raw_scan_audit` | audit_id, terminal_id, client_event_id, captured_at, received_at, validation result, reason, hash | **Append-only all attempts**, including rejected and duplicate |
| `qr_shift_logs` | scan_id, emp_id, work_date, shift_type, raw_qr_time_in/out, overrides, effective hours, anomaly, status | Per-shift derived and final handoff row |
| `approval_events` | approval_id, scan_id, tier, decision, actor_id, note, server time | **Append-only review history** |
| `export_jobs` / `export_records` | export_id, pay_period, created_by/time, digest, pending count | Reproducible handoff receipt |
| `gate_images` | image_id, audit_id, storage ref, deletion due date, access log | Sensitive evidence (only if approved) |
| `offline_device_sequences` | terminal_id, event sequence, event hash, last accepted state | Idempotence and reconciliation |

**Required by source:** `system_config`, `qr_raw_scan_audit`, `qr_shift_logs`, immutable raw punches, reviewer actor/notes/time. Other names and decomposition above are proposals to implement those guarantees.

## Invariants (must be tested in PostgreSQL)

1. **No UPDATE or DELETE** of `qr_raw_scan_audit` through application DB role; privilege and triggers must both enforce immutability.
2. `qr_shift_logs.raw_qr_time_in` and `raw_qr_time_out` can move **NULL → one value** when an accepted punch is first paired. Once non-NULL, their values never change; an updated time is recorded only as a TK override. Row DELETE is prohibited.
3. A TK override or final `Disputed / Rejected` disposition requires `verified_by_tk`, trimmed non-empty `tk_verification_notes`, and server-assigned `verified_timestamp`. Reviewer identity must match the authorized authenticated actor.
4. An audit event is linked to the exact terminal, employee/badge resolution, validation status, receipt time and effective configuration/key version.
5. No duplicate `(terminal_id, client_event_id)` can cause a second accepted punch. Likewise, no duplicate review event ID may be applied twice.
6. Approval transitions are enforced by API **and** database constraints/permission design. Every transition must leave append-only decision history.
7. Effective/derived fields are reproducible from raw events, overrides, config version, approved assignment and timezone policy.
8. Payroll export projects only the 23 public contract columns; internal IDs, timestamps, evidence and hold details remain internal metadata.

## Example enforcement pattern (illustrative, not a complete migration)

```sql
-- PostgreSQL sketch: protect write-once raw punch columns.
CREATE OR REPLACE FUNCTION protect_raw_shift_fields()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'qr_shift_logs cannot be deleted';
  END IF;
  IF OLD.raw_qr_time_in IS NOT NULL
     AND NEW.raw_qr_time_in IS DISTINCT FROM OLD.raw_qr_time_in THEN
    RAISE EXCEPTION 'raw_qr_time_in is immutable';
  END IF;
  IF OLD.raw_qr_time_out IS NOT NULL
     AND NEW.raw_qr_time_out IS DISTINCT FROM OLD.raw_qr_time_out THEN
    RAISE EXCEPTION 'raw_qr_time_out is immutable';
  END IF;
  RETURN NEW;
END;
$$;
CREATE TRIGGER trg_raw_shift_immutable
BEFORE UPDATE OR DELETE ON qr_shift_logs
FOR EACH ROW EXECUTE FUNCTION protect_raw_shift_fields();
```

The trigger permits NULL → value, and rejects value → NULL and value → different value. In production, also protect who can perform the first set, limit raw writes to a controlled ingest role/function, deny TRUNCATE, protect against disabling triggers, separate migration/admin privileges, and test concurrent inserts. A dedicated append-only audit trigger can reject UPDATE/DELETE outright.

## Proposed DB-level adjustment guard

```sql
ALTER TABLE qr_shift_logs
ADD CONSTRAINT ck_adjustment_audit_metadata
CHECK (
  (
    tk_adjusted_in IS NULL
    AND tk_adjusted_out IS NULL
    AND timekeeper_status <> 'Disputed / Rejected'
  )
  OR (
    NULLIF(BTRIM(verified_by_tk), '') IS NOT NULL
    AND NULLIF(BTRIM(tk_verification_notes), '') IS NOT NULL
    AND verified_timestamp IS NOT NULL
  )
);
```

This is **not sufficient by itself**: the API must bind actor to session, server must supply timestamp, audit events must be immutable, and a previous final rejection must not be cleared without a separate authorized reversal record. Consider a normalized state machine rather than allowing unrestricted direct status UPDATEs.

## Timestamp design and export projection

- Store absolute instants as `timestamptz` (UTC-normalized) and original device timestamp/offset as separate evidence; do not use HH:MM alone to compute durations.
- Work_Date is site-local **shift start date**; a 22:00–07:00 shift belongs to its start date even when out is next morning.
- Export `Raw_QR_Time_In` and other time-only columns as HH:MM in site-local time, with date context from Work_Date and shift rules. **Export format alone cannot reconstruct arbitrary multi-day or daylight-saving punches**; keep full instants internally.
- Quantize hours to 2 decimals with explicit rounding mode decided by product/finance; do not round intermediate minute totals before final conversion.
- Preserve config versions and previous anomaly decisions when dynamic settings re-evaluate active queues.

## Indexes, isolation, and retention (proposed)

Indexes: `qr_raw_scan_audit(terminal_id, client_event_id)` unique; `qr_shift_logs(emp_id, work_date)` lookup with uniqueness qualified by shift occurrence; `qr_shift_logs(pay_period, timekeeper_status)`; `approval_events(scan_id, created_at)`. Scope all access to tenant/organization where applicable.

Use row locks or serializable transactions to avoid double pairing. Retention of raw evidence, photos and audit history is **not specified** in the blueprint; determine jurisdictional schedules and legal holds before adding automated deletion (which must not undermine required immutability).
