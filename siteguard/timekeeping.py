from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import Field, model_validator

from .accounts import Input

CENT = Decimal("0.01")
ZERO = Decimal(0)
DAY = "Day Shift"
NIGHT = "Night Shift"
PENDING = "Pending Review"
VERIFIED = "Verified"
DISPUTED = "Disputed / Rejected"


class Policy(Input):
    day_start: time = time(8)
    day_end: time = time(17)
    night_start: time = time(22)
    night_end: time = time(7)
    break_mins: int = Field(default=60, ge=0, le=480)
    regular_hours: Decimal = Field(default=Decimal("8"), gt=0, le=24, decimal_places=2)
    late_grace_minutes: int = Field(default=5, ge=0, le=120)
    debounce_seconds: int = Field(default=300, ge=1, le=1800)
    high_ot_hours: Decimal = Field(default=Decimal("2"), ge=0, le=24, decimal_places=2)
    missing_out_grace_minutes: int = Field(default=60, ge=0, le=360)
    qr_mode: Literal["dynamic", "static", "both"] = "dynamic"
    qr_step_seconds: int = Field(default=30, ge=15, le=120)
    qr_drift_windows: int = Field(default=1, ge=0, le=2)
    offline_hours: int = Field(default=24, ge=1, le=48)
    auto_verify_ok_scans: bool = False

    @model_validator(mode="after")
    def valid_schedules(self):
        times = (self.day_start, self.day_end, self.night_start, self.night_end)
        if any(t.tzinfo is not None or t.second or t.microsecond for t in times):
            raise ValueError("Schedules require local HH:MM values")
        if not self.day_start < self.day_end or not self.night_start > self.night_end:
            raise ValueError("Day shifts must end the same day and night shifts the next day")
        return self


def policy(db, org_id, version=None):
    row = db.execute(
        """SELECT version,settings FROM policy_versions
        WHERE org_id=%s AND (%s::integer IS NULL OR version=%s) ORDER BY version DESC LIMIT 1""",
        (org_id, version, version),
    ).fetchone()
    return (row["version"], Policy.model_validate(row["settings"])) if row else (0, Policy())


def hours(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def duration_hours(delta):
    return (Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / 1_000_000) / 3600


def scheduled(work_date, timezone, shift_type, rules):
    zone = ZoneInfo(timezone)
    if shift_type == DAY:
        start, end_day, end = rules.day_start, work_date, rules.day_end
    else:
        start, end_day, end = rules.night_start, work_date + timedelta(days=1), rules.night_end
    start_at = datetime.combine(work_date, start, zone).astimezone(UTC)
    end_at = datetime.combine(end_day, end, zone).astimezone(UTC)
    return start_at, end_at


def assign_day(instant, timezone, shift_type, rules, direction):
    local_date = instant.astimezone(ZoneInfo(timezone)).date()
    candidates = [local_date + timedelta(days=offset) for offset in (-1, 0, 1)]
    slots = [(day, *scheduled(day, timezone, shift_type, rules)) for day in candidates]
    if direction == "in":
        nearest = min(slots, key=lambda item: abs(instant - item[1]))
        return nearest[0], "in"
    if direction == "out":
        nearest = min(slots, key=lambda item: abs(instant - item[2]))
        return nearest[0], "out"
    day, start, end = min(slots, key=lambda item: min(abs(instant - item[1]), abs(instant - item[2])))
    return day, "in" if abs(instant - start) <= abs(instant - end) else "out"


def calculate(row, rules, current):
    arrival = row["adjusted_in"] or row["raw_in"]
    departure = row["adjusted_out"] or row["raw_out"]
    start, end = scheduled(row["work_date"], row["timezone"], row["shift_type"], rules)
    net = max(ZERO, duration_hours(departure - arrival) - Decimal(rules.break_mins) / 60) if arrival and departure else ZERO
    regular = min(rules.regular_hours, net)
    overtime = max(ZERO, net - rules.regular_hours)
    night = regular if row["shift_type"] == NIGHT else ZERO
    closed = current >= end + timedelta(minutes=rules.missing_out_grace_minutes)
    alerts = []
    if arrival and not departure and closed:
        alerts.append("MISSING QR OUT")
    if departure and not arrival:
        alerts.append("MISSING QR IN")
    if row["shift_type"] == DAY and arrival and arrival > start + timedelta(minutes=rules.late_grace_minutes):
        alerts.append("LATE (>5m)")
    if overtime > rules.high_ot_hours:
        alerts.append("HIGH OT (>2h)")
    return {
        "effective_in": arrival, "effective_out": departure, "net_hours": hours(net),
        "regular_hours": hours(regular), "ot_hours": hours(overtime), "night_hours": hours(night),
        "anomaly": alerts[0] if alerts else "OK", "alerts": alerts,
        "open_shift": bool(arrival and not departure and not closed), "break_mins": rules.break_mins,
        "status": {"verified": VERIFIED, "disputed": DISPUTED}.get(row["stage"], PENDING),
    }
