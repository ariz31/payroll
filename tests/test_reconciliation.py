from datetime import timedelta

import psycopg

from siteguard.db import transaction
from siteguard.registry import badge_code
from test_attendance import API, IN, AttendanceFixture, Terminal


class ReconciliationTest(AttendanceFixture):
    def test_reconcile_quarantine_without_mutating_evidence(self):
        self.site("EAST")
        keeper = self.account("keeper", "timekeeper", site_id="GATE")
        other = self.account("other", "timekeeper", site_id="EAST")
        auditor = self.account("audit", "auditor")
        code = badge_code(self.worker(), "STATIC")
        terminal = Terminal(self)
        first = terminal.tap(code, IN, direction="in")
        event = terminal.tap(code, IN + timedelta(minutes=10), direction="in")
        self.assertEqual(event["result"], "QUARANTINED")
        listing = API + "/audit/scans?unresolved=true"
        self.assertEqual([row["id"] for row in keeper.get(listing).json()], [event["id"]])
        self.assertEqual(other.get(listing).json(), [])
        payload = {"disposition": "linked_for_review", "shift_id": first["shift_id"],
                   "notes": "Field supervisor confirmed a duplicate arrival"}
        url = f"{API}/audit/scans/{event['id']}/reconcile"
        self.assertEqual(auditor.post(url, json=payload).status_code, 403)
        self.assertEqual(other.post(url, json=payload).status_code, 404)
        first_save = keeper.post(url, json=payload)
        self.assertEqual(first_save.status_code, 200, first_save.text)
        self.assertEqual(keeper.post(url, json=payload).json(), first_save.json())
        self.assertEqual(keeper.post(url, json={**payload, "notes": "Different explanation"}).status_code, 409)
        self.assertEqual(keeper.get(listing).json(), [])
        shift = keeper.get(f"{API}/shifts/{first['shift_id']}").json()
        self.assertEqual(shift["reconciled_scans"][0]["event_id"], event["id"])
        self.assertIsNone(shift["raw_out"])
        self.assertEqual(shift["version"], 1)
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), transaction(self.runtime) as db:
            db.execute("DELETE FROM scan_reconciliations")
