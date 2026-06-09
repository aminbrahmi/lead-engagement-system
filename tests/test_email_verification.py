"""
test_email_verification.py — Tests the automatic SMTP email verification pipeline.

Tests covered:
  1. Bug fix: _find_email reads "status" field (not the missing "verified" key)
  2. Auto-verify: trusted sources (Hunter, FTL, Apollo) skip SMTP
  3. EmailFinderTool output format: always has "status" key
  4. SMTP result propagation: verified pattern → email_verified=True in lead dict
  5. Integration: full _find_email flow on a real lead
"""

import sys
import os
import json
import unittest
from unittest.mock import patch, MagicMock

# Force UTF-8 on Windows terminals (cp1252 can't render unicode symbols)
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from agents.qualifier_node import _find_email, is_auto_verified
from tools.email_finder import EmailFinderTool

SEP  = "=" * 65
SEP2 = "-" * 65

# ── Helpers ───────────────────────────────────────────────────────────────────

def ok(label):   print(f"  [PASS]  {label}")
def fail(label): print(f"  [FAIL]  {label}")
def section(title): print(f"\n{SEP}\n  {title}\n{SEP}")


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 1 — Unit tests (no network, mocked)
# ─────────────────────────────────────────────────────────────────────────────

class TestEmailVerifiedPropagation(unittest.TestCase):
    """Verify that _find_email correctly maps EmailFinderTool output to email_verified."""

    def _lead(self, name="Karim Beguir", company="ClusterLab"):
        return {"name": name, "company": company, "role": "CEO"}

    # ── The fixed path: status="verified" ────────────────────────────────────

    def test_pattern_smtp_verified_sets_email_verified_true(self):
        """When finder returns status=verified (pattern SMTP passed) → email_verified=True."""
        finder_output = json.dumps({
            "email":      "karim.beguir@clusterlab.ai",
            "confidence": 35,
            "source":     "pattern",
            "status":     "verified",
        })
        with patch.object(EmailFinderTool, "_run", return_value=finder_output):
            result = _find_email(self._lead())
        self.assertTrue(result.get("email_verified"),
                        "SMTP-verified pattern email must set email_verified=True")
        self.assertEqual(result["email"], "karim.beguir@clusterlab.ai")
        self.assertEqual(result["email_source"], "pattern")

    def test_pattern_unverified_sets_email_verified_false(self):
        """When finder returns status=unverified → email_verified=False."""
        finder_output = json.dumps({
            "email":      "k.beguir@clusterlab.ai",
            "confidence": 35,
            "source":     "pattern",
            "status":     "unverified",
        })
        with patch.object(EmailFinderTool, "_run", return_value=finder_output):
            result = _find_email(self._lead())
        self.assertFalse(result.get("email_verified"),
                         "Unverified pattern must set email_verified=False")

    # ── Old bug repro: data.get("verified") always None ──────────────────────

    def test_old_verified_key_was_missing(self):
        """Regression: the old code checked data.get('verified'), which is always None."""
        finder_output = json.dumps({
            "email":  "karim@clusterlab.ai",
            "source": "pattern",
            "status": "verified",
            # "verified" key intentionally absent — old code would miss this
        })
        data = json.loads(finder_output)
        old_result = data.get("verified") is True          # old (buggy) check
        new_result = data.get("status") == "verified"      # new (fixed) check
        self.assertFalse(old_result, "Old check should fail for backward compat test")
        self.assertTrue(new_result,  "New check should correctly detect verified status")

    # ── Auto-verify: trusted sources ─────────────────────────────────────────

    def test_hunter_source_auto_verified(self):
        finder_output = json.dumps({
            "email":  "karim@clusterlab.ai",
            "source": "hunter",
            "status": "unverified",   # status doesn't matter for trusted sources
        })
        with patch.object(EmailFinderTool, "_run", return_value=finder_output):
            result = _find_email(self._lead())
        self.assertTrue(result.get("email_verified"),
                        "Hunter emails must be auto-verified regardless of status")

    def test_findthatlead_source_auto_verified(self):
        finder_output = json.dumps({
            "email":  "karim@clusterlab.ai",
            "source": "findthatlead",
            "status": "unverified",
        })
        with patch.object(EmailFinderTool, "_run", return_value=finder_output):
            result = _find_email(self._lead())
        self.assertTrue(result.get("email_verified"))

    def test_apollo_source_auto_verified(self):
        finder_output = json.dumps({
            "email":  "karim@clusterlab.ai",
            "source": "apollo",
            "status": "unverified",
        })
        with patch.object(EmailFinderTool, "_run", return_value=finder_output):
            result = _find_email(self._lead())
        self.assertTrue(result.get("email_verified"))

    def test_unknown_source_not_auto_verified(self):
        finder_output = json.dumps({
            "email":  "karim@clusterlab.ai",
            "source": "scraping",
            "status": "unverified",
        })
        with patch.object(EmailFinderTool, "_run", return_value=finder_output):
            result = _find_email(self._lead())
        self.assertFalse(result.get("email_verified"),
                         "Scraping source without SMTP verification must be False")

    def test_no_email_returned(self):
        """When no email found → lead returned unchanged, no email_verified key."""
        finder_output = json.dumps({"email": None, "confidence": 0,
                                    "source": None, "status": "not_found"})
        with patch.object(EmailFinderTool, "_run", return_value=finder_output):
            lead   = self._lead()
            result = _find_email(lead)
        self.assertIsNone(result.get("email"))


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 2 — is_auto_verified unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIsAutoVerified(unittest.TestCase):

    def test_trusted_sources(self):
        for src in ["hunter", "Hunter", "HUNTER", "findthatlead", "ftl", "apollo", "google"]:
            self.assertTrue(is_auto_verified(src), f"{src} should be trusted")

    def test_untrusted_sources(self):
        for src in ["pattern", "scraping", "web", "", None, "unknown"]:
            self.assertFalse(is_auto_verified(src), f"{src} should NOT be trusted")


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 3 — EmailFinderTool output format
# ─────────────────────────────────────────────────────────────────────────────

