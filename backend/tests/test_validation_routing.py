"""Unit tests for Invoice Validation and Confidence-Based Routing (Step 13).

Covers:
1. Rule 1: Vendor Name validation (presence, non-empty)
2. Rule 2: Invoice Number validation (presence, non-empty)
3. Rule 3: Invoice Date validation (presence, calendar validity)
4. Rule 4: Total Amount validation (presence, numeric, strictly > 0)
5. Full invoice validation and field error mapping
6. Confidence computation (weighted composite scoring)
7. Confidence-based routing (VERIFIED vs. NEEDS_REVIEW with human review reasons)
8. Threshold customization and boundary conditions
"""

import datetime
from decimal import Decimal
import pytest

from app.core.config import settings
from app.schemas.validation import (
    ConfidenceEvaluationResult,
    FieldConfidenceInfo,
    RoutingDecision,
    RoutingStatus,
    ValidationResult,
)
from app.services.confidence import (
    ConfidenceRouter,
    ConfidenceService,
    compute_overall_confidence,
    evaluate_and_route,
    evaluate_field_confidences,
    route_invoice,
)
from app.services.validator import (
    InvoiceValidator,
    validate_invoice,
    validate_invoice_date,
    validate_invoice_number,
    validate_total_amount,
    validate_vendor_name,
)


class TestInvoiceValidationRules:
    """Test suite for individual invoice validation rules."""

    # ---------------------------------------------------------
    # Rule 1: Vendor Name
    # ---------------------------------------------------------
    @pytest.mark.parametrize(
        "valid_vendor",
        [
            "ABC Technologies Pvt Ltd",
            "Acme Corp",
            "Reliance Retail Limited",
            "Tata Consultancy Services",
        ],
    )
    def test_vendor_name_valid(self, valid_vendor: str):
        ok, err = validate_vendor_name(valid_vendor)
        assert ok is True
        assert err is None

    @pytest.mark.parametrize(
        "invalid_vendor",
        [
            None,
            "",
            "   ",
            "\t\n",
        ],
    )
    def test_vendor_name_invalid(self, invalid_vendor):
        ok, err = validate_vendor_name(invalid_vendor)
        assert ok is False
        assert err == "Vendor Name is required"

    # ---------------------------------------------------------
    # Rule 2: Invoice Number
    # ---------------------------------------------------------
    @pytest.mark.parametrize(
        "valid_number",
        [
            "INV-2026-00125",
            "INV/2026/998",
            "100234",
            "BILL-001-A",
        ],
    )
    def test_invoice_number_valid(self, valid_number: str):
        ok, err = validate_invoice_number(valid_number)
        assert ok is True
        assert err is None

    @pytest.mark.parametrize(
        "invalid_number",
        [
            None,
            "",
            "   ",
            "\n",
        ],
    )
    def test_invoice_number_invalid(self, invalid_number):
        ok, err = validate_invoice_number(invalid_number)
        assert ok is False
        assert err == "Invoice Number is required"

    # ---------------------------------------------------------
    # Rule 3: Invoice Date
    # ---------------------------------------------------------
    @pytest.mark.parametrize(
        "valid_date",
        [
            "2026-09-05",
            "2025-01-31",
            "2024-02-29",  # Leap year
            datetime.date(2026, 9, 5),
            "05/09/2026",
            "05-09-2026",
        ],
    )
    def test_invoice_date_valid(self, valid_date):
        ok, err = validate_invoice_date(valid_date)
        assert ok is True
        assert err is None

    @pytest.mark.parametrize(
        "missing_date",
        [
            None,
            "",
            "   ",
        ],
    )
    def test_invoice_date_missing(self, missing_date):
        ok, err = validate_invoice_date(missing_date)
        assert ok is False
        assert err == "Invoice Date is required"

    @pytest.mark.parametrize(
        "invalid_calendar_date",
        [
            "2026-02-30",  # Feb 30 does not exist
            "2026-02-29",  # 2026 is not a leap year
            "99/99/2026",
            "not a date",
            "2026-13-01",  # Month 13
        ],
    )
    def test_invoice_date_invalid_calendar(self, invalid_calendar_date: str):
        ok, err = validate_invoice_date(invalid_calendar_date)
        assert ok is False
        assert "Invoice Date is invalid" in err

    # ---------------------------------------------------------
    # Rule 4: Total Amount
    # ---------------------------------------------------------
    @pytest.mark.parametrize(
        "valid_amount",
        [
            "25500.00",
            "25,500.00",
            "₹25,500.00",
            "Rs. 25500.50",
            25500.00,
            Decimal("25500.00"),
            "1.00",
            "0.01",
        ],
    )
    def test_total_amount_valid(self, valid_amount):
        ok, err = validate_total_amount(valid_amount)
        assert ok is True
        assert err is None

    @pytest.mark.parametrize(
        "missing_amount",
        [
            None,
            "",
            "   ",
        ],
    )
    def test_total_amount_missing(self, missing_amount):
        ok, err = validate_total_amount(missing_amount)
        assert ok is False
        assert err == "Total Amount is required"

    @pytest.mark.parametrize(
        "zero_or_negative_amount",
        [
            "0",
            "0.00",
            0,
            0.0,
            "-500.00",
            "-0.01",
            Decimal("-500.00"),
            Decimal("0.00"),
        ],
    )
    def test_total_amount_must_be_strictly_positive(self, zero_or_negative_amount):
        ok, err = validate_total_amount(zero_or_negative_amount)
        assert ok is False
        assert err == "Total Amount must be greater than 0"

    def test_total_amount_non_numeric(self):
        ok, err = validate_total_amount("abc")
        assert ok is False
        assert "Total Amount must be a valid number" in err


