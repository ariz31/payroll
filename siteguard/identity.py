import base64
import hashlib
import hmac
import json
import os
import secrets
from urllib.parse import urlencode, urlsplit

import httpx
import jwt
from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import StringConstraints
from typing import Annotated

from .db import control, lock_org, transaction
from .security import CODE_PATTERN, derived_key, new_session, reserve_attempt

router = APIRouter()
FLOW_COOKIE = "siteguard_oidc"
FLOW_AGE = 600
CALLBACK = "/api/v1/auth/oidc/callback"


def configuration():
    issuer = os.getenv("OIDC_ISSUER", "").rstrip("/")
    client = os.getenv("OIDC_CLIENT_ID", "")
    password = os.getenv("OIDC_CLIENT_SECRET", "")
    origin = os.getenv("SITEGUARD_ORIGIN", "").rstrip("/")
    if not all((issuer, client, password, origin)):
        return None
    if urlsplit(issuer).scheme != "https" or urlsplit(origin).scheme != "https":
        return None
    return issuer, client, password, origin


@router.get("/auth/options")
def options():
    return {"oidc": configuration() is not None}


def discovery(client, issuer):
    response = client.get(issuer + "/.well-known/openid-configuration")
    response.raise_for_status()
    metadata = response.json()
    if metadata["issuer"] != issuer:
        raise ValueError("Issuer configuration mismatch")
    for name in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        parsed = urlsplit(metadata[name])
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Invalid identity provider endpoint")
    return metadata


def cipher():
    return Fernet(base64.urlsafe_b64encode(derived_key("oidc-flow")))


def base64url(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


@router.get("/auth/oidc/start")
def start(request: Request, organization: Annotated[str, StringConstraints(pattern=CODE_PATTERN)]):
    config = configuration()
    if not config:
        raise HTTPException(404, "Single sign-on is unavailable")
    issuer, client_id, _password, origin = config
    host = request.client.host if request.client else "unknown"
    with transaction() as db:
        allowed = reserve_attempt(db, f"oidc/{host}", 30, 600)
    if not allowed:
        raise HTTPException(429, "Too many sign-in attempts")
    try:
        with httpx.Client(timeout=5) as client:
            metadata = discovery(client, issuer)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "The identity provider is unavailable") from None
    flow = {"org": organization.lower(), "state": secrets.token_urlsafe(24), "nonce": secrets.token_urlsafe(24),
            "verifier": secrets.token_urlsafe(48)}
    args = {
        "response_type": "code", "client_id": client_id, "redirect_uri": origin + CALLBACK,
        "scope": "openid email", "state": flow["state"], "nonce": flow["nonce"],
        "code_challenge": base64url(hashlib.sha256(flow["verifier"].encode()).digest()), "code_challenge_method": "S256",
    }
    join = "&" if "?" in metadata["authorization_endpoint"] else "?"
    response = RedirectResponse(metadata["authorization_endpoint"] + join + urlencode(args), status_code=303)
    response.set_cookie(FLOW_COOKIE, cipher().encrypt(json.dumps(flow).encode()).decode(),
                        max_age=FLOW_AGE, secure=True, httponly=True, samesite="lax", path=CALLBACK)
    return response


def validate_id_token(client, metadata, token, issuer, client_id, nonce):
    header = jwt.get_unverified_header(token)
    if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
        raise ValueError("Unsupported identity signature")
    response = client.get(metadata["jwks_uri"])
    response.raise_for_status()
    keys = [key for key in response.json()["keys"] if key.get("kid") == header["kid"]
            and key.get("kty") == "RSA" and key.get("use", "sig") == "sig" and key.get("alg", "RS256") == "RS256"]
    if len(keys) != 1:
        raise ValueError("Identity signing key is unavailable")
    claims = jwt.decode(token, jwt.PyJWK.from_dict(keys[0]).key, algorithms=["RS256"], issuer=issuer,
                        audience=client_id, leeway=30, options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]})
    if not isinstance(claims["nonce"], str) or not hmac.compare_digest(nonce, claims["nonce"]):
        raise ValueError("Identity nonce mismatch")
    aud = claims["aud"]
    if (isinstance(aud, list) and len(aud) > 1 and claims.get("azp") != client_id) or (
         "azp" in claims and claims["azp"] != client_id):
        raise ValueError("Unauthorized identity audience")
    return claims


