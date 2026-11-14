import hmac
import re
import secrets
from collections import defaultdict
from uuid import UUID, uuid4

from fastapi import APIRouter, Header, HTTPException, Query

from .accounts import Code, Input, Name, Staff, fetch_site
from .db import control, lock_org, transaction
from .payroll import snapshot, totals, validate_period
from .security import digest, require_role
from .timekeeping import VERIFIED

router = APIRouter()
META = "id,name,site_id,created_at,revoked_at"


class IntegrationInput(Input):
    name: Name
    site_id: Code | None = None


def org_admin(user):
    require_role(user, "admin")
    if user["site_id"]:
        raise HTTPException(403, "Only an organization administrator can manage payroll integrations")


@router.get("/integrations/payroll")
def integrations(user: Staff):
    org_admin(user)
    with transaction() as db:
        return db.execute(f"SELECT {META} FROM payroll_integrations WHERE org_id=%s ORDER BY created_at DESC",
                          (user["org_id"],)).fetchall()


@router.post("/integrations/payroll", status_code=201)
def issue_integration(payload: IntegrationInput, user: Staff):
    org_admin(user)
    ident = uuid4()
    credential = f"{ident}.{secrets.token_urlsafe(32)}"
    with transaction() as db:
        lock_org(db, user["org_id"])
        if payload.site_id:
            fetch_site(db, user, payload.site_id, active=True)
        row = db.execute(
            f"""INSERT INTO payroll_integrations (id,org_id,name,site_id,credential_hash,created_by)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING {META}""",
            (ident, user["org_id"], payload.name, payload.site_id, digest(credential), user["id"]),
        ).fetchone()
        control(db, user["org_id"], user["id"], "integration.issued", ident, {"site": payload.site_id})
        return {**row, "credential": credential}


@router.post("/integrations/payroll/{ident}/revoke")
def revoke_integration(ident: UUID, user: Staff):
    org_admin(user)
    org = user["org_id"]
    with transaction() as db:
        lock_org(db, org)
        row = db.execute(
            f"SELECT {META} FROM payroll_integrations WHERE id=%s AND org_id=%s", (ident, org),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Payroll integration not found")
        if row["revoked_at"]:
            return row
        updated = db.execute(
            f"UPDATE payroll_integrations SET revoked_at=clock_timestamp() WHERE id=%s RETURNING {META}", (ident,),
        ).fetchone()
        control(db, org, user["id"], "integration.revoked", ident)
        return updated


def authenticate_integration(db, auth):
    try:
        scheme, credential = auth.split(" ")
        ident, value = credential.split(".")
        if scheme.lower() != "bearer" or not re.fullmatch(r"[A-Za-z0-9_-]{43}", value):
            raise ValueError
        ident = UUID(ident)
    except ValueError:
        raise HTTPException(401, "A valid payroll integration credential is required") from None
    row = db.execute(
        """SELECT i.* FROM payroll_integrations i LEFT JOIN sites s ON (i.org_id,i.site_id)=(s.org_id,s.id)
        WHERE i.id=%s AND i.revoked_at IS NULL AND (i.site_id IS NULL OR s.active)""", (ident,),
    ).fetchone()
    if not row or not hmac.compare_digest(row["credential_hash"], digest(credential)):
        raise HTTPException(401, "A valid payroll integration credential is required")
    return row


@router.get("/integrations/payroll/periods/{period}")
def payroll_feed(period: str, authorization: str = Header(default="", max_length=256),
                 snapshot_key: str | None = Query(default=None, pattern=r"^[a-f0-9]{64}$"),
                 offset: int = Query(default=0, ge=0), limit: int = Query(default=250, ge=1, le=1000)):
    validate_period(period)
    if offset and not snapshot_key:
        raise HTTPException(422, "Pass the first page snapshot key when paging")
    with transaction() as db:
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        channel = authenticate_integration(db, authorization)
        user = {"org_id": channel["org_id"], "site_id": channel["site_id"], "role": "integration"}
        rows, summary = snapshot(db, user, period, channel["site_id"])
        if snapshot_key is not None and snapshot_key != summary["snapshot_key"]:
            raise HTTPException(409, "The release snapshot changed. Discard fetched pages and start again.")
        held = set(summary["audit_hold_employee_ids"])
        eligible = defaultdict(list)
        for row in rows:
            if row["status"] == VERIFIED and row["employee_id"] not in held:
                eligible[row["employee_id"]].append(row)
        ordered = sorted(eligible)
        control(db, channel["org_id"], None, "integration.read", channel["id"],
                {"period": period, "offset": offset, "snapshot_key": summary["snapshot_key"]})
        end = offset + limit
        return {"period": period, "site_id": channel["site_id"], "snapshot_key": summary["snapshot_key"],
                "held_employee_count": len(held), "total_employees": len(ordered),
                "next_offset": end if end < len(ordered) else None,
                "items": [{"employee_id": ident, **totals(eligible[ident])} for ident in ordered[offset:end]]}
