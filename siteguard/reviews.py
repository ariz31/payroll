from datetime import date, timedelta
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query
from psycopg.errors import CheckViolation, InsufficientPrivilege, SerializationFailure
from pydantic import AwareDatetime, Field, field_validator, model_validator

from .accounts import Code, Input, Staff, evidence_enabled
from .db import control, lock_org, now, transaction
from .registry import image_response
from .security import digest, require_role
from .timekeeping import calculate, policy, scheduled

router = APIRouter()
REVIEWERS = ("admin", "foreman", "engineer", "timekeeper", "auditor", "employee")
Period = Query(pattern=r"^20[0-9]{2}-(0[1-9]|1[0-2])$")
FOREMAN = {"endorse", "request_evidence"}
ENGINEER = {"cost_approve", "cost_reject", "return_foreman"}
TIMEKEEPER = {"verify", "reject", "return_engineer", "reopen"}


class Review(Input):
    action: Literal["endorse", "request_evidence", "cost_approve", "cost_reject", "return_foreman",
                    "verify", "reject", "return_engineer", "reopen"]
    request_id: UUID
    version: int = Field(ge=1)
    notes: str = Field(min_length=1, max_length=1500)
    adjusted_in: AwareDatetime | None = None
    adjusted_out: AwareDatetime | None = None

    @field_validator("notes")
    @classmethod
    def trim(cls, value):
        if not value.strip():
            raise ValueError("A review reason is required")
        return value.strip()


class BulkItem(Input):
    id: UUID
    version: int = Field(ge=1)


class Bulk(Input):
    request_id: UUID
    items: list[BulkItem] = Field(min_length=1, max_length=100)


class Reconciliation(Input):
    disposition: Literal["dismissed", "linked_for_review"]
    notes: str = Field(min_length=1, max_length=1500)
    shift_id: UUID | None = None

    @model_validator(mode="after")
    def validate_decision(self):
        self.notes = self.notes.strip()
        if not self.notes:
            raise ValueError("Record the evidence or reason")
        if (self.disposition == "linked_for_review") != bool(self.shift_id):
            raise ValueError("A linked decision requires the pending shift ID")
        return self


def bounds(period):
    year, month = map(int, period.split("-"))
    first = date(year, month, 1)
    return first, date(year + (month == 12), month % 12 + 1, 1)


def scoped(user, alias="s"):
    terms = [f"{alias}.org_id=%s"]
    params = [user["org_id"]]
    if user["site_id"]:
        terms.append(f"{alias}.site_id=%s")
        params.append(user["site_id"])
    if user["role"] in {"engineer", "foreman"} and user["scope_code"]:
        terms.append(f"{alias}." + ("cost_code" if user["role"] == "engineer" else "crew") + "=%s")
        params.append(user["scope_code"])
    if user["role"] == "employee":
        terms.append(f"{alias}.employee_id=%s")
        params.append(user["employee_id"])
    return " AND ".join(terms), params


def shift_for(db, user, ident):
    where, params = scoped(user)
    row = db.execute(f"SELECT s.* FROM shifts s WHERE {where} AND s.id=%s", (*params, ident)).fetchone()
    if not row:
        raise HTTPException(404, "Shift not found")
    return row


def project(db, rows, current):
    policies = {}
    rendered = []
    for row in rows:
        key = (row["org_id"], row["policy_version"])
        if key not in policies:
            policies[key] = policy(db, *key)[1]
        rules = policies[key]
        rendered.append({**row, **calculate(row, rules, current)})
    return rendered


def period_shifts(db, user, period, site=None, employee=None):
    where, params = scoped(user)
    start, end = bounds(period)
    return db.execute(
        f"""SELECT s.* FROM shifts s WHERE {where} AND s.work_date >= %s AND s.work_date < %s
        AND (%s::text IS NULL OR s.site_id=%s) AND (%s::text IS NULL OR s.employee_id=%s)
        ORDER BY s.work_date,s.employee_id,s.id""", (*params, start, end, site, site, employee, employee),
    ).fetchall()


def call_review(db, row, actor, request_id, version, action, reason,
                adjusted_in=None, adjusted_out=None, request_digest=None):
    try:
        db.execute("SELECT review_shift(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (
            row["id"], actor, request_id, version, action, reason, adjusted_in, adjusted_out,
            request_digest or digest(action + reason),
        ))
    except SerializationFailure:
        raise HTTPException(409, "This shift or review request has changed. Refresh and try again.") from None
    except InsufficientPrivilege:
        raise HTTPException(403, "This reviewer cannot act on the shift") from None
    except CheckViolation as exc:
        raise HTTPException(409, exc.diag.message_primary or "This review transition is not permitted") from None