class TestFullInvoiceValidation:
    """Test suite for full invoice validation orchestration."""

    def test_valid_invoice(self):
        invoice_data = {
            "vendor_name": "ABC Technologies Pvt Ltd",
            "invoice_number": "INV-2026-00125",
            "invoice_date": "2026-09-05",
            "total_amount": "25500.00",
        }
        res = validate_invoice(invoice_data)
        assert isinstance(res, ValidationResult)
        assert res.is_valid is True
        assert len(res.errors) == 0
        assert len(res.field_errors) == 0

    def test_missing_vendor_invoice(self):
        invoice_data = {
            "vendor_name": None,
            "invoice_number": "INV-2026-00125",
            "invoice_date": "2026-09-05",
            "total_amount": "25500.00",
        }
        res = validate_invoice(invoice_data)
        assert res.is_valid is False
        assert "Vendor Name is required" in res.errors
        assert res.field_errors["vendor_name"] == "Vendor Name is required"

    def test_multiple_validation_failures(self):
        invoice_data = {
            "vendor_name": "",
            "invoice_number": "INV-001",
            "invoice_date": "2026-02-30",
            "total_amount": "-500.00",
        }
        res = validate_invoice(invoice_data)
        assert res.is_valid is False
        assert len(res.errors) == 3
        assert "vendor_name" in res.field_errors
        assert "invoice_date" in res.field_errors
        assert "total_amount" in res.field_errors

    def test_class_and_instance_calls(self):
        validator = InvoiceValidator()
        res1 = validator.validate_invoice(
            vendor_name="Acme",
            invoice_number="INV-1",
            invoice_date="2026-09-05",
            total_amount="100.00",
        )
        assert res1.is_valid is True

        res2 = InvoiceValidator.validate_invoice(
            vendor_name="Acme",
            invoice_number="INV-1",
            invoice_date="2026-09-05",
            total_amount="100.00",
        )
        assert res2.is_valid is True


