import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = "sqlite:///./test_placement.db"

from fastapi.testclient import TestClient
from sqlmodel import Session
from sqlalchemy import text

from app.main import app
from app.database import init_db, engine


class CriticalWorkflowTests(unittest.TestCase):
    def setUp(self):
        engine.dispose()
        os.environ["RESET_DB"] = "1"
        init_db()
        os.environ.pop("RESET_DB", None)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        engine.dispose()
        db_file = os.path.join(os.getcwd(), "test_placement.db")
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except OSError:
                pass

    def _auth_header(self, token: str):
        return {"Authorization": f"Bearer {token}"}

    def _register(self, email: str, password: str, role: str) -> str:
        resp = self.client.post(
            "/auth/register",
            json={"email": email, "password": password, "role": role},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["access_token"]

    def _login(self, email: str, password: str) -> str:
        resp = self.client.post(
            "/auth/login",
            data={"username": email, "password": password},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        return resp.json()["access_token"]

    def test_root_does_not_expose_users(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertIn("message", payload)
        self.assertNotIn("users", payload)

    def test_sqlite_foreign_keys_enabled(self):
        with Session(engine) as session:
            value = session.exec(text("PRAGMA foreign_keys")).one()
        if not isinstance(value, int):
            value = value[0]
        self.assertEqual(value, 1)

    def test_student_soft_delete_deactivates_account(self):
        student_token = self._register("student1@example.com", "Password123", "student")

        create_resp = self.client.post(
            "/students/",
            headers=self._auth_header(student_token),
            json={
                "name": "Student One",
                "roll_no": "R001",
                "cgpa": 8.2,
                "branch": "CSE",
                "graduation_year": 2027,
                "backlogs": 0,
            },
        )
        self.assertEqual(create_resp.status_code, 200, create_resp.text)

        delete_resp = self.client.delete("/students/me", headers=self._auth_header(student_token))
        self.assertEqual(delete_resp.status_code, 200, delete_resp.text)

        # Existing token should stop working because account becomes inactive.
        me_resp = self.client.get("/students/me", headers=self._auth_header(student_token))
        self.assertEqual(me_resp.status_code, 403, me_resp.text)

    def test_accepted_to_rejected_rolls_back_and_unlocks_student(self):
        admin_token = self._register("admin1@example.com", "Password123", "admin")
        company_token = self._register("company1@example.com", "Password123", "company")
        student_token = self._register("student2@example.com", "Password123", "student")

        company_profile = self.client.post(
            "/companies/",
            headers=self._auth_header(company_token),
            json={"name": "Acme Corp"},
        )
        self.assertEqual(company_profile.status_code, 200, company_profile.text)
        company_id = company_profile.json()["id"]

        verify_company = self.client.post(
            f"/admin/companies/{company_id}/verify",
            headers=self._auth_header(admin_token),
        )
        self.assertEqual(verify_company.status_code, 200, verify_company.text)

        create_student = self.client.post(
            "/students/",
            headers=self._auth_header(student_token),
            json={
                "name": "Student Two",
                "roll_no": "R002",
                "cgpa": 8.4,
                "branch": "CSE",
                "graduation_year": 2027,
                "backlogs": 0,
            },
        )
        self.assertEqual(create_student.status_code, 200, create_student.text)
        student_id = create_student.json()["id"]

        verify_student = self.client.post(
            f"/admin/students/{student_id}/verify",
            headers=self._auth_header(admin_token),
        )
        self.assertEqual(verify_student.status_code, 200, verify_student.text)

        job_resp = self.client.post(
            "/jobs/",
            headers=self._auth_header(company_token),
            json={
                "title": "SDE I",
                "description": "Software Developer role",
                "role_type": "full_time",
                "ctc": 12.0,
                "application_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=3)
                ).isoformat(),
            },
        )
        self.assertEqual(job_resp.status_code, 200, job_resp.text)
        job_id = job_resp.json()["id"]

        apply_resp = self.client.post(
            f"/jobs/{job_id}/apply",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(apply_resp.status_code, 200, apply_resp.text)

        applicants_resp = self.client.get(
            f"/companies/jobs/{job_id}/applicants",
            headers=self._auth_header(company_token),
        )
        self.assertEqual(applicants_resp.status_code, 200, applicants_resp.text)
        application_id = applicants_resp.json()[0]["id"]

        shortlist_resp = self.client.patch(
            f"/companies/applications/{application_id}",
            headers=self._auth_header(company_token),
            json={"status": "shortlisted"},
        )
        self.assertEqual(shortlist_resp.status_code, 200, shortlist_resp.text)

        offer_resp = self.client.patch(
            f"/companies/applications/{application_id}",
            headers=self._auth_header(company_token),
            json={
                "status": "offered",
                "ctc": 12.0,
                "offer_response_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=2)
                ).isoformat(),
            },
        )
        self.assertEqual(offer_resp.status_code, 200, offer_resp.text)
        offer_id = offer_resp.json()["id"]

        accept_resp = self.client.post(
            f"/students/offers/{offer_id}/accept",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(accept_resp.status_code, 200, accept_resp.text)

        # Company is allowed to move accepted -> rejected.
        reject_resp = self.client.patch(
            f"/companies/applications/{application_id}",
            headers=self._auth_header(company_token),
            json={"status": "rejected"},
        )
        self.assertEqual(reject_resp.status_code, 200, reject_resp.text)
        self.assertEqual(reject_resp.json()["status"], "rejected")

        # After rollback, student should be able to apply to another job.
        second_job_resp = self.client.post(
            "/jobs/",
            headers=self._auth_header(company_token),
            json={
                "title": "SDE II",
                "description": "Second Software Developer role",
                "role_type": "full_time",
                "ctc": 15.0,
                "application_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=3)
                ).isoformat(),
            },
        )
        self.assertEqual(second_job_resp.status_code, 200, second_job_resp.text)
        second_job_id = second_job_resp.json()["id"]

        second_apply = self.client.post(
            f"/jobs/{second_job_id}/apply",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(second_apply.status_code, 200, second_apply.text)

    def test_admin_can_reactivate_student_and_company(self):
        admin_token = self._register("admin2@example.com", "Password123", "admin")
        company_email = "company2@example.com"
        student_email = "student3@example.com"
        company_password = "Password123"
        student_password = "Password123"

        company_token = self._register(company_email, company_password, "company")
        student_token = self._register(student_email, student_password, "student")

        company_profile = self.client.post(
            "/companies/",
            headers=self._auth_header(company_token),
            json={"name": "Beta Corp"},
        )
        self.assertEqual(company_profile.status_code, 200, company_profile.text)
        company_id = company_profile.json()["id"]

        student_profile = self.client.post(
            "/students/",
            headers=self._auth_header(student_token),
            json={
                "name": "Student Three",
                "roll_no": "R003",
                "cgpa": 8.0,
                "branch": "CSE",
                "graduation_year": 2027,
                "backlogs": 0,
            },
        )
        self.assertEqual(student_profile.status_code, 200, student_profile.text)
        student_id = student_profile.json()["id"]

        del_company = self.client.delete("/companies/me", headers=self._auth_header(company_token))
        self.assertEqual(del_company.status_code, 200, del_company.text)
        del_student = self.client.delete("/students/me", headers=self._auth_header(student_token))
        self.assertEqual(del_student.status_code, 200, del_student.text)

        # Reactivate both from admin endpoints.
        react_company = self.client.post(
            f"/admin/companies/{company_id}/reactivate",
            headers=self._auth_header(admin_token),
        )
        self.assertEqual(react_company.status_code, 200, react_company.text)

        react_student = self.client.post(
            f"/admin/students/{student_id}/reactivate",
            headers=self._auth_header(admin_token),
        )
        self.assertEqual(react_student.status_code, 200, react_student.text)

        # They should be able to login again after reactivation.
        new_company_token = self._login(company_email, company_password)
        new_student_token = self._login(student_email, student_password)
        self.assertTrue(isinstance(new_company_token, str) and len(new_company_token) > 10)
        self.assertTrue(isinstance(new_student_token, str) and len(new_student_token) > 10)


if __name__ == "__main__":
    unittest.main()
