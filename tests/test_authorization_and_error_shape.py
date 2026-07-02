import os
import unittest

os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:2005@localhost:5432/test_placement_portal",
)
os.environ["TEST_DATABASE_URL"] = "postgresql+psycopg://postgres:2005@localhost:5432/test_placement_portal"
os.environ["DEBUG"] = "true"
os.environ["LOG_LEVEL"] = "ERROR"
os.environ["ENABLE_RATE_LIMITING"] = "false"
os.environ["SECRET_KEY"] = "588b4257178a991143c21aa7e42c102999c2c2d32e5069d6cc8389c2b3fc0fb5"
os.environ["JWT_SECRET_KEY"] = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2"
os.environ["SESSION_SECRET_KEY"] = "z9y8x7w6v5u4t3s2r1q0p9o8n7m6l5k4j3i2h1g0f9e8d7c6b5a4z3y2x1w0v9"

from fastapi.testclient import TestClient
from alembic import command
from alembic.config import Config
from app.main import app
from app.database import engine


class AuthorizationAndErrorShapeTests(unittest.TestCase):
    def setUp(self):
        engine.dispose()
        alembic_cfg = Config("alembic.ini")
        command.downgrade(alembic_cfg, "base")
        command.upgrade(alembic_cfg, "head")
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        engine.dispose()

    def _auth_header(self, token: str):
        return {"Authorization": f"Bearer {token}"}

    def _login(self, email: str, password: str) -> str:
        resp = self.client.post("/auth/login", data={"username": email, "password": password})
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["access_token"]

    def _register(self, email: str, password: str, role: str) -> str:
        resp = self.client.post(
            "/auth/register",
            json={"email": email, "password": password, "role": role},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        if role in {"admin", "company"}:
            verify_resp = self.client.post(
                "/auth/verify-email",
                json={"token": payload["verification_token"]},
            )
            self.assertEqual(verify_resp.status_code, 200, verify_resp.text)
            return self._login(email, password)
        return payload["access_token"]

    def _provision_student(self, admin_token: str, email: str, password: str):
        provision_resp = self.client.post(
            "/admin/students/provision",
            headers=self._auth_header(admin_token),
            json={
                "email": email,
                "name": "Student Test",
                "reg_no": "REGAUTH1",
                "roll_no": "ROLLAUTH1",
                "cgpa": 8.0,
                "branch": "CSE",
                "graduation_year": 2027,
                "backlogs": 0,
            },
        )
        self.assertEqual(provision_resp.status_code, 200, provision_resp.text)
        invite = provision_resp.json()["invite_token"]
        reset_resp = self.client.post(
            "/auth/reset-password",
            json={"token": invite, "new_password": password},
        )
        self.assertEqual(reset_resp.status_code, 200, reset_resp.text)
        return self._login(email, password)

    def test_student_cannot_access_admin_endpoints(self):
        admin_token = self._register("auth_admin@example.com", "Password123", "admin")
        student_token = self._provision_student(admin_token, "auth_student@example.com", "Password123")

        resp = self.client.get("/admin/students", headers=self._auth_header(student_token))
        self.assertEqual(resp.status_code, 403, resp.text)
        payload = resp.json()
        self.assertIn("detail", payload)
        self.assertIn(payload.get("error_code"), {"HTTP_403", "AUTHORIZATION_ERROR"})

    def test_company_cannot_access_student_profile_endpoint(self):
        company_token = self._register("auth_company@example.com", "Password123", "company")
        resp = self.client.get("/students/me", headers=self._auth_header(company_token))
        self.assertEqual(resp.status_code, 403, resp.text)
        self.assertIn(resp.json().get("error_code"), {"HTTP_403", "AUTHORIZATION_ERROR"})

    def test_http_exception_shape_is_standardized(self):
        resp = self.client.get("/jobs/999999")
        self.assertEqual(resp.status_code, 404, resp.text)
        payload = resp.json()
        self.assertIn("detail", payload)
        self.assertEqual(payload.get("error_code"), "HTTP_404")


if __name__ == "__main__":
    unittest.main()
