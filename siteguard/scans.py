import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field

from .accounts import Input, evidence_enabled
from .db import lock_org, now, transaction
from .registry import badge_tag, clean_jpeg, distance, evidence_cipher
from .security import derived_key, digest, previous_secrets, secret
from .timekeeping import assign_day, policy, scheduled

router = APIRouter()
TOKEN = re.compile(r"(DYN|STC)\|([A-Za-z0-9][A-Za-z0-9._-]{0,63})\|(STATIC|[0-9]{1,12})\|([a-fA-F0-9]{16})")
HEX = r"^[a-f0-9]{64}$"
TOLERANCE_SECONDS = 90


class Scan(Input):
    client_event_id: UUID
    generation: int = Field(ge=1, le=2**31 - 1)
    sequence: int = Field(ge=1, le=2**53 - 1)
    captured_ms: int = Field(ge=1, le=4_102_444_800_000)
    latitude_e6: int | None = Field(default=None, ge=-90_000_000, le=90_000_000)
    longitude_e6: int | None = Field(default=None, ge=-180_000_000, le=180_000_000)
    accuracy_mm: int | None = Field(default=None, ge=0, le=100_000_000)
    direction: Literal["auto", "in", "out"] = "auto"
    qr_payload: str = Field(max_length=256)
    jpeg: str = Field(default="", max_length=88000)
    lease: str = Field(max_length=512)
    previous_hash: str = Field(pattern=r"^(?:[a-f0-9]{64})?$")
    event_hash: str = Field(pattern=HEX)
    device_mac: str = Field(pattern=HEX)

    def canonical(self):
        fields = [1, str(self.client_event_id), self.generation, self.sequence, self.captured_ms,
                  self.latitude_e6, self.longitude_e6, self.accuracy_mm, self.direction,
                  self.qr_payload, self.jpeg, self.lease, self.previous_hash]
        return json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode()


class Batch(Input):
    events: list[Scan] = Field(min_length=1, max_length=20)


class LeaseInput(Input):
    client_ms: int = Field(ge=1, le=4_102_444_800_000)


def authenticate(db, auth, write=False):
    try:
        scheme, credential = (auth or "").split(" ")
        terminal_id, token = credential.split(".")
        ident = UUID(terminal_id)
        if scheme.lower() != "device" or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise ValueError
    except ValueError:
        raise HTTPException(401, "A valid terminal credential is required") from None
    row = db.execute("SELECT * FROM terminals WHERE id=%s", (ident,)).fetchone()
    if not row or not hmac.compare_digest(row["credential_hash"], digest(credential)):
        raise HTTPException(401, "A valid terminal credential is required")
    if write:
        lock_org(db, row["org_id"])
        row = db.execute("SELECT * FROM terminals WHERE id=%s FOR UPDATE", (ident,)).fetchone()
        if not hmac.compare_digest(row["credential_hash"], digest(credential)):
            raise HTTPException(401, "The terminal enrollment has changed")
    return row, credential


def mac(key, message):
    return hmac.digest(key, message.encode(), "sha256").hex()


def lease_token(terminal, client_ms, current, rules):
    issued = int(current.timestamp() * 1000)
    expires = issued + rules.offline_hours * 3600 * 1000
    body = f"{terminal['id']}:{terminal['generation']}:{issued}:{expires}:{client_ms}"
    return f"{body}:{mac(derived_key('terminal-lease'), body)}", issued, expires


def load_lease(payload, terminal, current):
    try:
        body, signature = payload.lease.rsplit(":", 1)
        ident, generation, issued, expires, _client_ms = body.split(":")
        if ident != str(terminal["id"]) or int(generation) != payload.generation:
            return None
        keys = [derived_key("terminal-lease", root) for root in [secret(), *previous_secrets()]]
        if not any(hmac.compare_digest(signature, mac(key, body)) for key in keys):
            return None
        received_ms = int(current.timestamp() * 1000)
        if not int(issued) <= payload.captured_ms <= int(expires) or received_ms > int(expires) + 90_000:
            return None
        if payload.captured_ms > received_ms + 5000:
            return None
        return datetime.fromtimestamp(payload.captured_ms / 1000, UTC)
    except (ValueError, OverflowError):
        return None


