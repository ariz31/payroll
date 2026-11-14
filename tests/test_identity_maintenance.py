from datetime import timedelta
from unittest.mock import patch

import httpx
import jwt
import psycopg
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from app import app
from siteguard.db import now, transaction
from siteguard.identity import linked_user, validate_id_token
from siteguard.maintenance import cleanup
from support import DatabaseTest
from test_attendance import API, AttendanceFixture


class IdentityTest(DatabaseTest):
    def test_sso_subject_link_cannot_claim_password_account(self):
        with transaction(self.runtime) as db:
            self.assertIsNone(linked_user(db, self.slug, "https://identity.example",
                                          {"email": "admin", "email_verified": True, "sub": "unknown"}))
        response = self.client.put(f"{API}/users/user@example.com", json={"name": "User", "role": "auditor"})
        self.assertEqual(response.status_code, 200, response.text)
        with transaction(self.runtime) as db:
            claims = {"email": "user@example.com", "email_verified": True, "sub": "person-1"}
            linked = linked_user(db, self.slug, "https://identity.example", claims)
            self.assertEqual(str(linked["id"]), response.json()["id"])
            self.assertIsNone(linked_user(db, self.slug, "https://identity.example", {**claims, "sub": "other"}))
            self.assertEqual(linked_user(db, self.slug, "https://identity.example", {"sub": "person-1"})["id"], linked["id"])

    def test_id_token_verifies_signature_and_audience_and_nonce(self):
        issuer = "https://identity.example"
        pair = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key = jwt.algorithms.RSAAlgorithm.to_jwk(pair.public_key(), as_dict=True)
        key["kid"] = "signing"
        token = jwt.encode({"iss": issuer, "aud": "client", "sub": "person-1", "nonce": "flow",
                            "iat": now(), "exp": now() + timedelta(minutes=1)}, pair, algorithm="RS256",
                           headers={"kid": "signing"})
        transport = httpx.MockTransport(lambda req: httpx.Response(200, json={"keys": [key]}))
        with httpx.Client(transport=transport) as client:
            metadata = {"jwks_uri": issuer + "/jwks"}
            self.assertEqual(validate_id_token(client, metadata, token, issuer, "client", "flow")["sub"], "person-1")
            with self.assertRaises(ValueError):
                validate_id_token(client, metadata, token, issuer, "client", "wrong")
            with self.assertRaises(jwt.InvalidAudienceError):
                validate_id_token(client, metadata, token, issuer, "other-client", "flow")


class MaintenanceTest(AttendanceFixture):
    def test_cron_auth_retention_and_immutable_raw_state(self):
        worker = self.worker()
        with transaction(self.owner) as db:
            for employee, expiry in ((worker["employee_id"], now() - timedelta(days=1)),):
                db.execute("INSERT INTO profile_evidence VALUES (%s,%s,%s,%s)", (self.org_id, employee, b"x", expiry))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege), transaction(self.runtime) as db:
            db.execute("DELETE FROM profile_evidence")
        with TestClient(app) as client, patch.dict("os.environ", {"CRON_SECRET": "retention-test-key-1234"}):
            self.assertEqual(client.get(API + "/internal/daily").status_code, 401)
            result = client.get(API + "/internal/daily", headers={"Authorization": "Bearer retention-test-key-1234"})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["badge_images"], 1)
        self.assertEqual(cleanup()["badge_images"], 0)