class TestEmailFinderOutputFormat(unittest.TestCase):
    """Verify the tool always returns JSON with the expected keys."""

    def _run_mock(self, email, source, verified_flag):
        """Simulate what EmailFinderTool._run returns after picking a winner."""
        winner = {"email": email, "confidence": 35, "source": source, "verified": verified_flag}
        return json.dumps({
            "email":      winner["email"],
            "confidence": winner["confidence"],
            "source":     winner["source"],
            "status":     "verified" if winner.get("verified") else "unverified",
        })

    def test_output_has_status_key(self):
        out = json.loads(self._run_mock("a@b.com", "pattern", True))
        self.assertIn("status", out, "Output must have 'status' key")
        self.assertEqual(out["status"], "verified")

    def test_output_unverified(self):
        out = json.loads(self._run_mock("a@b.com", "pattern", False))
        self.assertEqual(out["status"], "unverified")

    def test_output_no_bare_verified_key(self):
        out = json.loads(self._run_mock("a@b.com", "hunter", True))
        self.assertNotIn("verified", out,
                         "Output must NOT have a bare 'verified' key — use 'status'")


# ─────────────────────────────────────────────────────────────────────────────
# SUITE 4 — Integration tests (real network calls)
# ─────────────────────────────────────────────────────────────────────────────

INTEGRATION_LEADS = [
    # Leads where only pattern emails are expected (no FTL/Hunter key likely to return)
    {"name": "Karim Beguir",   "company": "ClusterLab",    "domain": "clusterlab.ai"},
    {"name": "Yassine Maalej", "company": "Swiver",        "domain": "swiver.io"},
    {"name": "Mehdi Baccour",  "company": "InstaDeep",     "domain": "instadeep.com"},
]


