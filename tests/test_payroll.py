import csv
import hashlib
import io
from datetime import timedelta
from uuid import uuid4

import openpyxl
import psycopg

from siteguard.db import transaction
from siteguard.payroll import HEADERS
from siteguard.registry import badge_code
from siteguard.timekeeping import Policy
from test_attendance import API, IN, AttendanceFixture, Terminal


class PayrollTest(AttendanceFixture):
    def setUp(self):
        super().setUp()
        self.foreman = self.account("field", "foreman", site_id="GATE", scope_code="A")
        self.engineer = self.account("project", "engineer", site_id="GATE", scope_code="PRJ")
        self.keeper = self.account("keeper", "timekeeper")
        self.auditor = self.account("audit", "auditor")
        self.terminal = Terminal(self)

    def review(self, client, shift_id, action, **details):
        row = client.get(f"{API}/shifts/{shift_id}").json()
        return client.post(f"{API}/shifts/{shift_id}/review", json={
            "request_id": str(uuid4()), "version": row.get("version", 1), "notes": "Synthetic fixture evidence",
            "action": action, **details,
        })

    def chain(self, shift_id):
        for client, action in ((self.foreman, "endorse"), (self.engineer, "cost_approve")):
            response = self.review(client, shift_id, action)
            self.assertEqual(response.status_code, 200, response.text)

    def tap_fixture(self, ident, arrival, departure=None, shift="Day Shift", **fields):
        token = badge_code(self.worker(ident, shift=shift, **fields), "STATIC")
        shift_id = self.terminal.tap(token, arrival, direction="in")["shift_id"]
        if departure:
            self.assertEqual(self.terminal.tap(token, departure, direction="out")["result"], "ACCEPTED_OUT")
        return shift_id

    def preview(self, client=None, **params):
        response = (client or self.keeper).get(API + "/payroll/periods/2026-11/preflight", params=params)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def export(self, preview, file_format, **fields):
        return self.keeper.post(API + "/payroll/exports", json={
            "period": "2026-11", "format": file_format, "expected_pending_count": preview["pending"],
            "snapshot_key": preview["snapshot_key"], **fields,
        })

    def test_blueprint_rows_hold_totals_formats_and_immutable_revisions(self):
        ok = self.tap_fixture("001", IN - timedelta(minutes=4), IN + timedelta(hours=9, minutes=4),
                              name="Élena, Reyes")
        night = self.tap_fixture("002", IN + timedelta(hours=13, minutes=58), IN + timedelta(hours=23, minutes=3),
                                 shift="Night Shift")
        missing = self.tap_fixture("003", IN + timedelta(minutes=1))
        high_ot = self.tap_fixture("004", IN, IN + timedelta(hours=12, minutes=30))
        self.tap_fixture("005", IN + timedelta(minutes=19), IN + timedelta(hours=9, minutes=15),
                         name="=1+1")
        self.tap_fixture("006", IN + timedelta(hours=14), shift="Night Shift")
        items = [{"id": ident, "version": self.keeper.get(f"{API}/shifts/{ident}").json()["version"]}
                 for ident in (ok, night)]
        response = self.keeper.post(API + "/shifts/bulk-verify", json={"request_id": str(uuid4()), "items": items})
        self.assertEqual(response.status_code, 200, response.text)
        self.chain(missing)
        response = self.review(self.keeper, missing, "verify", adjusted_out=(IN + timedelta(hours=9)).isoformat())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIsNone(response.json()["raw_out"])
        self.chain(high_ot)
        self.assertEqual(self.review(self.keeper, high_ot, "reject").status_code, 200)
        view = self.preview()
        self.assertEqual(view["verified_hours"], {"regular_hours": "23.98", "ot_hours": "0.21", "night_hours": "8.00"})
        self.assertEqual(view["pending"], 2)
        self.assertEqual(view["audit_hold_employee_ids"], ["005", "006"])
        self.assertEqual(view["disputed"], 1)
        downloads = []
        for file_format in ("csv", "xlsx"):
            generated = self.export(view, file_format)
            self.assertEqual(generated.status_code, 201, generated.text)
            meta = generated.json()
            saved = self.auditor.get(f"{API}/payroll/exports/{meta['id']}", params={"download": True})
            self.assertEqual(saved.headers["x-artifact-sha256"], hashlib.sha256(saved.content).hexdigest())
            downloads.append((meta, saved.content))
        csv_rows = list(csv.reader(io.StringIO(downloads[0][1].decode())))
        self.assertEqual(tuple(csv_rows[0]), HEADERS)
        self.assertEqual([len(row) for row in csv_rows], [23] * 7)
        self.assertEqual(csv_rows[1][3:5], ["001", "Élena, Reyes"])
        self.assertEqual(csv_rows[3][9:14], ["", "60", "", "17:00", "08:01"])
        self.assertEqual(csv_rows[5][4], "'=1+1")
        book = openpyxl.load_workbook(io.BytesIO(downloads[1][1]), read_only=True)
        self.assertEqual(book.sheetnames, ["06_QR_Timekeeper_Log"])
        sheet = book.active
        self.assertEqual(tuple(c.value for c in sheet[1]), HEADERS)
        self.assertEqual(sheet["D2"].value, "001")
        self.assertEqual((sheet["E6"].data_type, sheet["E6"].value), ("s", "=1+1"))
        self.assertEqual(sheet["Q4"].value, 7.98)
        self.assertEqual(self.review(self.keeper, ok, "reopen").status_code, 200)
        self.assertEqual(self.export(view, "csv").status_code, 409)
        again = self.auditor.get(f"{API}/payroll/exports/{downloads[0][0]['id']}", params={"download": True})
        self.assertEqual(again.content, downloads[0][1])
        record = self.keeper.get(f"{API}/payroll/periods/2026-11/dtr/002").json()
        self.assertEqual(record["days"][11]["overnight"]["out"], "2026-11-13T07:03:00+08:00")

    def test_reviewer_scope_version_idempotency_and_database_guard(self):
        ident = self.tap_fixture("X1", IN, IN + timedelta(hours=9))
        wrong_area = self.account("other", "foreman", site_id="GATE", scope_code="B")
        self.assertEqual(wrong_area.get(f"{API}/shifts/{ident}").status_code, 404)
        self.assertEqual(self.review(self.keeper, ident, "verify").status_code, 409)
        self.assertEqual(self.review(self.foreman, ident, "verify").status_code, 403)
        self.assertEqual(self.review(self.foreman, ident, "endorse", notes="  ").status_code, 422)
        version = self.foreman.get(f"{API}/shifts/{ident}").json()["version"]
        payload = {"version": version, "request_id": str(uuid4()), "action": "endorse", "notes": "Field confirmed"}
        url = f"{API}/shifts/{ident}/review"
        first = self.foreman.post(url, json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.foreman.post(url, json=payload).json(), first.json())
        self.assertEqual(self.foreman.post(url, json={**payload, "notes": "Other"}).status_code, 409)
        self.assertEqual(self.foreman.post(url, json={**payload, "request_id": str(uuid4())}).status_code, 409)
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), transaction(self.runtime) as db:
            db.execute("UPDATE shifts SET stage='verified' WHERE id=%s", (ident,))
        with self.assertRaises(psycopg.errors.CheckViolation), transaction(self.runtime) as db:
            keeper_id = self.keeper.get(API + "/auth/me").json()["id"]
            db.execute("SELECT review_shift(%s,%s,%s,%s,'verify','Invalid jump',NULL,NULL,'x')",
                       (ident, keeper_id, uuid4(), version + 1))

    def test_cross_site_hold_and_active_policy_re_evaluation(self):
        self.site("EAST")
        ident = self.tap_fixture("X1", IN, IN + timedelta(hours=9), site_ids=["GATE", "EAST"])
        version = self.keeper.get(f"{API}/shifts/{ident}").json()["version"]
        self.assertEqual(self.keeper.post(API + "/shifts/bulk-verify", json={
            "request_id": str(uuid4()), "items": [{"id": ident, "version": version}],
        }).status_code, 200)
        alt = Terminal(self, "EAST1", "EAST")
        with transaction(self.owner) as db:
            badge = db.execute("SELECT * FROM badges WHERE org_id=%s AND employee_id='X1'",
                               (self.org_id,)).fetchone()
        pending = alt.tap(badge_code(badge, "STATIC"), IN + timedelta(days=1) - timedelta(hours=1),
                          direction="in")["shift_id"]
        local = self.account("local", "timekeeper", site_id="GATE")
        view = self.preview(local)
        self.assertEqual(view["pending"], 0)
        self.assertEqual(view["audit_hold_employee_ids"], ["X1"])
        self.assertEqual(view["verified_hours"]["regular_hours"], "8.00")
        self.assertEqual(view["releasable_hours"]["regular_hours"], "0.00")
        changed = Policy(qr_mode="both", break_mins=30, late_grace_minutes=10)
        response = self.client.put(API + "/config", json=changed.model_dump(mode="json"))
        self.assertEqual(response.status_code, 200, response.text)
        final = self.keeper.get(f"{API}/shifts/{ident}").json()
        active = self.keeper.get(f"{API}/shifts/{pending}").json()
        self.assertEqual(final["break_mins"], 60)
        self.assertEqual(active["break_mins"], 30)
        self.assertEqual(active["history"][-1]["action"], "policy_changed")

    def test_explicit_auto_verification(self):
        response = self.client.put(API + "/config", json=Policy(qr_mode="both", auto_verify_ok_scans=True).model_dump(mode="json"))
        self.assertEqual(response.status_code, 200, response.text)
        ident = self.tap_fixture("AUTO", IN, IN + timedelta(hours=9))
        row = self.keeper.get(f"{API}/shifts/{ident}").json()
        self.assertEqual(row["status"], "Verified")
        self.assertEqual(row["verified_by"], "system")
        self.assertEqual(row["history"][-1]["action"], "auto_verify")
