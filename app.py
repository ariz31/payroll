import logging
import os
from pathlib import Path

import psycopg
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from siteguard.accounts import router as accounts
from siteguard.db import transaction
from siteguard.identity import router as identity
from siteguard.maintenance import router as maintenance
from siteguard.payroll import router as payroll
from siteguard.reviews import router as reviews
from siteguard.registry import router as registry
from siteguard.scans import router as scans
from siteguard.security import secret

logger = logging.getLogger("siteguard")
app = FastAPI(title="SiteGuard QR", version="1.0", docs_url="/api/docs",
              openapi_url="/api/openapi.json", redoc_url=None)
for router in (accounts, registry, scans, reviews, payroll, identity, maintenance):
    app.include_router(router, prefix="/api/v1")


@app.middleware("http")
async def protect_response(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH"}:
        length = request.headers.get("content-length")
        if length and length.isdecimal() and int(length) > 2_000_000:
            return JSONResponse({"detail": "Request is too large"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(_request, exc):
    errors = [{"loc": item["loc"], "msg": item["msg"], "type": item["type"]} for item in exc.errors()]
    return JSONResponse({"detail": errors}, status_code=422)


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    logger.error("database error method=%s code=%s", request.method, exc.sqlstate)
    unavailable = isinstance(exc, (psycopg.OperationalError, psycopg.errors.UndefinedTable))
    return JSONResponse({"detail": "Database unavailable" if unavailable else "Database operation failed"},
                        status_code=503 if unavailable else 500)


@app.get("/api/v1/health/live")
def liveness():
    return {"status": "ok"}


@app.get("/api/v1/health/ready")
def readiness():
    secret()
    with transaction() as db:
        version = db.execute("SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1").fetchone()
    if not version or version["version"] < "006_reconciliation.sql":
        raise HTTPException(503, "Database schema is not ready")
    return {"status": "ready"}


public = Path(__file__).parent / "public"
if public.is_dir() and not os.getenv("VERCEL"):
    app.mount("/", StaticFiles(directory=public, html=True), name="web")
