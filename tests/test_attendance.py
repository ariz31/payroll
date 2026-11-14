import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import psycopg

from siteguard.db import transaction
from siteguard.registry import badge_code
from siteguard.scans import Scan, lease_token, mac
from siteguard.timekeeping import Policy, assign_day, calculate
from support import DatabaseTest
from unittest import TestCase

API = "/api/v1"
IN = datetime(2026, 11, 12, 0, 0, tzinfo=UTC)


class Terminal:
    def __init__(self, fixture, code="TERM1", site="GATE", rules=None):
        self.fixture = fixture
        self.rules = rules or Policy()
        response = fixture.client.put(f"{API}/terminals/{code}", json={
            "name": code, "site_id": site, "latitude": 14.6, "longitude": 121,
        })
        fixture.assertEqual(response.status_code, 200, response.text)
        self.row = response.json()
        self.auth = {"Authorization": "Device " + self.row["credential"]}
        self.sequence = 0
        self.previous = ""
        self.anchor = IN - timedelta(hours=3)
        with transaction(fixture.owner) as db:
            device = db.execute("SELECT * FROM terminals WHERE id=%s", (self.row["id"],)).fetchone()
        self.lease = lease_token(device, int(self.anchor.timestamp() * 1000), self.anchor, self.rules)[0]

    def record(self, token, stamp, direction="auto", **changes):
        self.sequence += 1
        blob = {
            "client_event_id": str(uuid4()), "generation": 1, "sequence": self.sequence,
            "captured_ms": int(stamp.timestamp() * 1000), "latitude_e6": 14_600_000,
            "longitude_e6": 121_000_000, "accuracy_mm": 6000, "direction": direction,
            "qr_payload": token, "jpeg": "", "lease": self.lease, "previous_hash": self.previous,
            "event_hash": "0" * 64, "device_mac": "0" * 64, **changes,
        }
        blob["event_hash"] = hashlib.sha256(Scan.model_validate(blob).canonical()).hexdigest()
        blob["device_mac"] = mac(self.row["credential"].encode(), blob["event_hash"])
        self.previous = blob["event_hash"]
        return blob

    def send(self, blob, received=None):
        received = received or datetime.fromtimestamp(blob["captured_ms"] / 1000, UTC)
        with patch("siteguard.scans.now", return_value=received):
            return self.fixture.client.post(API + "/scans", json=blob, headers=self.auth)

    def tap(self, token, stamp, direction="auto", **changes):
        response = self.send(self.record(token, stamp, direction, **changes))
        self.fixture.assertEqual(response.status_code, 200, response.text)
        return response.json()


