import calendar
import csv
import hashlib
import hmac
import io
import json
import re
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import xlsxwriter
from fastapi import APIRouter, HTTPException, Query, Response
from psycopg.types.json import Jsonb
from pydantic import Field

from .accounts import Code, Input, Staff
from .db import control, lock_org, now, transaction
from .reviews import Period, bounds, period_shifts, project, scoped
from .security import authorize_site, derived_key, require_role, secret
from .timekeeping import DISPUTED, PENDING, VERIFIED, ZERO

router = APIRouter()
SHEET = "06_QR_Timekeeper_Log"
HEADERS = (
    "Scan_ID", "Pay_Period", "Work_Date", "Emp_ID", "Full_Name", "Department", "QR_Terminal_ID", "Shift_Type",
    "Raw_QR_Time_In", "Raw_QR_Time_Out", "Break_Mins", "TK_Adjusted_In", "TK_Adjusted_Out", "Effective_In",
    "Effective_Out", "Net_Worked_Hrs", "Calc_Reg_Hrs", "Calc_OT_Hrs", "Calc_Night_Hrs", "QR_Anomaly_Alert",
    "Timekeeper_Status", "Verified_By_TK", "TK_Verification_Notes",
)
HOUR_FIELDS = ("regular_hours", "ot_hours", "night_hours")
EXPORT_META = "id,site_id,period,revision,format,actor_name,created_at,digest,signed_receipt,snapshot"


class ExportRequest(Input):
    period: str = Field(pattern=r"^20[0-9]{2}-(0[1-9]|1[0-2])$")
    format: Literal["csv", "xlsx"]
    site: Code | None = None
    expected_pending_count: int = Field(ge=0)
    snapshot_key: str = Field(pattern=r"^[a-f0-9]{64}$")


def money(value):
    return f"{value:.2f}"


def totals(rows):
    return {key: money(sum((r[key] for r in rows), ZERO)) for key in HOUR_FIELDS}


def count_summary(rows, holds):
    verified = [r for r in rows if r["status"] == VERIFIED]
    return {
        "verified": len(verified), "pending": sum(r["status"] == PENDING for r in rows),
        "disputed": sum(r["status"] == DISPUTED for r in rows),
        "missing_out": sum(r["anomaly"] == "MISSING QR OUT" for r in rows),
        "row_count": len(rows), "audit_hold_employee_ids": sorted(holds),
        "verified_hours": totals(verified),
        "releasable_hours": totals([r for r in verified if r["employee_id"] not in holds]),
        "policy_versions": sorted({r["policy_version"] for r in rows}),
    }


def global_holds(db, org, period, employees):
    start, end = bounds(period)
    rows = db.execute(
        """SELECT DISTINCT employee_id FROM shifts WHERE org_id=%s AND work_date>=%s AND work_date<%s
        AND stage NOT IN ('verified','disputed') AND employee_id=ANY(%s)""",
        (org, start, end, employees),
    ).fetchall()
    return {row["employee_id"] for row in rows}


def snapshot(db, user, period, site):
    if site:
        authorize_site(user, site)
    rows = project(db, period_shifts(db, user, period, site), now())
    holds = global_holds(db, user["org_id"], period, sorted({r["employee_id"] for r in rows}))
    summary = count_summary(rows, holds)
    content = [(str(row["id"]), row["version"], row["anomaly"]) for row in rows]
    summary["snapshot_key"] = hashlib.sha256(json.dumps([period, site, content, sorted(holds)]).encode()).hexdigest()
    return rows, summary


def local_time(value, zone):
    return value.astimezone(zone).strftime("%H:%M") if value else ""


def export_row(row, period):
    zone = ZoneInfo(row["timezone"])
    return [
        "QR-" + row["id"].hex.upper(), period, row["work_date"].isoformat(), row["employee_id"],
        row["name"], row["department"], row["terminal_code"], row["shift_type"],
        local_time(row["raw_in"], zone), local_time(row["raw_out"], zone), row["break_mins"],
        local_time(row["adjusted_in"], zone), local_time(row["adjusted_out"], zone),
        local_time(row["effective_in"], zone), local_time(row["effective_out"], zone),
        *(row[key] for key in ("net_hours", *HOUR_FIELDS)),
        row["anomaly"], row["status"], row["verified_by"] or "", row["notes"] or "",
    ]


