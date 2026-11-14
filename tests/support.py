import os
import unittest
from unittest.mock import patch
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app import app
from siteguard.db import migrate, transaction
from siteguard.security import hash_password

ORIGIN = {"origin": "http://testserver"}


class DatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = os.getenv("TEST_POSTGRES_URL")
        if not base:
            raise unittest.SkipTest("Set TEST_POSTGRES_URL to run PostgreSQL integration tests")
        cls.db_name = "siteguard_" + uuid4().hex[:12]
        cls.role = cls.db_name + "_runtime"
        cls.base = base
        runtime_password = uuid4().hex
        with psycopg.connect(base, autocommit=True) as conn:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.db_name)))
            conn.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(cls.role), sql.Literal(runtime_password)))
        cls.addClassCleanup(cls.drop_test_database)
        cls.owner = make_conninfo(base, dbname=cls.db_name)
        cls.runtime = make_conninfo(**{**conninfo_to_dict(cls.owner), "user": cls.role,
                                      "password": runtime_password})
        migrate(cls.owner, cls.role)
        environment = patch.dict(os.environ, {"DATABASE_URL": cls.runtime, "SITEGUARD_SECRET": "test-secret-" * 4})
        environment.start()
        cls.addClassCleanup(environment.stop)

    @classmethod
    def drop_test_database(cls):
        with psycopg.connect(cls.base, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(cls.db_name)))
            conn.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(cls.role)))

    def setUp(self):
        self.org_id, self.admin_id = uuid4(), uuid4()
        self.slug = "fixture-" + self.org_id.hex[:12]
        self.password = "sample fixture password"
        with transaction(self.owner) as db:
            db.execute("INSERT INTO organizations VALUES (%s,%s,%s)", (self.org_id, self.slug, "Fixture Org"))
            db.execute("""INSERT INTO staff (id,org_id,login,name,role,password_hash)
                VALUES (%s,%s,'admin','Test Admin','admin',%s)""",
                       (self.admin_id, self.org_id, hash_password(self.password)))
        self.client = TestClient(app, headers=ORIGIN)
        self.addCleanup(self.client.close)
        self.assertEqual(self.login(self.client, "admin").status_code, 200)

    def login(self, client, login):
        return client.post("/api/v1/auth/login", json={"organization": self.slug, "login": login,
                                                       "password": self.password})

    def site(self, ident="GATE", **options):
        payload = {"name": ident, "timezone": "Asia/Manila", "latitude": 14.6, "longitude": 121.0,
                   "radius_m": 100, **options}
        response = self.client.put(f"/api/v1/sites/{ident}", json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def account(self, login, role, **options):
        response = self.client.put(f"/api/v1/users/{login}", json={"name": login, "role": role,
                                                                   "password": self.password, **options})
        self.assertEqual(response.status_code, 200, response.text)
        client = TestClient(app, headers=ORIGIN)
        self.addCleanup(client.close)
        self.assertEqual(self.login(client, login).status_code, 200)
        return client