class AttendanceTest(DatabaseTest):
    def setUp(self):
        super().setUp()
        self.site()
        self.rules = Policy(qr_mode="both")
        r = self.client.put(API + "/config", json=self.rules.model_dump(mode="json"))
        self.assertEqual(r.status_code, 200, r.text)

    def worker(self, ident="EMP1", shift="Day Shift", mode="STC", **fields):
        payload = {"name": ident, "department": "Civil", "cost_code": "PRJ", "crew": "A",
                   "shift_type": shift, "site_ids": ["GATE"], **fields}
        response = self.client.put(f"{API}/employees/{ident}", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        response = self.client.post(API + "/badges/issue", json={"employee_id": ident, "mode": mode})
        self.assertEqual(response.status_code, 201, response.text)
        badge = response.json()
        with transaction(self.owner) as db:
            db.execute("UPDATE badges SET created_at=%s WHERE id=%s", (IN - timedelta(days=4), badge["id"]))
        return badge

    def test_durable_receipt_duplicate_geofence_and_raw_integrity(self):
        badge = self.worker()
        t = Terminal(self)
        code = badge_code(badge, "STATIC")
        first_blob = t.record(code, IN)
        first = t.send(first_blob).json()
        self.assertEqual(first["result"], "ACCEPTED_IN")
        self.assertEqual(t.send(first_blob).json(), first)
        changed = {**first_blob, "direction": "out"}
        self.assertEqual(t.send(changed).status_code, 409)
        self.assertEqual(t.tap(code, IN + timedelta(seconds=300))["result"], "IGNORED_DEBOUNCE")
        self.assertEqual(t.tap(code, IN + timedelta(hours=8), latitude_e6=17_000_000)["result"], "REJECTED")
        self.assertEqual(t.tap(code, IN + timedelta(hours=9))["result"], "ACCEPTED_OUT")
        with self.assertRaises(psycopg.errors.CheckViolation), transaction(self.runtime) as db:
            db.execute("UPDATE shifts SET raw_out=raw_out+interval '1 min' WHERE id=%s", (first["shift_id"],))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), transaction(self.runtime) as db:
            db.execute("TRUNCATE scan_audit")
        with transaction(self.owner) as db:
            self.assertEqual(db.execute("SELECT count(*) AS n FROM scan_audit WHERE org_id=%s", (self.org_id,)).fetchone()["n"], 4)

    def test_dynamic_window_revocation_and_site_assignment(self):
        badge = self.worker(mode="DYN")
        t = Terminal(self)
        marker = int(IN.timestamp()) // 30
        self.assertEqual(t.tap(badge_code(badge, str(marker - 2)), IN)["result"], "REJECTED")
        self.assertEqual(t.tap(badge_code(badge, str(marker + 1)), IN)["result"], "ACCEPTED_IN")
        self.assertEqual(t.tap(badge_code(badge, str(marker + 1)), IN)["result"], "IGNORED_DEBOUNCE")
        self.site("EAST")
        outside = Terminal(self, "TERM2", "EAST")
        self.assertEqual(outside.tap(badge_code(badge, str(marker)), IN)["result"], "REJECTED")
        self.client.post(f"{API}/badges/{badge['id']}/revoke")
        self.assertEqual(t.tap(badge_code(badge, str(marker)), IN)["result"], "REJECTED")

    def test_offline_batch_preserves_order_and_failed_chain_is_audited(self):
        code = badge_code(self.worker(), "STATIC")
        t = Terminal(self)
        events = [t.record(code, IN), t.record(code, IN + timedelta(hours=9))]
        with patch("siteguard.scans.now", return_value=IN + timedelta(hours=12)):
            response = self.client.post(API + "/scans/offline-batches", json={"events": events}, headers=t.auth)
            replay = self.client.post(API + "/scans/offline-batches", json={"events": events}, headers=t.auth)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), replay.json())
        self.assertEqual([r["result"] for r in response.json()["receipts"]], ["ACCEPTED_IN", "ACCEPTED_OUT"])
        broken = t.record(code, IN + timedelta(hours=10), previous_hash="f" * 64)
        result = t.send(broken).json()
        self.assertEqual(result["result"], "QUARANTINED")
        self.assertFalse(result["chain_advanced"])

    def test_concurrent_terminals_produce_one_arrival(self):
        badge = self.worker()
        code = badge_code(badge, "STATIC")
        terminals = [Terminal(self, "ONE"), Terminal(self, "TWO")]
        items = [(terminal, terminal.record(code, IN)) for terminal in terminals]
        with patch("siteguard.scans.now", return_value=IN), ThreadPoolExecutor(2) as pool:
            results = list(pool.map(lambda item: self.client.post(API + "/scans", json=item[1],
                                                                 headers=item[0].auth).json()["result"], items))
        self.assertEqual(sorted(results), ["ACCEPTED_IN", "IGNORED_DEBOUNCE"])


class RuleTest(TestCase):
    def test_reference_arithmetic_and_alert_priority(self):
        cases = [
            ("Day Shift", IN - timedelta(minutes=4), IN + timedelta(hours=9, minutes=4), "OK", "8.00", "0.13", "0.00"),
            ("Night Shift", IN + timedelta(hours=13, minutes=58), IN + timedelta(hours=23, minutes=3), "OK", "8.00", "0.08", "8.00"),
            ("Day Shift", IN + timedelta(minutes=1), IN + timedelta(hours=9), "OK", "7.98", "0.00", "0.00"),
            ("Day Shift", IN, IN + timedelta(hours=12, minutes=30), "HIGH OT (>2h)", "8.00", "3.50", "0.00"),
            ("Day Shift", IN + timedelta(minutes=19), IN + timedelta(hours=9, minutes=15), "LATE (>5m)", "7.93", "0.00", "0.00"),
            ("Night Shift", IN + timedelta(hours=14), None, "MISSING QR OUT", "0.00", "0.00", "0.00"),
        ]
        for shift, arrival, out, alert, reg, ot, night in cases:
            result = calculate({"shift_type": shift, "raw_in": arrival, "raw_out": out,
                                "adjusted_in": None, "adjusted_out": None, "stage": "foreman",
                                "work_date": IN.date(), "timezone": "Asia/Manila"}, Policy(), IN + timedelta(days=2))
            self.assertEqual(result["anomaly"], alert)
            self.assertEqual([result[field] for field in ("regular_hours", "ot_hours", "night_hours")],
                             [Decimal(reg), Decimal(ot), Decimal(night)])
        day, _ = assign_day(IN + timedelta(hours=23, minutes=3), "Asia/Manila", "Night Shift", Policy(), "out")
        self.assertEqual(day, IN.date())
