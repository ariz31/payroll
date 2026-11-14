import base64
import hmac
import io
import secrets
from datetime import timedelta
from math import asin, cos, radians, sin, sqrt
from typing import Literal
from uuid import UUID, uuid4

import segno
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from fastapi import APIRouter, HTTPException, Request, Response
from PIL import Image, UnidentifiedImageError
from pydantic import Field
from psycopg.types.json import Jsonb

from .accounts import Code, Input, Name, Staff, evidence_enabled, fetch_site
from .db import control, lock_org, now, transaction
from .security import authorize_site, derived_key, digest, previous_secrets, require_role, secret
from .timekeeping import Policy, policy

router = APIRouter()


class EmployeeInput(Input):
    name: Name
    department: Name
    cost_code: Name
    crew: Name
    shift_type: Literal["Day Shift", "Night Shift"]
    site_ids: list[Code] = Field(min_length=1, max_length=30)
    active: bool = True


class TerminalInput(Input):
    name: Name
    site_id: Code
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    active: bool = True


class BadgeInput(Input):
    employee_id: Code
    mode: Literal["DYN", "STC"]


class ImageInput(Input):
    jpeg: str = Field(max_length=88000)


def employees_for(db, user, employee_id=None):
    return db.execute(
        """SELECT e.*, array_agg(a.site_id ORDER BY a.site_id) AS site_ids FROM employees e
        JOIN assignments a ON (e.org_id,e.id)=(a.org_id,a.employee_id)
        WHERE e.org_id=%s AND (%s::text IS NULL OR a.site_id=%s) AND (%s::text IS NULL OR e.id=%s)
        GROUP BY e.org_id,e.id ORDER BY e.id""",
        (user["org_id"], user["site_id"], user["site_id"], employee_id, employee_id),
    ).fetchall()


def employee_for(db, user, employee_id):
    found = employees_for(db, user, employee_id)
    if not found:
        raise HTTPException(404, "Employee not found")
    return found[0]