def csv_value(value):
    if isinstance(value, Decimal):
        return money(value)
    if isinstance(value, str):
        if (value.lstrip().startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n", "'"))):
            return "'" + value
    return value


def produce(rows, period, file_format):
    if file_format == "csv":
        out = io.StringIO(newline="")
        writer = csv.writer(out, lineterminator="\r\n")
        writer.writerow(HEADERS)
        writer.writerows([csv_value(value) for value in export_row(row, period)] for row in rows)
        return out.getvalue().encode("utf-8")

    out = io.BytesIO()
    with xlsxwriter.Workbook(out, {"in_memory": True, "strings_to_formulas": False, "strings_to_urls": False}) as book:
        sheet = book.add_worksheet(SHEET)
        header = book.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#12273B"})
        numeric = book.add_format({"num_format": "0.00"})
        sheet.write_row(0, 0, HEADERS, header)
        sheet.set_column(0, 0, 37)
        sheet.set_column(1, 22, 21)
        sheet.set_column(4, 5, 29)
        sheet.set_column(22, 22, 50)
        sheet.freeze_panes(1, 4)
        sheet.autofilter(0, 0, len(rows), len(HEADERS) - 1)
        for index, row in enumerate(rows, 1):
            for col, value in enumerate(export_row(row, period)):
                if isinstance(value, Decimal):
                    sheet.write_number(index, col, float(value), numeric)
                elif isinstance(value, int):
                    sheet.write_number(index, col, value)
                elif value:
                    sheet.write_string(index, col, value)
    return out.getvalue()


@router.get("/dashboard")
def dashboard(user: Staff, period: str = Period, site: Code | None = None):
    require_role(user, "admin", "foreman", "engineer", "timekeeper", "auditor", "employee")
    with transaction() as db:
        _, summary = snapshot(db, user, period, site)
        start, end = bounds(period)
        where, params = scoped(user)
        only_shifts = user["role"] in {"foreman", "engineer", "employee"}
        join = "JOIN shifts s ON s.id=a.shift_id" if only_shifts else ""
        if not only_shifts:
            where, params = scoped(user, "a")
        audit = db.execute(
            f"""SELECT count(*) AS scanned, count(*) FILTER(WHERE result='QUARANTINED') AS quarantined,
            count(*) FILTER(WHERE result='REJECTED') AS rejected
            FROM scan_audit a {join} WHERE {where} AND (%s::text IS NULL OR a.site_id=%s)
            AND COALESCE(a.work_date,(a.received_at AT TIME ZONE (
                SELECT timezone FROM sites WHERE org_id=a.org_id AND id=a.site_id))::date)>= %s
            AND COALESCE(a.work_date,(a.received_at AT TIME ZONE (
                SELECT timezone FROM sites WHERE org_id=a.org_id AND id=a.site_id))::date)< %s""",
            (*params, site, site, start, end),
        ).fetchone()
        return {**summary, **audit, "scan_scope": "linked" if only_shifts else "all attempts"}


@router.get("/payroll/periods/{period}/preflight")
def preflight(user: Staff, period: str, site: Code | None = None):
    require_role(user, "timekeeper", "auditor")
    validate_period(period)
    with transaction() as db:
        # The projections and hold query share one snapshot under concurrent ingestion.
        db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        return snapshot(db, user, period, site)[1]


def validate_period(period):
    if not re.fullmatch(r"20[0-9]{2}-(0[1-9]|1[0-2])", period):
        raise HTTPException(422, "Period must use YYYY-MM")


@router.post("/payroll/exports", status_code=201)
def make_export(body: ExportRequest, user: Staff):
    require_role(user, "timekeeper")
    org = user["org_id"]
    secret()
    with transaction() as db:
        lock_org(db, org)
        rows, summary = snapshot(db, user, body.period, body.site)
        if summary["snapshot_key"] != body.snapshot_key or summary["pending"] != body.expected_pending_count:
            raise HTTPException(409, "The payroll period changed. Refresh the preview before exporting.")
        if len(rows) > 8000:
            raise HTTPException(413, "Select a smaller site scope for this export")
        artifact = produce(rows, body.period, body.format)
        if len(artifact) > 3_600_000:
            raise HTTPException(413, "This file exceeds the download limit. Select a smaller site scope.")
        checksum = hashlib.sha256(artifact).hexdigest()
        rev = db.execute(
            "SELECT COALESCE(max(revision),0)+1 AS next FROM payroll_exports WHERE org_id=%s AND period=%s",
            (org, body.period),
        ).fetchone()["next"]
        ident = uuid4()
        created = now()
        site = body.site or user["site_id"]
        proof = [str(ident), str(org), site, body.period, rev, body.format, user["login"], created.isoformat(),
                 checksum, summary]
        signature = hmac.digest(derived_key("payroll-receipt"),
                                json.dumps(proof, sort_keys=True, separators=(",", ":")).encode(), "sha256").hex()
        row = db.execute(
            f"""INSERT INTO payroll_exports (id,org_id,site_id,period,revision,format,actor_id,actor_name,created_at,
            digest,signed_receipt,snapshot,artifact) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING {EXPORT_META}""",
            (ident, org, site, body.period, rev, body.format, user["id"], user["login"], created, checksum,
             signature, Jsonb(summary), artifact),
        ).fetchone()
        control(db, org, user["id"], "export.created", ident, {"period": body.period, "revision": rev})
        return row


@router.get("/payroll/exports")
def list_exports(user: Staff, period: str = Period, offset: int = Query(default=0, ge=0)):
    require_role(user, "timekeeper", "auditor")
    with transaction() as db:
        return db.execute(
            f"""SELECT {EXPORT_META} FROM payroll_exports WHERE org_id=%s AND period=%s
            AND (%s::text IS NULL OR site_id=%s) ORDER BY revision DESC LIMIT 100 OFFSET %s""",
            (user["org_id"], period, user["site_id"], user["site_id"], offset),
        ).fetchall()


@router.get("/payroll/exports/{ident}")
def export_record(ident: UUID, user: Staff, download: bool = False):
    require_role(user, "timekeeper", "auditor")
    with transaction() as db:
        columns = EXPORT_META + (",artifact" if download else "")
        row = db.execute(f"""SELECT {columns} FROM payroll_exports WHERE id=%s AND org_id=%s
                         AND (%s::text IS NULL OR site_id=%s)""",
                         (ident, user["org_id"], user["site_id"], user["site_id"])).fetchone()
        if not row:
            raise HTTPException(404, "Export revision not found")
        if not download:
            return row
        control(db, user["org_id"], user["id"], "export.downloaded", ident)
        mime = ("text/csv; charset=utf-8" if row["format"] == "csv" else
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        filename = f"{SHEET}_{row['period']}_r{row['revision']}.{row['format']}"
        return Response(row["artifact"], media_type=mime, headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Artifact-SHA256": row["digest"],
        })


@router.get("/payroll/periods/{period}/dtr/{employee}")
def daily_time_record(period: str, employee: Code, user: Staff):
    require_role(user, "timekeeper", "auditor", "employee")
    validate_period(period)
    with transaction() as db:
        rows = project(db, period_shifts(db, user, period, employee=employee), now())
        if not rows:
            raise HTTPException(404, "No attendance records for this period")
        holds = global_holds(db, user["org_id"], period, [employee])
        year, month = map(int, period.split("-"))
        days = [{"day": day} for day in range(1, calendar.monthrange(year, month)[1] + 1)]
        for row in rows:
            if row["status"] != VERIFIED:
                days[row["work_date"].day - 1]["note"] = row["status"]
                continue
            zone = ZoneInfo(row["timezone"])
            day = days[row["work_date"].day - 1]
            for label, stamp in (("in", row["effective_in"]), ("out", row["effective_out"])):
                if stamp:
                    local = stamp.astimezone(zone)
                    if local.date() == row["work_date"] and row["shift_type"] == "Day Shift":
                        day[("am_" if local.hour < 12 else "pm_") + label] = local.strftime("%H:%M")
                    else:
                        day.setdefault("overnight", {})[label] = local.isoformat()
        control(db, user["org_id"], user["id"], "dtr.viewed", employee, {"period": period})
        return {"employee_id": employee, "name": rows[-1]["name"], "period": period, "days": days,
                "audit_hold": bool(holds), "department": rows[-1]["department"]}
