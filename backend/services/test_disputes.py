import unittest
from types import SimpleNamespace

from backend.routers.disputes import _cached_interpretation_is_current


class CachedInterpretationTests(unittest.TestCase):
    def setUp(self):
        self.interpretation = {"summary": "Supported by the current evidence."}
        self.calculation = SimpleNamespace(
            result={
                "complete": True,
                "invoice_total": "90.00",
                "evidence_high_watermark": 10,
                "traditional_evidence_high_watermark": 2,
            }
        )
        self.analysis = SimpleNamespace(
            agent_status="complete",
            agent_interpretation=self.interpretation,
        )

    def test_reuses_interpretation_when_evidence_and_calculation_match(self):
        result = _cached_interpretation_is_current(
            self.calculation,
            self.analysis,
            {"complete": True, "invoice_total": "90.00"},
            10,
            2,
        )

        self.assertEqual(result, self.interpretation)

    def test_does_not_reuse_interpretation_after_new_evidence(self):
        result = _cached_interpretation_is_current(
            self.calculation,
            self.analysis,
            {"complete": True, "invoice_total": "90.00"},
            11,
            2,
        )

        self.assertIsNone(result)

    def test_does_not_reuse_interpretation_when_calculation_changes(self):
        result = _cached_interpretation_is_current(
            self.calculation,
            self.analysis,
            {"complete": True, "invoice_total": "91.00"},
            10,
            2,
        )

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