class TestConfidenceBasedRouting:
    """Test suite for confidence evaluation and routing decisions."""

    def test_verified_routing(self):
        """All validation passes and all confidences exceed threshold -> VERIFIED."""
        val_res = ValidationResult(is_valid=True, errors=[], field_errors={})
        confidences = {
            "vendor_name": 0.95,
            "invoice_number": 0.92,
            "invoice_date": 0.90,
            "total_amount": 0.88,
        }

        decision = evaluate_and_route(val_res, confidences)
        assert isinstance(decision, RoutingDecision)
        assert decision.status == RoutingStatus.VERIFIED
        assert decision.is_valid is True
        assert decision.overall_confidence >= 0.85
        assert len(decision.review_reasons) == 0

    def test_needs_review_due_to_validation_failure(self):
        """Even with 1.0 confidence, any validation failure routes to NEEDS_REVIEW."""
        val_res = ValidationResult(
            is_valid=False,
            errors=["Invoice Date is required"],
            field_errors={"invoice_date": "Invoice Date is required"},
        )
        confidences = {
            "vendor_name": 1.0,
            "invoice_number": 1.0,
            "invoice_date": 0.0,
            "total_amount": 1.0,
        }

        decision = evaluate_and_route(val_res, confidences)
        assert decision.status == RoutingStatus.NEEDS_REVIEW
        assert decision.is_valid is False
        assert "Invoice Date is required" in decision.review_reasons

    def test_needs_review_due_to_low_overall_confidence(self):
        """Valid invoice with overall confidence below 0.85 routes to NEEDS_REVIEW."""
        val_res = ValidationResult(is_valid=True, errors=[], field_errors={})
        # Average = 0.75 < 0.85 threshold
        confidences = {
            "vendor_name": 0.75,
            "invoice_number": 0.75,
            "invoice_date": 0.75,
            "total_amount": 0.75,
        }

        decision = evaluate_and_route(val_res, confidences, overall_threshold=0.85)
        assert decision.status == RoutingStatus.NEEDS_REVIEW
        assert decision.is_valid is True
        assert any("Overall confidence" in r for r in decision.review_reasons)

    def test_needs_review_due_to_single_low_field_confidence(self):
        """High overall average but one field below min floor (0.70) routes to NEEDS_REVIEW."""
        val_res = ValidationResult(is_valid=True, errors=[], field_errors={})
        confidences = {
            "vendor_name": 0.98,
            "invoice_number": 0.60,  # Below 0.70
            "invoice_date": 0.95,
            "total_amount": 0.95,
        }

        decision = evaluate_and_route(val_res, confidences, min_field_threshold=0.70)
        assert decision.status == RoutingStatus.NEEDS_REVIEW
        assert any("Invoice Number" in r and "below threshold" in r for r in decision.review_reasons)

    def test_custom_thresholds(self):
        """Customizing threshold allows tailoring straight-through processing."""
        val_res = ValidationResult(is_valid=True, errors=[], field_errors={})
        confidences = {
            "vendor_name": 0.80,
            "invoice_number": 0.80,
            "invoice_date": 0.80,
            "total_amount": 0.80,
        }

        # With default 0.85 threshold -> NEEDS_REVIEW
        default_decision = evaluate_and_route(val_res, confidences, overall_threshold=0.85)
        assert default_decision.status == RoutingStatus.NEEDS_REVIEW

        # With relaxed 0.75 threshold -> VERIFIED
        relaxed_decision = evaluate_and_route(val_res, confidences, overall_threshold=0.75, min_field_threshold=0.70)
        assert relaxed_decision.status == RoutingStatus.VERIFIED

    def test_overall_confidence_weighting(self):
        """Verify custom weights in composite confidence calculation."""
        scores = {"vendor_name": 1.0, "invoice_number": 0.0}
        # Equal weights: (1.0 + 0.0) / 2 = 0.50
        assert compute_overall_confidence(scores, weights={"vendor_name": 0.5, "invoice_number": 0.5}) == 0.50
        # Skewed weights: (1.0 * 0.9 + 0.0 * 0.1) = 0.90
        assert compute_overall_confidence(scores, weights={"vendor_name": 0.9, "invoice_number": 0.1}) == 0.90

    def test_routing_decision_to_dict(self):
        val_res = ValidationResult(is_valid=True, errors=[], field_errors={})
        confidences = {
            "vendor_name": 0.95,
            "invoice_number": 0.92,
            "invoice_date": 0.90,
            "total_amount": 0.88,
        }
        decision = ConfidenceRouter.evaluate_and_route(val_res, confidences)
        d = decision.to_dict()
        assert d["status"] == "VERIFIED"
        assert d["is_valid"] is True
        assert "overall_confidence" in d
        assert "field_confidences" in d
        assert d["review_reasons"] == []