def linked_user(db, slug, issuer, claims):
    org = db.execute("SELECT id FROM organizations WHERE slug=%s", (slug,)).fetchone()
    if not org:
        return None
    lock_org(db, org["id"])
    match = db.execute(
        """SELECT u.* FROM oidc_links l JOIN staff u ON (u.org_id,u.id)=(l.org_id,l.staff_id)
        WHERE l.org_id=%s AND l.issuer=%s AND l.subject=%s AND u.active""",
        (org["id"], issuer, claims["sub"]),
    ).fetchone()
    if match:
        return match
    email = claims.get("email")
    if claims.get("email_verified") is not True or not isinstance(email, str) or len(email) > 120:
        return None
    user = db.execute("""
        SELECT u.* FROM staff u WHERE u.org_id=%s AND u.login=%s AND u.active
        AND u.password_hash IS NULL AND NOT EXISTS (
            SELECT 1 FROM oidc_links WHERE staff_id=u.id AND issuer=%s)
        """, (org["id"], email.lower(), issuer)).fetchone()
    if not user:
        return None
    created = db.execute("""
        INSERT INTO oidc_links (org_id,staff_id,issuer,subject) VALUES (%s,%s,%s,%s)
        ON CONFLICT DO NOTHING RETURNING staff_id
        """, (org["id"], user["id"], issuer, claims["sub"])).fetchone()
    if not created:
        return None
    control(db, org["id"], user["id"], "account.sso_linked", user["id"])
    return user


@router.get(CALLBACK.removeprefix("/api/v1"))
def finish(request: Request, code: str = "", state: str = ""):
    config = configuration()
    if not config:
        raise HTTPException(404, "Single sign-on is unavailable")
    issuer, client_id, password, origin = config
    response = RedirectResponse("/#overview", status_code=303)
    response.delete_cookie(FLOW_COOKIE, path=CALLBACK, secure=True, httponly=True, samesite="lax")
    try:
        if not code or not state or len(code) > 4096 or len(state) > 128:
            raise ValueError
        flow = json.loads(cipher().decrypt(request.cookies.get(FLOW_COOKIE, "").encode(), ttl=FLOW_AGE))
        if not hmac.compare_digest(flow["state"], state):
            raise ValueError
        with httpx.Client(timeout=5) as client:
            metadata = discovery(client, issuer)
            params = {"grant_type": "authorization_code", "code": code, "redirect_uri": origin + CALLBACK,
                      "code_verifier": flow["verifier"]}
            methods = metadata.get("token_endpoint_auth_methods_supported", ["client_secret_basic"])
            if "client_secret_basic" in methods:
                issued = client.post(metadata["token_endpoint"], data=params, auth=(client_id, password))
            elif "client_secret_post" in methods:
                issued = client.post(metadata["token_endpoint"], data={**params, "client_id": client_id,
                                                                       "client_secret": password})
            else:
                raise ValueError
            issued.raise_for_status()
            claims = validate_id_token(client, metadata, issued.json()["id_token"], issuer, client_id, flow["nonce"])
    except (InvalidToken, ValueError, jwt.PyJWTError, httpx.HTTPError, KeyError, TypeError):
        response.headers["location"] = "/#sso-failed"
        return response
    with transaction() as db:
        user = linked_user(db, flow["org"], issuer, claims)
        if not user:
            response.headers["location"] = "/#sso-failed"
        else:
            new_session(db, user, response, request)
    return response