def reproject_active(db, user, version):
    rows = db.execute(
        """SELECT * FROM shifts WHERE org_id=%s AND policy_version<>%s
        AND stage IN ('foreman','engineer','timekeeper') ORDER BY id""", (user["org_id"], version),
    ).fetchall()
    for row in rows:
        call_review(db, row, user["id"], uuid4(), row["version"], "policy_changed", f"Applied policy version {version}")


def automatically_verify(db, result, shift_id, current):
    if result not in {"ACCEPTED_IN", "ACCEPTED_OUT"}:
        return
    row = db.execute("SELECT * FROM shifts WHERE id=%s", (shift_id,)).fetchone()
    _, rules = policy(db, row["org_id"], row["policy_version"])
    if rules.auto_verify_ok_scans and row["raw_in"] and row["raw_out"] and not db.execute(
        "SELECT 1 FROM approval_audit WHERE shift_id=%s", (shift_id,),
    ).fetchone() and calculate(row, rules, current)["anomaly"] == "OK":
        call_review(db, row, None, uuid4(), row["version"], "auto_verify", "Clean shift verified by configured policy")


def history(db, ident):
    return db.execute(
        """SELECT id,actor_name,occurred_at,action,reason, before_state,after_state
        FROM approval_audit WHERE shift_id=%s ORDER BY id""", (ident,),
    ).fetchall()


def enrichment(db, row):
    images = db.execute(
        """SELECT EXISTS(SELECT 1 FROM profile_evidence WHERE org_id=%s AND employee_id=%s
           AND expires_at>clock_timestamp()) AS badge,
           ARRAY(SELECT event_id FROM scan_evidence WHERE event_id IN (%s,%s)
           AND expires_at>clock_timestamp()) AS scans""",
        (row["org_id"], row["employee_id"], row["in_event"], row["out_event"]),
    ).fetchone()
    return images


@router.get("/shifts")
def list_shifts(user: Staff, period: str = Period, site: Code | None = None, employee: Code | None = None,
                status: str | None = None, anomaly: str | None = None, stage: str | None = None,
                cost_code: str | None = Query(default=None, max_length=120),
                department: str | None = Query(default=None, max_length=120),
                shift_type: Literal["Day Shift", "Night Shift"] | None = None,
                work_date: date | None = None, offset: int = Query(default=0, ge=0),
                limit: int = Query(default=100, ge=1, le=250)):
    require_role(user, *REVIEWERS)
    with transaction() as db:
        rows = project(db, period_shifts(db, user, period, site, employee), now())
    filters = {"status": status, "anomaly": anomaly, "stage": stage, "cost_code": cost_code,
               "department": department, "shift_type": shift_type, "work_date": work_date}
    found = [row for row in rows if all(value is None or row[key] == value for key, value in filters.items())]
    return {"items": found[offset:offset + limit], "total": len(found)}


@router.get("/shifts/{ident}")
def shift_detail(ident: UUID, user: Staff):
    require_role(user, *REVIEWERS)
    with transaction() as db:
        shift = shift_for(db, user, ident)
        row = project(db, [shift], now())[0]
        if user["role"] != "employee":
            row["history"] = history(db, ident)
            row["reconciled_scans"] = db.execute(
                """SELECT event_id, actor_login, decided_at, notes FROM scan_reconciliations
                WHERE org_id=%s AND shift_id=%s ORDER BY decided_at""", (user["org_id"], ident),
            ).fetchall()
        if evidence_enabled() and user["role"] in {"timekeeper", "auditor"}:
            row["evidence"] = enrichment(db, shift)
        return row


@router.post("/shifts/bulk-verify")
def bulk_verify(payload: Bulk, user: Staff):
    require_role(user, "timekeeper")
    if len({item.id for item in payload.items}) != len(payload.items):
        raise HTTPException(422, "Select each shift only once")
    with transaction() as db:
        lock_org(db, user["org_id"])
        for item in payload.items:
            row = shift_for(db, user, item.id)
            call_review(db, row, user["id"], payload.request_id, item.version, "bulk_verify",
                        "Complete clean shift approved in bulk", request_digest=digest(str(item.version)))
    return {"verified": len(payload.items)}


@router.post("/shifts/{ident}/review")
def apply_review(ident: UUID, payload: Review, user: Staff):
    require_role(user, "foreman" if payload.action in FOREMAN else
                 "engineer" if payload.action in ENGINEER else "timekeeper")
    with transaction() as db:
        lock_org(db, user["org_id"])
        row = shift_for(db, user, ident)
        if payload.adjusted_in or payload.adjusted_out:
            _, rules = policy(db, row["org_id"], row["policy_version"])
            start, end = scheduled(row["work_date"], row["timezone"], row["shift_type"], rules)
            for value in (payload.adjusted_in, payload.adjusted_out):
                if value and not start - timedelta(hours=12) <= value <= end + timedelta(hours=12):
                    raise HTTPException(422, "Adjustments must belong to this shift window")
        call_review(db, row, user["id"], payload.request_id, payload.version, payload.action, payload.notes,
                    payload.adjusted_in, payload.adjusted_out, digest(payload.model_dump_json()))
        return project(db, [shift_for(db, user, ident)], now())[0]


