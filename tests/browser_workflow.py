"""Chromium smoke test with a real local HTTP server, restricted PostgreSQL role and synthetic staff."""
import csv
import os
import threading
import time
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from playwright.sync_api import expect, sync_playwright

from app import app
from siteguard.db import transaction
from siteguard.registry import badge_code
from support import DatabaseTest
from test_attendance import API
from siteguard.timekeeping import Policy


@contextmanager
def server():
    config = uvicorn.Config(app, host="127.0.0.1", port=4187, log_level="warning")
    process = uvicorn.Server(config)
    thread = threading.Thread(target=process.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if process.started:
                break
            time.sleep(0.05)
        if not process.started:
            raise RuntimeError("Could not start test API")
        yield "http://127.0.0.1:4187/"
    finally:
        process.should_exit = True
        thread.join(timeout=5)


class BrowserWorkflow(DatabaseTest):
    def provision(self):
        self.site()
        self.account("field", "foreman", site_id="GATE", scope_code="A")
        self.account("engineer", "engineer", site_id="GATE", scope_code="P1")
        self.account("keeper", "timekeeper")
        rules = Policy(qr_mode="static", debounce_seconds=1, day_start="00:00", day_end="23:59",
                       late_grace_minutes=5, break_mins=0)
        self.assertEqual(self.client.put(API + "/config", json=rules.model_dump(mode="json")).status_code, 200)
        self.assertEqual(self.client.put(API + "/employees/EMP1", json={
            "name": "Browser Worker", "department": "Civil", "cost_code": "P1", "crew": "A",
            "shift_type": "Day Shift", "site_ids": ["GATE"],
        }).status_code, 200)
        issued = self.client.post(API + "/badges/issue", json={"employee_id": "EMP1", "mode": "STC"}).json()
        terminal = self.client.put(API + "/terminals/KIOSK", json={"name": "Gate kiosk", "site_id": "GATE",
                                                                 "latitude": 14.6, "longitude": 121}).json()
        local = datetime.now(ZoneInfo("Asia/Manila"))
        return terminal["credential"], badge_code(issued, "STATIC"), local.strftime("%Y-%m")

    def test_kiosk_reloads_offline_then_reviews_and_exports(self):
        credential, qr, period = self.provision()
        with sync_playwright() as playwright, server() as url:
            chromium = playwright.chromium.launch(executable_path=os.getenv("CHROMIUM_EXECUTABLE") or None,
                                                   args=["--no-sandbox"])
            kiosk = chromium.new_context(permissions=["geolocation"], geolocation={"latitude": 14.6, "longitude": 121,
                                                                                 "accuracy": 4})
            page = kiosk.new_page()
            page.goto(url + "#kiosk")
            page.get_by_label("Terminal credential").fill(credential)
            page.get_by_role("button", name="Enroll terminal").click()
            expect(page.get_by_role("heading", name="Scan a badge")).to_be_visible()
            page.wait_for_function("Boolean(navigator.serviceWorker.controller)")
            page.get_by_label("Action").select_option("in")
            page.get_by_label("Scanner input").fill(qr)
            page.get_by_role("button", name="Submit scan").click()
            expect(page.get_by_text("Clock-In Recorded")).to_be_visible()
            page.wait_for_timeout(1250)

            kiosk.set_offline(True)
            page.reload(wait_until="domcontentloaded")
            expect(page.get_by_role("heading", name="Scan a badge")).to_be_visible()
            page.get_by_label("Action").select_option("out")
            page.get_by_label("Scanner input").fill(qr)
            page.get_by_role("button", name="Submit scan").click()
            expect(page.get_by_text("Offline Captured & Sealed")).to_be_visible()
            kiosk.set_offline(False)
            expect(page.get_by_text("Clock-Out Recorded")).to_be_visible(timeout=16000)
            kiosk.close()

            with transaction(self.owner) as db:
                shifts = db.execute("SELECT id,raw_in,raw_out FROM shifts WHERE org_id=%s", (self.org_id,)).fetchall()
                self.assertEqual(len(shifts), 1)
                self.assertTrue(shifts[0]["raw_in"] and shifts[0]["raw_out"])
                shift = shifts[0]["id"]
            for username, label in (("field", "Field endorsement"), ("engineer", "Cost and overtime approved"),
                                    ("keeper", "Verified")):
                context = chromium.new_context(accept_downloads=True)
                page = context.new_page()
                page.goto(url + f"#verification/{shift}")
                page.get_by_label("Organization code").fill(self.slug)
                page.get_by_label("Username").fill(username)
                page.get_by_label("Password").fill(self.password)
                page.get_by_role("button", name="Sign in", exact=True).click()
                expect(page.get_by_role("heading", name="Browser Worker")).to_be_visible(timeout=10000)
                page.get_by_label("Action").select_option(label=label)
                page.get_by_label("Reason and evidence").fill("Verified synthetic fixture")
                page.get_by_role("button", name="Save review").click()
                expect(page.get_by_text("Review saved.")).to_be_visible()
                if username == "keeper":
                    page.get_by_role("link", name="Payroll exports").click()
                    page.get_by_label("Pay period").fill(period)
                    page.get_by_role("button", name="Generate CSV").click()
                    expect(page.get_by_text("Revision 1 is ready to download.")).to_be_visible()
                    with page.expect_download() as download:
                        page.get_by_role("link", name="CSV", exact=True).click()
                    with Path(download.value.path()).open(encoding="utf-8", newline="") as file:
                        rows = list(csv.reader(file))
                    self.assertEqual(len(rows[0]), 23)
                    self.assertEqual(rows[1][20], "Verified")
                    page.get_by_label("Employee ID").fill("EMP1")
                    page.get_by_role("button", name="Open print view").click()
                    expect(page.get_by_role("heading", name="Daily time record")).to_be_visible()
                context.close()
            chromium.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
