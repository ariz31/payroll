from datetime import timedelta
from uuid import uuid4

from siteguard.db import transaction
from siteguard.registry import badge_code
from test_attendance import API, IN, AttendanceFixture, Terminal


class IntegrationTest(AttendanceFixture):
    def test_read_only_scope_holds_revocation_and_pagination(self):
        self.site("EAST")
        keeper = self.account("keeper", "timekeeper")
        east = Terminal(self, "SIDE", "EAST")
        gate = Terminal(self, "GATE1")
        items = []
        for ident in ("E1", "E2", "E3"):
            badge = self.worker(ident, site_ids=["GATE", "EAST"])
            token = badge_code(badge, "STATIC")
            recorded = gate.tap(token, IN, direction="in")
            gate.tap(token, IN + timedelta(hours=9), direction="out")
            items.append({"id": recorded["shift_id"], "version": 2})
            if ident == "E3":
                east.lease = self.new_lease(east, IN + timedelta(hours=20))
                east.tap(token, IN + timedelta(days=1), direction="in")
        verified = keeper.post(API + "/shifts/bulk-verify", json={"items": items, "request_id": str(uuid4())})
        self.assertEqual(verified.status_code, 200, verified.text)

        namespace = API + "/integrations/payroll"
        self.assertEqual(keeper.post(namespace, json={"name": "ERP"}).status_code, 403)
        credential = self.client.post(namespace, json={"name": "ERP", "site_id": "GATE"})
        self.assertEqual(credential.status_code, 201, credential.text)
        meta = credential.json()
        authorized = {"Authorization": "Bearer " + meta["credential"]}
        url = namespace + "/periods/2026-11"
        self.assertEqual(self.client.get(url).status_code, 401)
        page = self.client.get(url, headers=authorized, params={"limit": 1})
        self.assertEqual(page.status_code, 200, page.text)
        data = page.json()
        self.assertEqual(data["held_employee_count"], 1)
        self.assertEqual(data["total_employees"], 2)
        self.assertEqual(data["items"], [{"employee_id": "E1", "regular_hours": "8.00",
                                         "ot_hours": "0.00", "night_hours": "0.00"}])
        self.assertEqual(self.client.get(url, headers=authorized, params={"offset": 1}).status_code, 422)
        next_page = self.client.get(url, headers=authorized, params={"offset": 1, "snapshot_key": data["snapshot_key"]})
        self.assertEqual(next_page.json()["items"][0]["employee_id"], "E2")
        change = keeper.post(f"{API}/shifts/{items[1]['id']}/review", json={
            "version": 3, "action": "reopen", "notes": "Fixture verification changed", "request_id": str(uuid4()),
        })
        self.assertEqual(change.status_code, 200, change.text)
        stale = self.client.get(url, headers=authorized, params={"offset": 1, "snapshot_key": data["snapshot_key"]})
        self.assertEqual(stale.status_code, 409)
        self.assertNotIn("credential", self.client.get(namespace).json()[0])
        self.assertEqual(self.client.post(f"{namespace}/{meta['id']}/revoke").status_code, 200)
        self.assertEqual(self.client.get(url, headers=authorized).status_code, 401)

    def new_lease(self, device, anchor):
        from siteguard.scans import lease_token

        with transaction(self.owner) as db:
            row = db.execute("SELECT * FROM terminals WHERE id=%s", (device.row["id"],)).fetchone()
        return lease_token(row, int(anchor.timestamp() * 1000), anchor, self.rules)[0]