@router.get("/employees")
def list_employees(user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        return employees_for(db, user)


@router.get("/employees/{employee_id}")
def read_employee(employee_id: Code, user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        return employee_for(db, user, employee_id)


@router.put("/employees/{employee_id}")
def save_employee(employee_id: Code, payload: EmployeeInput, user: Staff):
    require_role(user, "admin")
    org = user["org_id"]
    with transaction() as db:
        lock_org(db, org)
        for site_id in set(payload.site_ids):
            fetch_site(db, user, site_id)
        previous = db.execute("SELECT 1 FROM employees WHERE org_id=%s AND id=%s", (org, employee_id)).fetchone()
        if previous and user["site_id"]:
            scope = db.execute("SELECT site_id FROM assignments WHERE org_id=%s AND employee_id=%s",
                               (org, employee_id)).fetchall()
            if {item["site_id"] for item in scope} != {user["site_id"]}:
                raise HTTPException(403, "This employee requires an organization administrator")
        db.execute(
            """INSERT INTO employees VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (org_id,id) DO UPDATE SET name=excluded.name,department=excluded.department,
            cost_code=excluded.cost_code,crew=excluded.crew,shift_type=excluded.shift_type,active=excluded.active""",
            (org, employee_id, payload.name, payload.department, payload.cost_code, payload.crew,
             payload.shift_type, payload.active),
        )
        db.execute("DELETE FROM assignments WHERE org_id=%s AND employee_id=%s", (org, employee_id))
        with db.cursor() as cursor:
            cursor.executemany("INSERT INTO assignments VALUES (%s,%s,%s)",
                               [(org, employee_id, site_id) for site_id in sorted(set(payload.site_ids))])
        control(db, org, user["id"], "employee.saved", employee_id, {
            "active": payload.active, "site_ids": payload.site_ids, "shift_type": payload.shift_type,
        })
        return employee_for(db, user, employee_id)


def distance(lat1, lon1, lat2, lon2):
    north = sin(radians(lat2 - lat1) / 2) ** 2
    east = cos(radians(lat1)) * cos(radians(lat2)) * sin(radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371000 * asin(min(1, sqrt(north + east)))


def public_terminal(row):
    return {key: row[key] for key in ("id", "code", "name", "site_id", "latitude", "longitude",
                                      "active", "generation")}


@router.get("/terminals")
def list_terminals(user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        rows = db.execute(
            """SELECT * FROM terminals WHERE org_id=%s AND (%s::text IS NULL OR site_id=%s) ORDER BY code""",
            (user["org_id"], user["site_id"], user["site_id"]),
        )
        return [public_terminal(row) for row in rows]


def save_terminal(db, user, code, payload=None, rotate=False):
    org = user["org_id"]
    lock_org(db, org)
    row = db.execute("SELECT * FROM terminals WHERE org_id=%s AND code=%s", (org, code)).fetchone()
    if row:
        authorize_site(user, row["site_id"])
    if rotate and not row:
        raise HTTPException(404, "Terminal not found")
    if payload:
        site = fetch_site(db, user, payload.site_id, active=payload.active)
        if payload.active and distance(site["latitude"], site["longitude"], payload.latitude,
                                       payload.longitude) > site["radius_m"]:
            raise HTTPException(422, "Enrolled terminal coordinates must be inside the site perimeter")
        if row and row["site_id"] != payload.site_id:
            raise HTTPException(409, "Enroll a new terminal code when moving to a different site")
    ident = row["id"] if row else uuid4()
    credential = f"{ident}.{secrets.token_urlsafe(32)}" if rotate or not row else None
    if not row:
        row = db.execute(
            """INSERT INTO terminals (id,org_id,code,name,site_id,latitude,longitude,active,credential_hash)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
            (ident, org, code, payload.name, payload.site_id, payload.latitude, payload.longitude, payload.active,
             digest(credential)),
        ).fetchone()
    elif rotate:
        row = db.execute(
            """UPDATE terminals SET credential_hash=%s,generation=generation+1,last_sequence=0,last_hash=''
            WHERE id=%s RETURNING *""", (digest(credential), ident),
        ).fetchone()
    else:
        row = db.execute(
            "UPDATE terminals SET name=%s,latitude=%s,longitude=%s,active=%s WHERE id=%s RETURNING *",
            (payload.name, payload.latitude, payload.longitude, payload.active, ident),
        ).fetchone()
    control(db, org, user["id"], "terminal.rotated" if rotate else "terminal.saved", code,
            {"site": row["site_id"], "generation": row["generation"], "active": row["active"]})
    return {**public_terminal(row), **({"credential": credential} if credential else {})}


@router.put("/terminals/{code}")
def put_terminal(code: Code, payload: TerminalInput, user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        return save_terminal(db, user, code, payload)


@router.post("/terminals/{code}/rotate")
def rotate_terminal(code: Code, user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        return save_terminal(db, user, code, rotate=True)


def permit_badge_admin(db, user, employee_id):
    employee = employee_for(db, user, employee_id)
    if user["site_id"] and db.execute(
        "SELECT 1 FROM assignments WHERE org_id=%s AND employee_id=%s AND site_id<>%s",
        (user["org_id"], employee_id, user["site_id"]),
    ).fetchone():
        raise HTTPException(403, "This badge requires an organization administrator")
    return employee


@router.get("/badges")
def list_badges(user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        return db.execute(
            """SELECT b.id,b.employee_id,b.mode,b.created_at,b.revoked_at FROM badges b WHERE org_id=%s
            AND (%s::text IS NULL OR EXISTS (SELECT 1 FROM assignments a
                WHERE (b.org_id,b.employee_id)=(a.org_id,a.employee_id) AND a.site_id=%s))
            ORDER BY b.created_at DESC""", (user["org_id"], user["site_id"], user["site_id"]),
        ).fetchall()


@router.post("/badges/issue", status_code=201)
def issue_badge(payload: BadgeInput, user: Staff):
    require_role(user, "admin")
    org = user["org_id"]
    with transaction() as db:
        lock_org(db, org)
        employee = permit_badge_admin(db, user, payload.employee_id)
        if not employee["active"]:
            raise HTTPException(409, "Reactivate the employee before issuing a badge")
        db.execute(
            "UPDATE badges SET revoked_at=clock_timestamp() WHERE org_id=%s AND employee_id=%s AND mode=%s AND revoked_at IS NULL",
            (org, payload.employee_id, payload.mode),
        )
        row = db.execute(
            "INSERT INTO badges (org_id,id,employee_id,mode) VALUES (%s,%s,%s,%s) RETURNING *",
            (org, uuid4(), payload.employee_id, payload.mode),
        ).fetchone()
        control(db, org, user["id"], "badge.issued", row["id"], {"employee": payload.employee_id, "mode": payload.mode})
        return row


@router.post("/badges/{badge_id}/revoke")
def revoke_badge(badge_id: UUID, user: Staff):
    require_role(user, "admin")
    org = user["org_id"]
    with transaction() as db:
        lock_org(db, org)
        row = db.execute("SELECT * FROM badges WHERE org_id=%s AND id=%s", (org, badge_id)).fetchone()
        if not row:
            raise HTTPException(404, "Badge not found")
        permit_badge_admin(db, user, row["employee_id"])
        if not row["revoked_at"]:
            row = db.execute("UPDATE badges SET revoked_at=clock_timestamp() WHERE org_id=%s AND id=%s RETURNING *",
                             (org, badge_id)).fetchone()
            control(db, org, user["id"], "badge.revoked", badge_id)
        return row


def badge_tag(row, marker, root=None):
    key = derived_key(f"badge/{row['mode']}/{row['org_id']}/{row['id']}", root)
    return hmac.digest(key, f"{row['mode']}|{row['employee_id']}|{marker}".encode(), "sha256").hex()[:16]


def badge_code(row, marker):
    return f"{row['mode']}|{row['employee_id']}|{marker}|{badge_tag(row, marker)}"


def badge_marker(row, rules, current):
    return "STATIC" if row["mode"] == "STC" else str(int(current.timestamp()) // rules.qr_step_seconds)


def badge_svg(payload):
    output = io.BytesIO()
    segno.make(payload, error="m", micro=False).save(output, kind="svg", scale=6, xmldecl=False, light="#fff")
    return output.getvalue().decode()


def present_badge(row, rules):
    current = now()
    marker = badge_marker(row, rules, current)
    raw = badge_code(row, marker)
    refresh_after_ms = None
    if marker != "STATIC":
        refresh_after_ms = max(250, int(((int(marker) + 1) * rules.qr_step_seconds - current.timestamp()) * 1000))
    return {"id": row["id"], "employee_id": row["employee_id"], "mode": row["mode"],
            "payload": raw, "svg": badge_svg(raw), "refresh_after_ms": refresh_after_ms}


@router.get("/badges/mine")
def my_badge(user: Staff):
    require_role(user, "employee")
    with transaction() as db:
        _, rules = policy(db, user["org_id"])
        row = db.execute(
            """SELECT b.* FROM badges b JOIN employees e ON (b.org_id,b.employee_id)=(e.org_id,e.id)
            WHERE b.org_id=%s AND b.employee_id=%s AND b.mode='DYN' AND b.revoked_at IS NULL AND e.active""",
            (user["org_id"], user["employee_id"]),
        ).fetchone()
        if not row:
            raise HTTPException(404, "No active dynamic badge")
        return present_badge(row, rules)


@router.get("/badges/{badge_id}/code")
def read_badge(badge_id: UUID, user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        row = db.execute("SELECT * FROM badges WHERE org_id=%s AND id=%s AND revoked_at IS NULL",
                         (user["org_id"], badge_id)).fetchone()
        if not row:
            raise HTTPException(404, "Badge not found")
        permit_badge_admin(db, user, row["employee_id"])
        _, rules = policy(db, user["org_id"])
        control(db, user["org_id"], user["id"], "badge.displayed", badge_id)
        return present_badge(row, rules)


@router.get("/config")
def get_config(user: Staff):
    require_role(user, "admin")
    with transaction() as db:
        version, settings = policy(db, user["org_id"])
        return {"version": version, "settings": settings}


@router.put("/config")
def update_config(payload: Policy, user: Staff):
    require_role(user, "admin")
    if user["site_id"]:
        raise HTTPException(403, "Only an organization administrator can change this policy")
    org = user["org_id"]
    with transaction() as db:
        lock_org(db, org)
        version, current_policy = policy(db, org)
        if current_policy == payload:
            return {"version": version, "settings": payload}
        version += 1
        db.execute("INSERT INTO policy_versions (org_id,version,settings) VALUES (%s,%s,%s)",
                   (org, version, Jsonb(payload.model_dump(mode="json"))))
        control(db, org, user["id"], "policy.updated", version)
        return {"version": version, "settings": payload}


def evidence_cipher(org):
    keys = [Fernet(base64.urlsafe_b64encode(derived_key(f"evidence/{org}", root)))
            for root in [secret(), *previous_secrets()]]
    return MultiFernet(keys)


def clean_jpeg(encoded):
    try:
        data = base64.b64decode(encoded, validate=True)
        if len(data) > 64000:
            raise ValueError
        with Image.open(io.BytesIO(data), formats=("JPEG",)) as image:
            if image.width * image.height > 800 * 600:
                raise ValueError
            image.thumbnail((480, 360))
            output = io.BytesIO()
            image.convert("RGB").save(output, "JPEG", quality=65, optimize=True)
            return output.getvalue()
    except (OSError, ValueError, UnidentifiedImageError, Image.DecompressionBombError):
        raise HTTPException(422, "Image evidence must be a small JPEG") from None


@router.put("/employees/{employee_id}/badge-image")
def save_badge_image(employee_id: Code, payload: ImageInput, user: Staff):
    require_role(user, "admin")
    if not evidence_enabled():
        raise HTTPException(403, "Image retention is disabled")
    image = clean_jpeg(payload.jpeg)
    org = user["org_id"]
    with transaction() as db:
        employee = permit_badge_admin(db, user, employee_id)
        limits = db.execute(
            """SELECT min(evidence_days) AS days FROM sites WHERE org_id=%s AND id=ANY(%s)
            AND evidence_mode<>'off' AND active""", (org, employee["site_ids"]),
        ).fetchone()
        if not limits["days"]:
            raise HTTPException(409, "No assigned active site has enabled camera evidence")
        db.execute(
            """INSERT INTO profile_evidence VALUES (%s,%s,%s,%s) ON CONFLICT (org_id,employee_id)
            DO UPDATE SET sealed=excluded.sealed,expires_at=excluded.expires_at""",
            (org, employee_id, evidence_cipher(org).encrypt(image), now() + timedelta(days=limits["days"])),
        )
        control(db, org, user["id"], "badge-image.saved", employee_id)
    return {"saved": True}


def image_response(sealed, org):
    try:
        return Response(evidence_cipher(org).decrypt(sealed), media_type="image/jpeg")
    except InvalidToken:
        raise HTTPException(503, "Image is temporarily unavailable") from None