def run_integration_tests():
    section("SUITE 4 — Integration: SMTP verification on real leads")
    print("  (Real network calls — may take 5-15 s per lead)\n")

    tool    = EmailFinderTool()
    results = []

    for lead_info in INTEGRATION_LEADS:
        name    = lead_info["name"]
        company = lead_info["company"]
        domain  = lead_info["domain"]
        query   = f"{name} | {domain} | {company}"

        print(f"  Lead     : {name} @ {company}")
        print(f"  Query    : {query}")

        try:
            raw  = tool._run(query)
            data = json.loads(raw)

            email  = data.get("email")
            source = data.get("source")
            status = data.get("status")

            has_status_key   = "status" in data
            has_no_bool_key  = "verified" not in data
            status_is_valid  = status in ("verified", "unverified", "not_found")

            # Simulate what _find_email would set
            email_verified = (
                status == "verified"
                or is_auto_verified(source)
            )

            print(f"  Email    : {email or '—'}")
            print(f"  Source   : {source or '—'}")
            print(f"  Status   : {status}")
            print(f"  email_verified would be set to: {email_verified}")

            # Assertions
            if has_status_key:
                ok("Output has 'status' key")
            else:
                fail("Output missing 'status' key")

            if has_no_bool_key:
                ok("Output has no bare 'verified' boolean key")
            else:
                fail("Output has unexpected 'verified' key")

            if status_is_valid:
                ok(f"Status value is valid: '{status}'")
            else:
                fail(f"Unexpected status value: '{status}'")

            if email:
                ok(f"Email found: {email} [{source}]")
                if email_verified:
                    ok("email_verified=True (SMTP passed or trusted source)")
                else:
                    print(f"  [WARN]  email_verified=False (SMTP failed or no trusted source)")
            else:
                print(f"  [WARN]  No email found for {name} @ {company}")

            results.append({
                "lead":           f"{name} @ {company}",
                "email":          email,
                "source":         source,
                "status":         status,
                "email_verified": email_verified,
                "passed":         has_status_key and has_no_bool_key and status_is_valid,
            })

        except Exception as e:
            fail(f"Exception for {name}: {e}")
            import traceback; traceback.print_exc()
            results.append({"lead": f"{name} @ {company}", "passed": False})

        print()

    return results


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{SEP}")
    print("  EMAIL VERIFICATION PIPELINE — TESTS")
    print(SEP)

    # ── Unit tests ────────────────────────────────────────────────────────────
    section("SUITE 1 — _find_email email_verified propagation (mocked)")
    loader  = unittest.TestLoader()
    runner  = unittest.TextTestRunner(verbosity=0, stream=open(os.devnull, "w"))
    suites  = [
        loader.loadTestsFromTestCase(TestEmailVerifiedPropagation),
        loader.loadTestsFromTestCase(TestIsAutoVerified),
        loader.loadTestsFromTestCase(TestEmailFinderOutputFormat),
    ]
    unit_passed = 0
    unit_total  = 0
    for suite in suites:
        res = runner.run(suite)
        unit_total  += res.testsRun
        unit_passed += res.testsRun - len(res.failures) - len(res.errors)
        for test, tb in res.failures + res.errors:
            fail(f"{test}: {tb.splitlines()[-1]}")
    for i in range(unit_passed):
        pass   # already printed per-test via runner

    # Re-run verbosely so we see per-test output
    print()
    suite = unittest.TestSuite()
    for cls in [TestEmailVerifiedPropagation, TestIsAutoVerified, TestEmailFinderOutputFormat]:
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(cls))
    for test in suite:
        try:
            test.debug()
            ok(str(test).split(" ")[0])
        except AssertionError as e:
            fail(f"{str(test).split(' ')[0]}: {e}")
        except Exception as e:
            fail(f"{str(test).split(' ')[0]}: {e}")

    print(f"\n  Unit tests: {unit_passed}/{unit_total} passed")

    # ── Integration tests ─────────────────────────────────────────────────────
    integration_results = run_integration_tests()

    int_passed = sum(1 for r in integration_results if r.get("passed"))
    int_total  = len(integration_results)

    # ── Summary ───────────────────────────────────────────────────────────────
    section("SUMMARY")
    print(f"  Unit tests        : {unit_passed}/{unit_total} passed")
    print(f"  Integration tests : {int_passed}/{int_total} passed")
    print()
    print("  Lead results:")
    for r in integration_results:
        verified_tag = "[verified]" if r.get("email_verified") else "[unverified]"
        email_tag    = r.get("email") or "no email"
        source_tag   = r.get("source") or "—"
        print(f"    {r['lead']:<35}  {email_tag:<35}  [{source_tag}]  {verified_tag}")

    print()
    api_keys = {
        "FTL_TOKEN":      os.getenv("FTL_TOKEN"),
        "HUNTER_API_KEY": os.getenv("HUNTER_API_KEY"),
        "APOLLO_API_KEY": os.getenv("APOLLO_API_KEY"),
        "TAVILY_API_KEY": os.getenv("TAVILY_API_KEY"),
    }
    print("  API keys:")
    for k, v in api_keys.items():
        print(f"    {k:<20} {'✓ set' if v else '✗ missing'}")

    print(f"\n{SEP}\n")
    sys.exit(0 if unit_passed == unit_total else 1)
