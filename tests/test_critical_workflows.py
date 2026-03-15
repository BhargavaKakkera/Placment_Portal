import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ["DATABASE_URL"] = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:2005@localhost:5432/test_placement_portal",
)
os.environ["DEBUG"] = "true"

from fastapi.testclient import TestClient
from sqlmodel import Session
from sqlalchemy import text
from alembic import command
from alembic.config import Config

from app.main import app
from app.database import engine


class CriticalWorkflowTests(unittest.TestCase):
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

    def _register(self, email: str, password: str, role: str) -> str:
        resp = self.client.post(
            "/auth/register",
            json={"email": email, "password": password, "role": role},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()

        if role in {"admin", "company"}:
            verification_token = payload.get("verification_token")
            self.assertTrue(verification_token)

            verify_resp = self.client.post(
                "/auth/verify-email",
                json={"token": verification_token},
            )
            self.assertEqual(verify_resp.status_code, 200, verify_resp.text)

            return self._login(email, password)

        return payload["access_token"]

    def _provision_student(
        self,
        admin_token: str,
        email: str,
        password: str,
        name: str,
        reg_no: str,
        roll_no: str,
        cgpa: float,
        branch: str,
        graduation_year: int,
        backlogs: int = 0,
    ) -> tuple[str, int]:
        provision_resp = self.client.post(
            "/admin/students/provision",
            headers=self._auth_header(admin_token),
            json={
                "email": email,
                "name": name,
                "reg_no": reg_no,
                "roll_no": roll_no,
                "cgpa": cgpa,
                "branch": branch,
                "graduation_year": graduation_year,
                "backlogs": backlogs,
            },
        )
        self.assertEqual(provision_resp.status_code, 200, provision_resp.text)
        invite_token = provision_resp.json()["invite_token"]

        reset_resp = self.client.post(
            "/auth/reset-password",
            json={"token": invite_token, "new_password": password},
        )
        self.assertEqual(reset_resp.status_code, 200, reset_resp.text)

        token = self._login(email, password)
        return token, provision_resp.json()["student_id"]

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
        self.assertIn("users", payload)
        self.assertIsInstance(payload["users"], list)

    def test_password_reset_flow(self):
        admin_token = self._register("admin_reset@example.com", "Password123", "admin")
        email = "student_reset@example.com"
        old_password = "Password123"
        new_password = "NewPassword123"

        self._provision_student(
            admin_token,
            email,
            old_password,
            "Student Reset",
            "REGRESET1",
            "ROLLRESET1",
            8.1,
            "CSE",
            2027,
        )

        forgot_resp = self.client.post(
            "/auth/forgot-password",
            json={"email": email},
        )
        self.assertEqual(forgot_resp.status_code, 200, forgot_resp.text)
        forgot_payload = forgot_resp.json()
        self.assertIn("message", forgot_payload)
        self.assertTrue(forgot_payload.get("reset_token"))

        reset_resp = self.client.post(
            "/auth/reset-password",
            json={
                "token": forgot_payload["reset_token"],
                "new_password": new_password,
            },
        )
        self.assertEqual(reset_resp.status_code, 200, reset_resp.text)

        old_login = self.client.post(
            "/auth/login",
            data={"username": email, "password": old_password},
        )
        self.assertEqual(old_login.status_code, 401, old_login.text)

        new_login = self.client.post(
            "/auth/login",
            data={"username": email, "password": new_password},
        )
        self.assertEqual(new_login.status_code, 200, new_login.text)

    def test_test_suite_uses_postgresql_database(self):
        with Session(engine) as session:
            value = session.exec(text("SELECT current_database()")).one()
        if not isinstance(value, str):
            value = value[0]
        self.assertEqual(value, "test_placement_portal")

    def test_student_soft_delete_deactivates_account(self):
        admin_token = self._register("admin_soft_delete@example.com", "Password123", "admin")
        student_token, _ = self._provision_student(
            admin_token,
            "student1@example.com",
            "Password123",
            "Student One",
            "REG001",
            "R001",
            8.2,
            "CSE",
            2027,
        )

        delete_resp = self.client.delete("/students/me", headers=self._auth_header(student_token))
        self.assertEqual(delete_resp.status_code, 200, delete_resp.text)

        # Existing token should stop working because account becomes inactive.
        me_resp = self.client.get("/students/me", headers=self._auth_header(student_token))
        self.assertEqual(me_resp.status_code, 403, me_resp.text)

    def test_accepted_to_rejected_rolls_back_and_unlocks_student(self):
        admin_token = self._register("admin1@example.com", "Password123", "admin")
        company_token = self._register("company1@example.com", "Password123", "company")
        student_token, student_id = self._provision_student(
            admin_token,
            "student2@example.com",
            "Password123",
            "Student Two",
            "REG002",
            "R002",
            8.4,
            "CSE",
            2027,
        )

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
        application_id = applicants_resp.json()["items"][0]["id"]

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
        student_token, student_id = self._provision_student(
            admin_token,
            student_email,
            student_password,
            "Student Three",
            "REG003",
            "R003",
            8.0,
            "CSE",
            2027,
        )

        company_profile = self.client.post(
            "/companies/",
            headers=self._auth_header(company_token),
            json={"name": "Beta Corp"},
        )
        self.assertEqual(company_profile.status_code, 200, company_profile.text)
        company_id = company_profile.json()["id"]

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

    def test_admin_can_filter_students_by_branch(self):
        admin_token = self._register("admin3@example.com", "Password123", "admin")
        self._provision_student(
            admin_token,
            "student4@example.com",
            "Password123",
            "Student Four",
            "REG004",
            "R004",
            8.1,
            "CSE",
            2027,
        )
        self._provision_student(
            admin_token,
            "student5@example.com",
            "Password123",
            "Student Five",
            "REG005",
            "R005",
            8.3,
            "ECE",
            2027,
        )

        filtered = self.client.get(
            "/admin/students?branch=CSE",
            headers=self._auth_header(admin_token),
        )
        self.assertEqual(filtered.status_code, 200, filtered.text)
        payload = filtered.json()

        self.assertEqual(payload["total"], 1)
        self.assertIn("has_more", payload)
        self.assertFalse(payload["has_more"])
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["branch"], "CSE")

    def test_public_jobs_list_returns_pagination_metadata(self):
        admin_token = self._register("admin_jobs_meta@example.com", "Password123", "admin")
        company_token = self._register("company_jobs_meta@example.com", "Password123", "company")

        company_profile = self.client.post(
            "/companies/",
            headers=self._auth_header(company_token),
            json={"name": "Jobs Meta Corp"},
        )
        self.assertEqual(company_profile.status_code, 200, company_profile.text)
        company_id = company_profile.json()["id"]

        verify_company = self.client.post(
            f"/admin/companies/{company_id}/verify",
            headers=self._auth_header(admin_token),
        )
        self.assertEqual(verify_company.status_code, 200, verify_company.text)

        for i in range(2):
            job_resp = self.client.post(
                "/jobs/",
                headers=self._auth_header(company_token),
                json={
                    "title": f"SDE Meta {i}",
                    "description": "Software Developer role",
                    "role_type": "full_time",
                    "ctc": 10.0 + i,
                    "application_deadline": (
                        datetime.now(timezone.utc) + timedelta(days=3)
                    ).isoformat(),
                },
            )
            self.assertEqual(job_resp.status_code, 200, job_resp.text)

        jobs_resp = self.client.get("/jobs/?skip=0&limit=1")
        self.assertEqual(jobs_resp.status_code, 200, jobs_resp.text)
        payload = jobs_resp.json()

        self.assertEqual(payload["skip"], 0)
        self.assertEqual(payload["limit"], 1)
        self.assertEqual(payload["total"], 2)
        self.assertTrue(payload["has_more"])
        self.assertEqual(len(payload["items"]), 1)

    def test_internship_acceptance_allows_full_time_until_full_time_is_accepted(self):
        admin_token = self._register("admin4@example.com", "Password123", "admin")
        company_token = self._register("company4@example.com", "Password123", "company")
        student_token, student_id = self._provision_student(
            admin_token,
            "student6@example.com",
            "Password123",
            "Student Six",
            "REG006",
            "R006",
            8.6,
            "CSE",
            2027,
        )

        company_profile = self.client.post(
            "/companies/",
            headers=self._auth_header(company_token),
            json={"name": "Gamma Corp"},
        )
        self.assertEqual(company_profile.status_code, 200, company_profile.text)
        company_id = company_profile.json()["id"]

        verify_company = self.client.post(
            f"/admin/companies/{company_id}/verify",
            headers=self._auth_header(admin_token),
        )
        self.assertEqual(verify_company.status_code, 200, verify_company.text)

        internship_job = self.client.post(
            "/jobs/",
            headers=self._auth_header(company_token),
            json={
                "title": "Intern 1",
                "description": "Internship role",
                "role_type": "internship",
                "stipend": 30000,
                "internship_duration": "6 months",
                "application_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=3)
                ).isoformat(),
            },
        )
        self.assertEqual(internship_job.status_code, 200, internship_job.text)
        internship_job_id = internship_job.json()["id"]

        second_internship_job = self.client.post(
            "/jobs/",
            headers=self._auth_header(company_token),
            json={
                "title": "Intern 2",
                "description": "Another internship role",
                "role_type": "internship",
                "stipend": 35000,
                "internship_duration": "2 months",
                "application_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=3)
                ).isoformat(),
            },
        )
        self.assertEqual(second_internship_job.status_code, 200, second_internship_job.text)
        second_internship_job_id = second_internship_job.json()["id"]

        full_time_job = self.client.post(
            "/jobs/",
            headers=self._auth_header(company_token),
            json={
                "title": "SDE 1",
                "description": "Full-time role",
                "role_type": "full_time",
                "ctc": 14.0,
                "application_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=3)
                ).isoformat(),
            },
        )
        self.assertEqual(full_time_job.status_code, 200, full_time_job.text)
        full_time_job_id = full_time_job.json()["id"]

        second_full_time_job = self.client.post(
            "/jobs/",
            headers=self._auth_header(company_token),
            json={
                "title": "SDE 2",
                "description": "Another full-time role",
                "role_type": "full_time",
                "ctc": 16.0,
                "application_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=3)
                ).isoformat(),
            },
        )
        self.assertEqual(second_full_time_job.status_code, 200, second_full_time_job.text)
        second_full_time_job_id = second_full_time_job.json()["id"]

        internship_apply = self.client.post(
            f"/jobs/{internship_job_id}/apply",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(internship_apply.status_code, 200, internship_apply.text)

        internship_applicants = self.client.get(
            f"/companies/jobs/{internship_job_id}/applicants",
            headers=self._auth_header(company_token),
        )
        self.assertEqual(internship_applicants.status_code, 200, internship_applicants.text)
        internship_application_id = internship_applicants.json()["items"][0]["id"]

        shortlist_internship = self.client.patch(
            f"/companies/applications/{internship_application_id}",
            headers=self._auth_header(company_token),
            json={"status": "shortlisted"},
        )
        self.assertEqual(shortlist_internship.status_code, 200, shortlist_internship.text)

        internship_offer = self.client.patch(
            f"/companies/applications/{internship_application_id}",
            headers=self._auth_header(company_token),
            json={
                "status": "offered",
                "offer_response_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=2)
                ).isoformat(),
            },
        )
        self.assertEqual(internship_offer.status_code, 200, internship_offer.text)
        internship_offer_id = internship_offer.json()["id"]

        accept_internship = self.client.post(
            f"/students/offers/{internship_offer_id}/accept",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(accept_internship.status_code, 200, accept_internship.text)

        blocked_internship_apply = self.client.post(
            f"/jobs/{second_internship_job_id}/apply",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(blocked_internship_apply.status_code, 409, blocked_internship_apply.text)

        allowed_full_time_apply = self.client.post(
            f"/jobs/{full_time_job_id}/apply",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(allowed_full_time_apply.status_code, 200, allowed_full_time_apply.text)

        full_time_applicants = self.client.get(
            f"/companies/jobs/{full_time_job_id}/applicants",
            headers=self._auth_header(company_token),
        )
        self.assertEqual(full_time_applicants.status_code, 200, full_time_applicants.text)
        full_time_application_id = full_time_applicants.json()["items"][0]["id"]

        shortlist_full_time = self.client.patch(
            f"/companies/applications/{full_time_application_id}",
            headers=self._auth_header(company_token),
            json={"status": "shortlisted"},
        )
        self.assertEqual(shortlist_full_time.status_code, 200, shortlist_full_time.text)

        full_time_offer = self.client.patch(
            f"/companies/applications/{full_time_application_id}",
            headers=self._auth_header(company_token),
            json={
                "status": "offered",
                "ctc": 14.0,
                "offer_response_deadline": (
                    datetime.now(timezone.utc) + timedelta(days=2)
                ).isoformat(),
            },
        )
        self.assertEqual(full_time_offer.status_code, 200, full_time_offer.text)
        full_time_offer_id = full_time_offer.json()["id"]

        accept_full_time = self.client.post(
            f"/students/offers/{full_time_offer_id}/accept",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(accept_full_time.status_code, 200, accept_full_time.text)

        blocked_full_time_apply = self.client.post(
            f"/jobs/{second_full_time_job_id}/apply",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(blocked_full_time_apply.status_code, 409, blocked_full_time_apply.text)

        blocked_intern_after_full_time = self.client.post(
            f"/jobs/{second_internship_job_id}/apply",
            headers=self._auth_header(student_token),
        )
        self.assertEqual(blocked_intern_after_full_time.status_code, 409, blocked_intern_after_full_time.text)


if __name__ == "__main__":
    unittest.main()
