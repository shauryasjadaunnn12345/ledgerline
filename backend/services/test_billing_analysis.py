import unittest
from types import SimpleNamespace

from backend.services.billing_analysis import analyze_billing


def make_evidence(evidence_id, evidence_type, payload):
    return SimpleNamespace(id=evidence_id, evidence_type=evidence_type, payload=payload)


class BillingAnalysisTests(unittest.TestCase):
    def test_usage_priced_line_uses_matching_usage_events(self):
        evidence = [
            make_evidence(1, "invoice_line_item", {
                "line_id": "L1",
                "description": "API usage",
                "quantity": "10",
                "unit_price": "2.00",
                "billed_amount": "20.00",
            }),
            make_evidence(2, "contract_rule", {
                "line_id": "L1",
                "description": "Usage rate",
                "allowed_unit_price": "1.00",
                "quantity_source": "usage",
            }),
            make_evidence(3, "usage_event", {
                "line_id": "L1",
                "description": "Recorded API calls",
                "quantity": "7",
            }),
        ]

        result = analyze_billing(evidence)

        self.assertEqual(result["calculation"]["lines"][0]["expected_amount"], "7.00")
        self.assertEqual(result["calculation"]["lines"][0]["recalculated_quantity"], "7")
        self.assertEqual(result["calculation"]["recalculated_total"], "7.00")

    def test_usage_priced_line_is_unavailable_without_usage_evidence(self):
        evidence = [
            make_evidence(1, "invoice_line_item", {
                "line_id": "L1",
                "description": "API usage",
                "quantity": "10",
                "unit_price": "2.00",
                "billed_amount": "20.00",
            }),
            make_evidence(2, "contract_rule", {
                "line_id": "L1",
                "description": "Usage rate",
                "allowed_unit_price": "1.00",
                "quantity_source": "usage",
            }),
        ]

        result = analyze_billing(evidence)

        self.assertIsNone(result["calculation"]["lines"][0]["expected_amount"])
        self.assertIsNone(result["calculation"]["recalculated_total"])

    def test_invoice_extension_math_is_available_without_contract_rule(self):
        evidence = [make_evidence(1, "invoice_line_item", {
            "line_id": "INV-2026-009-L01",
            "description": "Cloud Storage",
            "quantity": "12",
            "unit_price": "70.00",
            "billed_amount": "839.94",
        })]

        result = analyze_billing(evidence)

        line = result["calculation"]["lines"][0]
        self.assertEqual(line["invoice_calculated_amount"], "840.00")
        self.assertEqual(line["invoice_amount_variance"], "-0.06")
        self.assertEqual(result["calculation"]["invoice_extension_total"], "840.00")
        self.assertIsNone(result["calculation"]["recalculated_total"])
        self.assertTrue(any(
            finding["kind"] == "calculation_error"
            and "rather than the billed amount" in finding["text"]
            for finding in result["findings"]
        ))


if __name__ == "__main__":
    unittest.main()