class TestFieldLevelConfidence:
    """Test suite for field-level confidence evaluation and boundary rules."""

    @pytest.mark.parametrize(
        "score,expected_meets",
        [
            (0.90, True),
            (0.85, True),    # Exact threshold: 0.85 >= 0.85 MUST pass
            (0.8500, True),
            (0.849, False),  # 0.849 MUST fail
            (0.8499, False),
            (0.70, False),
            (0.0, False),
        ],
    )
    def test_confidence_boundary_strictly_greater_or_equal(self, score: float, expected_meets: bool):
        """Verify strict comparison: confidence >= threshold.

        0.85 >= 0.85 PASSES.
        0.849 < 0.85 FAILS.
        """
        input_data = {
            "vendor_name": score,
            "invoice_number": 0.90,
            "invoice_date": 0.90,
            "total_amount": 0.90,
        }
        res = evaluate_field_confidences(input_data, threshold=0.85)
        assert isinstance(res, ConfidenceEvaluationResult)
        assert res.fields["vendor_name"].confidence == round(score, 4)
        assert res.fields["vendor_name"].meets_threshold is expected_meets

    def test_all_required_fields_meet_threshold(self):
        """Verify the exact example from Requirement 8 & 10:

        Input:
        {
            "vendor_name": 0.94,
            "invoice_number": 0.91,
            "invoice_date": 0.88,
            "total_amount": 0.97
        }
        Threshold: 0.85
        Expected: All required fields meet threshold.
        """
        input_data = {
            "vendor_name": 0.94,
            "invoice_number": 0.91,
            "invoice_date": 0.88,
            "total_amount": 0.97,
        }
        res = ConfidenceRouter.evaluate_field_confidences(input_data, threshold=0.85)
        assert res.all_meet_threshold is True
        assert len(res.failing_fields) == 0

        # Verify field-level structure matching requirement 10
        expected_fields = {
            "vendor_name": {"confidence": 0.94, "meets_threshold": True},
            "invoice_number": {"confidence": 0.91, "meets_threshold": True},
            "invoice_date": {"confidence": 0.88, "meets_threshold": True},
            "total_amount": {"confidence": 0.97, "meets_threshold": True},
        }
        for field_name, expected in expected_fields.items():
            field_obj = res.fields[field_name]
            assert isinstance(field_obj, FieldConfidenceInfo)
            assert field_obj.confidence == expected["confidence"]
            assert field_obj.meets_threshold == expected["meets_threshold"]

    def test_failing_field_reporting(self):
        """Verify that a failing field records meets_threshold=False without hiding actual score."""
        input_data = {
            "vendor_name": 0.94,
            "invoice_number": 0.91,
            "invoice_date": 0.88,
            "total_amount": 0.72,  # Failing field
        }
        res = ConfidenceService.evaluate_field_confidences(input_data, threshold=0.85)
        assert res.all_meet_threshold is False
        assert res.failing_fields == ["total_amount"]
        assert res.fields["total_amount"].confidence == 0.72
        assert res.fields["total_amount"].meets_threshold is False

    def test_default_threshold_from_app_settings(self):
        """Verify that threshold defaults to settings.CONFIDENCE_THRESHOLD (0.85)."""
        assert settings.CONFIDENCE_THRESHOLD == 0.85
        assert ConfidenceRouter.get_configured_threshold() == 0.85

        input_data = {
            "vendor_name": 0.85,
            "invoice_number": 0.85,
            "invoice_date": 0.85,
            "total_amount": 0.85,
        }
        # Calling without passing threshold uses configured settings default
        res = evaluate_field_confidences(input_data)
        assert res.threshold == 0.85
        assert res.all_meet_threshold is True

    def test_configurable_threshold_without_code_change(self):
        """Verify that passing different thresholds changes evaluation without code changes."""
        input_data = {
            "vendor_name": 0.80,
            "invoice_number": 0.80,
            "invoice_date": 0.80,
            "total_amount": 0.80,
        }
        # Under strict threshold 0.90: all fail
        strict_res = evaluate_field_confidences(input_data, threshold=0.90)
        assert strict_res.all_meet_threshold is False

        # Under relaxed threshold 0.75: all pass
        relaxed_res = evaluate_field_confidences(input_data, threshold=0.75)
        assert relaxed_res.all_meet_threshold is True