@router.get("/shifts/{ident}/evidence/{kind}")
def get_evidence(ident: UUID, kind: Literal["badge", "in", "out"], user: Staff):
    require_role(user, "timekeeper", "auditor")
    if not evidence_enabled():
        raise HTTPException(404, "Image evidence is disabled")
    with transaction() as db:
        row = shift_for(db, user, ident)
        if kind == "badge":
            image = db.execute("""SELECT sealed FROM profile_evidence WHERE org_id=%s AND employee_id=%s
                               AND expires_at>clock_timestamp()""", (row["org_id"], row["employee_id"])).fetchone()
        else:
            image = db.execute("SELECT sealed FROM scan_evidence WHERE event_id=%s AND expires_at>clock_timestamp()",
                               (row[f"{kind}_event"],)).fetchone()
        if not image:
            raise HTTPException(404, "No retained image evidence")
        response = image_response(image["sealed"], row["org_id"])
        control(db, row["org_id"], user["id"], "evidence.viewed", row["id"], {"kind": kind})
        return response


@router.get("/audit/scans")
def scan_audit(user: Staff, site: Code | None = None, result: str | None = Query(default=None, max_length=30),
               unresolved: bool = False, offset: int = Query(default=0, ge=0),
               limit: int = Query(default=100, ge=1, le=250)):
    require_role(user, "admin", "timekeeper", "auditor")
    with transaction() as db:
        where, params = scoped(user, "a")
        return db.execute(
            f"""SELECT a.id,a.terminal_code,a.site_id,a.employee_id,a.client_event_id,a.generation,a.sequence,
             a.event_hash,a.received_at,a.reported_at,a.effective_at,a.result,a.reason,a.shift_id,a.work_date,
             a.chain_advanced,r.disposition,r.shift_id AS linked_shift,r.actor_login,r.notes AS reconciliation_notes
             FROM scan_audit a LEFT JOIN scan_reconciliations r ON r.event_id=a.id
             WHERE {where} AND (%s::text IS NULL OR a.site_id=%s)
             AND (%s::text IS NULL OR a.result=%s)
             AND (NOT %s OR (a.result='QUARANTINED' AND r.event_id IS NULL))
             ORDER BY a.received_at DESC,a.id LIMIT %s OFFSET %s""",
            (*params, site, site, result, result, unresolved, limit, offset),
        ).fetchall()


@router.post("/audit/scans/{ident}/reconcile")
def reconcile(ident: UUID, payload: Reconciliation, user: Staff):
    require_role(user, "timekeeper")
    with transaction() as db:
        lock_org(db, user["org_id"])
        where, params = scoped(user, "a")
        if not db.execute(f"SELECT 1 FROM scan_audit a WHERE {where} AND a.id=%s AND result='QUARANTINED'",
                          (*params, ident)).fetchone():
            raise HTTPException(404, "Quarantined scan not found")
        try:
            return db.execute("SELECT * FROM reconcile_scan(%s,%s,%s,%s,%s)",
                              (ident, user["id"], payload.disposition, payload.notes, payload.shift_id)).fetchone()
        except SerializationFailure:
            raise HTTPException(409, "This scan already has a reconciliation decision") from None
        except CheckViolation as exc:
            raise HTTPException(409, exc.diag.message_primary or "This reconciliation is invalid") from None


@router.get("/audit/approvals")
def approval_audit(user: Staff, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=250)):
    require_role(user, "admin", "foreman", "engineer", "timekeeper", "auditor")
    where, params = scoped(user)
    with transaction() as db:
        return db.execute(
            f"""SELECT a.id,a.shift_id,a.actor_name,a.occurred_at,a.action,a.reason,s.employee_id,s.site_id
             FROM approval_audit a JOIN shifts s ON s.id=a.shift_id WHERE {where}
             ORDER BY a.id DESC LIMIT %s OFFSET %s""", (*params, limit, offset),
        ).fetchall()


@router.get("/audit/control")
def control_audit(user: Staff, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=250)):
    require_role(user, "admin", "auditor")
    if user["site_id"]:
        raise HTTPException(403, "Organization-wide audit access is required")
    with transaction() as db:
        return db.execute("""SELECT a.id,a.action,a.occurred_at,a.object_id,a.detail,u.login
                          FROM control_audit a LEFT JOIN staff u ON u.id=a.actor_id
                          WHERE a.org_id=%s ORDER BY a.id DESC LIMIT %s OFFSET %s""",
                          (user["org_id"], limit, offset)).fetchall()
