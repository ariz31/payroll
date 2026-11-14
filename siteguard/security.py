import hashlib
import hmac
import os
import re
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response

from .db import now, transaction

COOKIE = "siteguard_session"
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}
DUMMY_SALT = bytes(16)
LOGIN_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9@._+-]{1,119}$"
CODE_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def secret():
    value = os.getenv("SITEGUARD_SECRET", "")
    if len(value.encode()) < 32:
        raise HTTPException(503, "SiteGuard service configuration is incomplete")
    return value.encode()


def derived_key(purpose, root=None):
    return hmac.digest(root if root is not None else secret(), f"siteguard/v1/{purpose}".encode(), "sha256")


def previous_secrets():
    return [value.encode() for value in os.getenv("SITEGUARD_PREVIOUS_SECRETS", "").split(",") if value]


def hash_password(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    result = hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=3, maxmem=64 * 1024**2)
    return f"scrypt-3:{salt.hex()}:{result.hex()}"


def check_password(password, stored):
    salt = bytes.fromhex(stored.split(":")[1]) if stored else DUMMY_SALT
    if stored and stored.startswith("scrypt:"):
        result = hashlib.scrypt(password.encode(), salt=salt, n=2**15, r=8, p=1, maxmem=64 * 1024**2)
        candidate = f"scrypt:{salt.hex()}:{result.hex()}"
    else:
        candidate = hash_password(password, salt)
    return hmac.compare_digest(candidate, stored or "") and bool(stored)


def valid_host_origin(request):
    configured = os.getenv("SITEGUARD_ORIGIN", "").rstrip("/")
    if configured:
        return configured
    host = request.url.netloc
    scheme = "https" if os.getenv("VERCEL") else request.url.scheme
    return f"{scheme}://{host}"


def require_same_origin(request, required=False):
    origin = request.headers.get("origin")
    if (required or origin is not None) and origin != valid_host_origin(request):
        raise HTTPException(403, "The request origin is not permitted")


def reserve_attempt(db, bucket, limit, window_seconds):
    tick = int(now().timestamp())
    window = tick // window_seconds * window_seconds
    row = db.execute(
        """INSERT INTO attempt_limits (bucket, window_start, count) VALUES (%s,%s,1)
        ON CONFLICT (bucket, window_start) DO UPDATE SET count = attempt_limits.count + 1
        RETURNING count""",
        (digest(bucket), window),
    ).fetchone()
    if secrets.randbelow(100) == 0:
        db.execute("DELETE FROM attempt_limits WHERE window_start < %s", (tick - 86400,))
    return row["count"] <= limit


def public_staff(row):
    return {key: row[key] for key in ("id", "org_id", "login", "name", "role", "site_id", "scope_code", "employee_id")}


def new_session(db, user, response, request):
    token = secrets.token_urlsafe(32)
    lifetime = timedelta(hours=12)
    db.execute("DELETE FROM sessions WHERE staff_id = %s AND expires_at <= clock_timestamp()", (user["id"],))
    old_token = request.cookies.get(COOKIE)
    if old_token:
        db.execute("DELETE FROM sessions WHERE token_hash = %s", (digest(old_token),))
    db.execute("INSERT INTO sessions VALUES (%s, %s, %s)", (digest(token), user["id"], now() + lifetime))
    origin = urlparse(valid_host_origin(request))
    secure = origin.scheme == "https" or origin.hostname not in LOCAL_HOSTS
    response.set_cookie(COOKIE, token, max_age=int(lifetime.total_seconds()), httponly=True,
                        samesite="strict", secure=secure, path="/")
    return public_staff(user)


def staff(request: Request):
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Sign in to continue")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_same_origin(request, required=True)
    with transaction() as db:
        user = db.execute(
            """SELECT u.* FROM staff u JOIN sessions s ON s.staff_id = u.id
            WHERE s.token_hash = %s AND s.expires_at > clock_timestamp() AND u.active""",
            (digest(token),),
        ).fetchone()
    if not user:
        raise HTTPException(401, "Your session has expired")
    return user


def require_role(user, *roles):
    if user["role"] not in roles:
        raise HTTPException(403, "Your role cannot perform this action")


def authorize_site(user, site_id):
    if user["site_id"] and user["site_id"] != site_id:
        raise HTTPException(404, "Site not found")


def validate_code(value):
    return re.fullmatch(CODE_PATTERN, value) is not None