class TestSpecificRoutingScenarios:
    """Exact test cases for Scenarios 1 to 4 specified in the prompt."""

    def test_scenario_1_everything_valid(self):
        """Scenario 1 — Everything valid:

        Vendor Name = "ABC Technologies", Invoice Number = "INV-001"
        Invoice Date = "2026-09-05", Total Amount = 25500.00
        Confidences: 0.95, 0.91, 0.89, 0.97. Threshold: 0.85
        Result: VERIFIED
        """
        invoice_data = {
            "vendor_name": "ABC Technologies",
            "invoice_number": "INV-001",
            "invoice_date": "2026-09-05",
            "total_amount": 25500.00,
        }
        confidences = {
            "vendor_name": 0.95,
            "invoice_number": 0.91,
            "invoice_date": 0.89,
            "total_amount": 0.97,
        }
        decision = route_invoice(invoice_data, confidences, threshold=0.85)
        assert decision.status == RoutingStatus.VERIFIED
        assert decision.status == "VERIFIED"
        assert decision.is_valid is True
        assert len(decision.review_reasons) == 0

    def test_scenario_2_validation_failure(self):
        """Scenario 2 — Validation Failure:

        Vendor Name = "ABC Technologies", Invoice Number = "INV-001"
        Invoice Date = "2026-09-05", Total Amount = 0.00
        Confidence: 0.95, 0.91, 0.89, 0.97
        Result: NEEDS_REVIEW
        Error: Total Amount must be greater than 0
        """
        invoice_data = {
            "vendor_name": "ABC Technologies",
            "invoice_number": "INV-001",
            "invoice_date": "2026-09-05",
            "total_amount": 0.00,
        }
        confidences = {
            "vendor_name": 0.95,
            "invoice_number": 0.91,
            "invoice_date": 0.89,
            "total_amount": 0.97,
        }
        decision = route_invoice(invoice_data, confidences, threshold=0.85)
        assert decision.status == RoutingStatus.NEEDS_REVIEW
        assert decision.status == "NEEDS_REVIEW"
        assert decision.is_valid is False
        assert "Total Amount must be greater than 0" in decision.review_reasons
        assert "Total Amount must be greater than 0" in decision.validation_errors

    def test_scenario_3_confidence_failure(self):
        """Scenario 3 — Confidence Failure:

        Vendor Name = "ABC Technologies", Invoice Number = "INV-001"
        Invoice Date = "2026-09-05", Total Amount = 25500.00
        Confidence:
        Vendor Name = 0.95, Invoice Number = 0.91, Invoice Date = 0.72, Total Amount = 0.97
        Validation passes. But Invoice Date confidence = 0.72 is below 0.85.
        Result: NEEDS_REVIEW
        Error: Invoice Date confidence 0.72 is below threshold 0.85
        """
        invoice_data = {
            "vendor_name": "ABC Technologies",
            "invoice_number": "INV-001",
            "invoice_date": "2026-09-05",
            "total_amount": 25500.00,
        }
        confidences = {
            "vendor_name": 0.95,
            "invoice_number": 0.91,
            "invoice_date": 0.72,
            "total_amount": 0.97,
        }
        decision = route_invoice(invoice_data, confidences, threshold=0.85)
        assert decision.status == RoutingStatus.NEEDS_REVIEW
        assert decision.status == "NEEDS_REVIEW"
        assert decision.is_valid is True
        assert any(
            "Invoice Date confidence 0.72 is below threshold 0.85" in r
            for r in decision.review_reasons
        )

    def test_scenario_4_exactly_85_percent(self):
        """Scenario 4 — Exactly 85%:

        Vendor Name = 0.85, Invoice Number = 0.85, Invoice Date = 0.85, Total Amount = 0.85
        Threshold: 0.85
        Result: VERIFIED (confidence >= threshold)
        """
        invoice_data = {
            "vendor_name": "ABC Technologies",
            "invoice_number": "INV-001",
            "invoice_date": "2026-09-05",
            "total_amount": 25500.00,
        }
        confidences = {
            "vendor_name": 0.85,
            "invoice_number": 0.85,
            "invoice_date": 0.85,
            "total_amount": 0.85,
        }
        decision = route_invoice(invoice_data, confidences, threshold=0.85)
        assert decision.status == RoutingStatus.VERIFIED
        assert decision.status == "VERIFIED"
        assert decision.is_valid is True
        assert len(decision.review_reasons) == 0


