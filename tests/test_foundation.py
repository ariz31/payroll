import unittest

import psycopg
from fastapi.testclient import TestClient

from app import app
from siteguard.db import migrate, transaction
from support import DatabaseTest


class FoundationTest(DatabaseTest):
    def test_runtime_health_and_repeatable_migration(self):
        migrate(self.owner, self.role)
        self.assertEqual(self.client.get('/api/v1/health/ready').json(), {"status": "ready"})
        self.assertEqual(self.client.get('/api/openapi.json').json()['info']['title'], 'SiteGuard QR')

    def test_roles_sites_sessions_and_no_cross_origin_writes(self):
        self.site()
        self.site("EAST")
        foreman = self.account("foreman", "foreman", site_id="GATE")
        self.assertEqual([site["id"] for site in foreman.get('/api/v1/sites').json()], ["GATE"])
        self.assertEqual(foreman.get('/api/v1/users').status_code, 403)
        self.assertEqual(self.client.post('/api/v1/auth/logout', headers={'Origin': 'https://other.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/auth/logout').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/auth/me').status_code, 401)

    def test_runtime_cannot_erase_audit(self):
        self.site()
        for statement in ('DELETE FROM control_audit', 'TRUNCATE control_audit', 'UPDATE control_audit SET action=\'x\''):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege), transaction(self.runtime) as db:
                db.execute(statement)


class LivenessTest(unittest.TestCase):
    def test_process_liveness(self):
        with TestClient(app) as client:
            self.assertEqual(client.get('/api/v1/health/live').json(), {"status": "ok"})