@router.post("/terminals/session")
def terminal_session(payload: LeaseInput, authorization: str | None = Header(default=None)):
    current = now()
    with transaction() as db:
        device, _ = authenticate(db, authorization)
        site = db.execute("SELECT * FROM sites WHERE org_id=%s AND id=%s", (device["org_id"], device["site_id"])).fetchone()
        if not device["active"] or not site["active"]:
            raise HTTPException(403, "This terminal is inactive")
        if abs(payload.client_ms - current.timestamp() * 1000) > TOLERANCE_SECONDS * 1000:
            raise HTTPException(409, "The terminal clock needs to be synchronized")
        _, rules = policy(db, device["org_id"])
        token, issued, expires = lease_token(device, payload.client_ms, current, rules)
        return {"terminal_id": device["id"], "code": device["code"], "site": site["name"],
                "generation": device["generation"], "last_sequence": device["last_sequence"],
                "last_hash": device["last_hash"], "lease": token, "issued_ms": issued, "expires_ms": expires,
                "evidence_mode": site["evidence_mode"] if evidence_enabled() else "off",
                "evidence_notice": site["evidence_notice"] if evidence_enabled() else ""}


def scan_badge(db, org, token, captured, rules):
    match = TOKEN.fullmatch(token)
    if not match:
        return None, None, "INVALID_TOKEN"
    mode, emp_id, marker, tag = match.groups()
    if (mode == "DYN" and (marker == "STATIC" or rules.qr_mode == "static")) or (
        mode == "STC" and (marker != "STATIC" or rules.qr_mode == "dynamic")
    ):
        return None, None, "MODE_MISMATCH"
    badge = db.execute(
        """SELECT b.id AS badge_id,b.mode,b.revoked_at,b.created_at,e.* FROM badges b
        JOIN employees e ON (b.org_id,b.employee_id)=(e.org_id,e.id) WHERE
        b.org_id=%s AND b.employee_id=%s AND b.mode=%s AND b.revoked_at IS NULL""",
        (org, emp_id, mode),
    ).fetchone()
    if not badge or not badge["active"] or badge["created_at"] > captured + timedelta(seconds=5):
        return None, None, "INACTIVE_BADGE"
    key_fields = {"mode": mode, "org_id": org, "id": badge["badge_id"], "employee_id": emp_id}
    if not any(hmac.compare_digest(tag.lower(), badge_tag(key_fields, marker, root))
               for root in [secret(), *previous_secrets()]):
        return None, None, "INVALID_SIGNATURE"
    if mode == "DYN":
        step = int(marker)
        if marker != str(step) or abs(int(captured.timestamp()) // rules.qr_step_seconds - step) > rules.qr_drift_windows:
            return None, None, "EXPIRED_TOKEN"
        return badge, step, ""
    return badge, None, ""


def geo_allowed(device, site, latitude, longitude, accuracy):
    return (
        latitude is not None and longitude is not None and accuracy is not None
        and accuracy <= min(75, site["radius_m"])
        and distance(site["latitude"], site["longitude"], device["latitude"], device["longitude"]) <= site["radius_m"]
        and distance(site["latitude"], site["longitude"], latitude, longitude) <= site["radius_m"]
        and distance(device["latitude"], device["longitude"], latitude, longitude) <= site["radius_m"]
    )


def pair(db, employee, device, site, captured, direction, version, rules, event_id):
    org, emp = employee["org_id"], employee["id"]
    work_date, inferred = assign_day(captured, site["timezone"], employee["shift_type"], rules, direction)
    shift = None
    if direction == "auto":
        candidates = db.execute(
            """SELECT * FROM shifts WHERE org_id=%s AND employee_id=%s AND site_id=%s AND raw_in<%s
            AND raw_out IS NULL AND stage NOT IN ('verified','disputed') AND adjusted_out IS NULL
            AND raw_in>%s ORDER BY raw_in DESC LIMIT 2""",
            (org, emp, site["id"], captured, captured - timedelta(hours=24)),
        ).fetchall()
        # An open shift in its scheduled window has priority over a new automatic arrival.
        for candidate in candidates:
            _, candidate_rules = policy(db, org, candidate["policy_version"])
            start, end = scheduled(candidate["work_date"], candidate["timezone"], candidate["shift_type"], candidate_rules)
            if captured <= min(end + timedelta(hours=6), start + timedelta(hours=24)):
                shift, inferred, work_date = candidate, "out", candidate["work_date"]
                break
    if not shift:
        shift = db.execute("SELECT * FROM shifts WHERE org_id=%s AND employee_id=%s AND work_date=%s",
                           (org, emp, work_date)).fetchone()

    if shift and (shift["site_id"] != site["id"] or shift["stage"] != "foreman" or
                  shift["adjusted_in"] or shift["adjusted_out"]):
        return "QUARANTINED", "SHIFT_IN_REVIEW_OR_OTHER_SITE", shift["id"], work_date
    if shift:
        same, other = (shift["raw_in"], shift["raw_out"]) if inferred == "in" else (shift["raw_out"], shift["raw_in"])
        if same:
            return "QUARANTINED", "PUNCH_ALREADY_PRESENT", shift["id"], work_date
        if other and (captured == other or abs(captured - other) >= timedelta(hours=24)
                      or (captured < other) != (inferred == "in")):
            return "QUARANTINED", "IMPLAUSIBLE_DURATION", shift["id"], work_date

    shift_id = shift["id"] if shift else uuid4()
    if shift:
        statement = (
            "UPDATE shifts SET raw_in=%s,in_event=%s,version=version+1,updated_at=clock_timestamp() WHERE id=%s"
            if inferred == "in" else
            "UPDATE shifts SET raw_out=%s,out_event=%s,version=version+1,updated_at=clock_timestamp() WHERE id=%s"
        )
        db.execute(statement, (captured, event_id, shift_id))
    else:
        db.execute(
            """INSERT INTO shifts (id,org_id,employee_id,site_id,work_date,timezone,name,department,cost_code,crew,
                shift_type,policy_version,terminal_code,raw_in,in_event,raw_out,out_event)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (shift_id, org, emp, site["id"], work_date, site["timezone"], employee["name"], employee["department"],
             employee["cost_code"], employee["crew"], employee["shift_type"], version, device["code"],
             captured if inferred == "in" else None, event_id if inferred == "in" else None,
             captured if inferred == "out" else None, event_id if inferred == "out" else None),
        )
    return ("ACCEPTED_IN" if inferred == "in" else "ACCEPTED_OUT"), "", shift_id, work_date


def scan_effect(db, payload, device, site, captured, event_id, latitude, longitude, accuracy, current):
    org = device["org_id"]
    version, rules = policy(db, org)
    if not device["active"] or not site["active"]:
        return "REJECTED", "INACTIVE_TERMINAL", None, None, None, None
    if not geo_allowed(device, site, latitude, longitude, accuracy):
        return "REJECTED", "GEOFENCE", None, None, None, None
    if captured is None:
        return "QUARANTINED", "CLOCK_OR_LEASE", None, None, None, None
    if db.execute("""SELECT count(*) AS n FROM (SELECT 1 FROM scan_audit WHERE terminal_id=%s AND received_at >= %s
                   LIMIT 181) recent""", (device["id"], current - timedelta(seconds=10))).fetchone()["n"] > 180:
        return "REJECTED", "TERMINAL_RATE", None, None, None, None
    employee, step, invalid = scan_badge(db, org, payload.qr_payload, captured, rules)
    if invalid:
        return "REJECTED", invalid, None, None, None, None
    emp_id = employee["id"]
    if not db.execute(
        "SELECT 1 FROM assignments WHERE org_id=%s AND employee_id=%s AND site_id=%s",
        (org, emp_id, site["id"]),
    ).fetchone():
        return "REJECTED", "SITE_ASSIGNMENT", emp_id, None, None, None

    evidence = None
    if evidence_enabled() and site["evidence_mode"] != "off":
        if payload.jpeg:
            try:
                evidence = clean_jpeg(payload.jpeg)
            except HTTPException:
                return "REJECTED", "INVALID_IMAGE", emp_id, None, None, None
        if not evidence and site["evidence_mode"] == "required":
            return "REJECTED", "MISSING_EVIDENCE", emp_id, None, None, None

    # Compare nearby accepted evidence so delayed batches can safely fill an earlier open shift.
    last = db.execute(
        """SELECT effective_at,shift_id,work_date FROM scan_audit WHERE org_id=%s AND employee_id=%s
        AND result IN ('ACCEPTED_IN','ACCEPTED_OUT') AND effective_at BETWEEN %s AND %s
        ORDER BY effective_at DESC LIMIT 1""", (org, emp_id, captured - timedelta(seconds=rules.debounce_seconds), captured),
    ).fetchone()
    if last and 0 <= (captured - last["effective_at"]).total_seconds() <= rules.debounce_seconds:
        return "IGNORED_DEBOUNCE", "DEBOUNCE", emp_id, last["shift_id"], last["work_date"], evidence

    if step is not None and db.execute(
        """INSERT INTO dynamic_uses VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING step""",
        (org, employee["badge_id"], step),
    ).fetchone() is None:
        return "REJECTED", "DYNAMIC_REPLAY", emp_id, None, None, evidence
    result, reason, shift_id, work_date = pair(db, employee, device, site, captured, payload.direction,
                                               version, rules, event_id)
    return result, reason, emp_id, shift_id, work_date, evidence


def receipt(row):
    return {key: row[key] for key in ("id", "client_event_id", "sequence", "event_hash", "result", "shift_id",
                                      "work_date", "received_at", "chain_advanced")}


def ingest(db, payload, device, credential, site, current):
    actual_hash = hashlib.sha256(payload.canonical()).hexdigest()
    existing = db.execute("SELECT * FROM scan_audit WHERE terminal_id=%s AND client_event_id=%s",
                          (device["id"], payload.client_event_id)).fetchone()
    if existing:
        if not hmac.compare_digest(actual_hash, existing["material_hash"]):
            raise HTTPException(409, "The event ID is already bound to different evidence")
        return receipt(existing)
    valid_chain = (
        hmac.compare_digest(actual_hash, payload.event_hash)
        and hmac.compare_digest(payload.device_mac, mac(credential.encode(), payload.event_hash))
        and payload.generation == device["generation"]
        and payload.sequence == device["last_sequence"] + 1
        and payload.previous_hash == device["last_hash"]
    )
    event_id = uuid4()
    reported = datetime.fromtimestamp(payload.captured_ms / 1000, UTC)
    captured = load_lease(payload, device, current) if valid_chain else None
    lat, lon = [value / 1_000_000 if value is not None else None for value in
                (payload.latitude_e6, payload.longitude_e6)]
    accuracy = payload.accuracy_mm / 1000 if payload.accuracy_mm is not None else None
    if valid_chain:
        result, reason, emp, shift, date, evidence = scan_effect(
            db, payload, device, site, captured, event_id, lat, lon, accuracy, current,
        )
    else:
        result, reason, emp, shift, date, evidence = ("QUARANTINED", "CHAIN_INTEGRITY", None, None, None, None)
    row = db.execute(
        """INSERT INTO scan_audit (id,org_id,terminal_id,terminal_code,site_id,employee_id,client_event_id,generation,
        sequence,event_hash,qr_digest,received_at,reported_at,effective_at,latitude,longitude,accuracy_m,
        result,reason,shift_id,work_date,chain_advanced,material_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
        (event_id, device["org_id"], device["id"], device["code"], site["id"], emp, payload.client_event_id,
         payload.generation, payload.sequence if valid_chain else None, payload.event_hash,
         mac(derived_key("scan-journal"), payload.qr_payload), current, reported, captured, lat, lon, accuracy,
         result, reason, shift, date, valid_chain, actual_hash),
    ).fetchone()
    if evidence:
        db.execute("INSERT INTO scan_evidence VALUES (%s,%s,%s)",
                   (event_id, evidence_cipher(device["org_id"]).encrypt(evidence),
                    current + timedelta(days=site["evidence_days"])))
    if valid_chain:
        db.execute("UPDATE terminals SET last_sequence=%s,last_hash=%s WHERE id=%s",
                   (payload.sequence, payload.event_hash, device["id"]))
        device.update(last_sequence=payload.sequence, last_hash=payload.event_hash)
    return receipt(row)


def ingest_batch(payloads, authorization):
    current = now()
    with transaction() as db:
        device, credential = authenticate(db, authorization, write=True)
        site = db.execute("SELECT * FROM sites WHERE org_id=%s AND id=%s", (device["org_id"], device["site_id"])).fetchone()
        receipts = []
        for payload in payloads:
            saved = ingest(db, payload, device, credential, site, current)
            receipts.append(saved)
            if not saved["chain_advanced"]:
                break
        return {"receipts": receipts, "last_contiguous_sequence_acked": device["last_sequence"]}


@router.post("/scans")
def scan(payload: Scan, authorization: str | None = Header(default=None)):
    return ingest_batch([payload], authorization)["receipts"][0]


@router.post("/scans/offline-batches")
def batch(payload: Batch, authorization: str | None = Header(default=None)):
    return ingest_batch(payload.events, authorization)
