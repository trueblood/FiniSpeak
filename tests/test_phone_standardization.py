import unittest
from types import SimpleNamespace

from scripts.standardize_phone_numbers import build_report, public_report


def account(identifier, email, phone, normalized=""):
    return SimpleNamespace(id=identifier, email=email, phone=phone, phone_normalized=normalized)


def private_profile(identifier, email, phone):
    return SimpleNamespace(id=identifier, email=email, phone=phone)


class PhoneStandardizationScriptTests(unittest.TestCase):
    def test_dry_run_standardizes_accounts_and_interpreter_private_phone(self):
        report = build_report(
            [account("one", "one@example.test", "(484) 459-5017")],
            [private_profile("one", "one@example.test", "4844595017")],
        )
        result = public_report(report)
        self.assertTrue(result["safeToApply"])
        self.assertEqual(result["accountChanges"][0]["to"], "+14844595017")
        self.assertEqual(result["accountChanges"][0]["normalized"], "14844595017")
        self.assertEqual(result["interpreterPrivateChanges"][0]["to"], "+14844595017")
        self.assertFalse(result["applied"])

    def test_duplicate_numbers_block_apply_until_specific_accounts_are_cleared(self):
        users = [
            account("one", "one@example.test", "17653700301"),
            account("two", "two@example.test", "+1 (765) 370-0301"),
        ]
        blocked = public_report(build_report(users, []))
        self.assertFalse(blocked["safeToApply"])
        self.assertEqual(len(blocked["duplicates"]), 1)

        cleared = public_report(build_report(users, [], clear_emails=["two@example.test"]))
        self.assertTrue(cleared["safeToApply"])
        cleared_change = next(change for change in cleared["accountChanges"] if change["email"] == "two@example.test")
        self.assertEqual(cleared_change["to"], "")


if __name__ == "__main__":
    unittest.main()
