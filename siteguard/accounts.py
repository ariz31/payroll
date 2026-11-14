import os
from typing import Annotated, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .db import control, lock_org, transaction
from .security import (CODE_PATTERN, COOKIE, LOGIN_PATTERN, authorize_site, check_password,
                       digest, hash_password, new_session, public_staff, require_role,
                       require_same_origin, reserve_attempt, staff)

router = APIRouter()
Staff = Annotated[dict, Depends(staff)]
Code = Annotated[str, StringConstraints(pattern=CODE_PATTERN)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
LoginName = Annotated[str, StringConstraints(pattern=LOGIN_PATTERN)]
Role = Literal["admin", "foreman", "engineer", "timekeeper", "auditor", "employee"]
Password = Annotated[str, StringConstraints(min_length=12, max_length=256)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Login(Input):
    organization: Code
    login: LoginName
    password: str = Field(max_length=256)


class SiteInput(Input):
    name: Name
    timezone: str = Field(min_length=1, max_length=64)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    radius_m: int = Field(ge=10, le=50000)
    active: bool = True
    evidence_mode: Literal["off", "optional", "required"] = "off"
    evidence_notice: str = Field(default="", max_length=600)
    evidence_days: int = Field(default=30, ge=1, le=90)


class StaffInput(Input):
    name: Name
    role: Role
    site_id: Code | None = None
    scope_code: Name | None = None
    employee_id: Code | None = None
    active: bool = True
    password: Password | None = None

    @model_validator(mode="after")
    def role_requirements(self):
        if self.role in {"foreman", "engineer"} and not self.site_id:
            raise ValueError("A site is required for field reviewers")
        if self.scope_code and self.role not in {"foreman", "engineer"}:
            raise ValueError("Only field reviewers can have a crew/project scope")
        if (self.role == "employee") != bool(self.employee_id):
            raise ValueError("An employee ID is required only for employee accounts")
        return self


@router.post("/auth/login")
def login(payload: Login, request: Request, response: Response):
    require_same_origin(request)
    login_name = payload.login.lower()
    slug = payload.organization.lower()
    host = request.client.host if request.client else "unknown"
    if request.headers.get("x-vercel-id"):
        host = request.headers.get("x-vercel-forwarded-for", host)
    with transaction() as db:
        client_allowed = reserve_attempt(db, f"ip/{host}", 90, 900)
        account_allowed = reserve_attempt(db, f"login/{slug}/{login_name}", 12, 900)
    if not client_allowed or not account_allowed:
        raise HTTPException(429, "Too many sign-in attempts. Try again in 15 minutes.")
    with transaction() as db:
        user = db.execute(
            """SELECT u.* FROM staff u JOIN organizations o ON o.id = u.org_id
            WHERE o.slug = %s AND u.login = %s AND u.active""",
            (slug, login_name),
        ).fetchone()
        if not check_password(payload.password, user["password_hash"] if user else None) or not user:
            raise HTTPException(401, "Incorrect organization, username or password")
        return new_session(db, user, response, request)


@router.get("/auth/me")
def whoami(user: Staff):
    return public_staff(user)


@router.post("/auth/logout")
def logout(request: Request, response: Response):
    require_same_origin(request, required=bool(request.cookies.get(COOKIE)))
    token = request.cookies.get(COOKIE)
    if token:
        with transaction() as db:
            db.execute("DELETE FROM sessions WHERE token_hash = %s", (digest(token),))
    response.delete_cookie(COOKIE, path="/")
    return {"signed_out": True}


@router.get("/sites")
def list_sites(user: Staff):
    require_role(user, "admin", "foreman", "engineer", "timekeeper", "auditor")
    with transaction() as db:
        return db.execute(
            "SELECT * FROM sites WHERE org_id = %s AND (%s::text IS NULL OR id = %s) ORDER BY name",
            (user["org_id"], user["site_id"], user["site_id"]),
        ).fetchall()


def fetch_site(db, user, site_id, active=False):
    authorize_site(user, site_id)
    row = db.execute(
        "SELECT * FROM sites WHERE org_id = %s AND id = %s AND (%s = false OR active)",
        (user["org_id"], site_id, active),
    ).fetchone()
    if not row:
        raise HTTPException(404, "Site not found")
    return row


@router.put("/sites/{site_id}")
def save_site(site_id: Code, payload: SiteInput, user: Staff):
    require_role(user, "admin")
    authorize_site(user, site_id)
    try:
        ZoneInfo(payload.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Select a valid IANA timezone") from None
    if payload.evidence_mode != "off":
        if not evidence_enabled() or not payload.evidence_notice.strip():
            raise HTTPException(422, "Enable image retention and provide the site privacy notice first")
    with transaction() as db:
        lock_org(db, user["org_id"])
        row = db.execute(
            """INSERT INTO sites (org_id,id,name,timezone,latitude,longitude,radius_m,active,evidence_mode,evidence_notice,evidence_days)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (org_id,id) DO UPDATE SET name=excluded.name,timezone=excluded.timezone,
            latitude=excluded.latitude,longitude=excluded.longitude,radius_m=excluded.radius_m,active=excluded.active,evidence_mode=excluded.evidence_mode,
            evidence_notice=excluded.evidence_notice,evidence_days=excluded.evidence_days
            RETURNING *""",
            (user["org_id"], site_id, payload.name, payload.timezone, payload.latitude, payload.longitude,
             payload.radius_m, payload.active, payload.evidence_mode, payload.evidence_notice, payload.evidence_days),
        ).fetchone()
        control(db, user["org_id"], user["id"], "site.saved", site_id, payload.model_dump())
        return row


@router.get("/users")
def list_users(user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        rows = db.execute(
            "SELECT * FROM staff WHERE org_id = %s AND (%s::text IS NULL OR site_id = %s) ORDER BY login",
            (user["org_id"], user["site_id"], user["site_id"]),
        ).fetchall()
        return [{**public_staff(row), "active": row["active"]} for row in rows]


def save_account(db, user, login_name, payload):
    org_id = user["org_id"]
    lock_org(db, org_id)
    if user["site_id"] and (not payload.site_id or payload.role == "admin"):
        raise HTTPException(403, "A site administrator cannot grant organization-wide access")
    if payload.site_id:
        fetch_site(db, user, payload.site_id)
    previous = db.execute(
        "SELECT * FROM staff WHERE org_id = %s AND login = %s", (org_id, login_name),
    ).fetchone()
    if previous and user["site_id"] and (previous["site_id"] != user["site_id"] or previous["role"] == "admin"):
        raise HTTPException(404, "Account not found")
    if previous and previous["id"] == user["id"] and (not payload.active or payload.role != "admin"
                                                      or payload.site_id != user["site_id"]):
        raise HTTPException(409, "Another administrator must change your access")
    if payload.employee_id and not db.execute(
        """SELECT 1 FROM assignments WHERE org_id=%s AND employee_id=%s
        AND (%s::text IS NULL OR site_id=%s) AND (%s::text IS NULL OR site_id=%s)""",
        (org_id, payload.employee_id, user["site_id"], user["site_id"], payload.site_id, payload.site_id),
    ).fetchone():
        raise HTTPException(422, "Employee account must be linked to a registered worker in scope")
    password_hash = hash_password(payload.password) if payload.password else (previous or {}).get("password_hash")
    row = db.execute(
        """INSERT INTO staff (id,org_id,login,name,role,site_id,scope_code,employee_id,active,password_hash)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (org_id,login) DO UPDATE SET name=excluded.name, role=excluded.role,
        site_id=excluded.site_id, scope_code=excluded.scope_code, employee_id=excluded.employee_id,
        active=excluded.active,password_hash=excluded.password_hash RETURNING *""",
        (uuid4(), org_id, login_name, payload.name, payload.role, payload.site_id, payload.scope_code,
         payload.employee_id, payload.active, password_hash),
    ).fetchone()
    if previous and (payload.password or any(previous[field] != row[field]
                                              for field in ("role", "active", "site_id", "scope_code", "employee_id"))):
        db.execute("DELETE FROM sessions WHERE staff_id = %s", (row["id"],))
    control(db, org_id, user["id"], "account.saved", row["id"], {
        "login": row["login"], "role": row["role"], "site_id": row["site_id"], "active": row["active"],
    })
    return {**public_staff(row), "active": row["active"]}


@router.put("/users/{login_name}")
def put_user(login_name: LoginName, payload: StaffInput, user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        return save_account(db, user, login_name.lower(), payload)


def evidence_enabled():
    return os.getenv("SITEGUARD_EVIDENCE_ENABLED", "").lower() == "true"
