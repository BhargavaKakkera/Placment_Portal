import unittest

from pydantic import ValidationError

from app.routers.students import _student_update_data
from app.schemas import JobCreate, StudentUpdate


class StudentUpdateValidationTests(unittest.TestCase):
    def test_blank_optional_profile_fields_are_none(self):
        payload = StudentUpdate.model_validate(
            {
                "phone": "9876543210",
                "personal_email": "",
                "resume_url": "",
                "github_url": "",
            }
        )

        self.assertEqual(payload.phone, "9876543210")
        self.assertIsNone(payload.personal_email)
        self.assertIsNone(payload.resume_url)
        self.assertIsNone(payload.github_url)

    def test_phone_must_be_exactly_ten_digits(self):
        with self.assertRaises(ValidationError) as ctx:
            StudentUpdate.model_validate({"phone": "123456"})

        self.assertIn("Phone number must be exactly 10 digits", str(ctx.exception))

    def test_update_data_does_not_null_academic_fields(self):
        payload = StudentUpdate.model_validate(
            {
                "phone": "9876543210",
                "personal_email": "student@example.com",
                "cgpa": None,
                "backlogs": None,
            }
        )

        self.assertEqual(
            _student_update_data(payload),
            {
                "phone": "9876543210",
                "personal_email": "student@example.com",
            },
        )


class JobCreateValidationTests(unittest.TestCase):
    def _valid_job_data(self, **overrides):
        data = {
            "title": "Software Engineer",
            "description": "Build placement portal features",
            "role_type": "full_time",
            "ctc": 300000,
            "allowed_branches": None,
        }
        data.update(overrides)
        return data

    def test_ctc_accepts_any_positive_amount(self):
        for ctc in (1, 300000, 100000000):
            with self.subTest(ctc=ctc):
                payload = JobCreate.model_validate(self._valid_job_data(ctc=ctc))
                self.assertEqual(payload.ctc, ctc)

    def test_ctc_rejects_non_positive_amount(self):
        for ctc in (0, -1):
            with self.subTest(ctc=ctc):
                with self.assertRaises(ValidationError) as ctx:
                    JobCreate.model_validate(self._valid_job_data(ctc=ctc))

                self.assertIn("CTC must be greater than 0", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
