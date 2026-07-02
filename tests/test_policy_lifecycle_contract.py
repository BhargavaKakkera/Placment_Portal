import os
import unittest

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("ENABLE_RATE_LIMITING", "false")

from app.main import lifecycle_policy


class LifecyclePolicyContractTests(unittest.TestCase):
    def test_policy_has_expected_contract_sections(self):
        data = lifecycle_policy()
        self.assertIn("policy_version", data)
        self.assertIn("company_state", data)
        self.assertIn("job_rules", data)
        self.assertIn("application_rules", data)
        self.assertIn("offer_rules", data)
        self.assertIn("admin_rules", data)

    def test_offer_history_rule_is_explicit(self):
        data = lifecycle_policy()
        accepted_rule = data["offer_rules"]["accepted_offer_if_company_becomes_inactive"]
        self.assertTrue(accepted_rule["remains_in_history"])
        self.assertFalse(accepted_rule["status_changes_automatically"])


if __name__ == "__main__":
    unittest.main()

