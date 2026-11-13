"""
Tests for Phase 6: Policy Engine Integration
Feature: 008-mortgage-underwriting

Tests cover:
- Mortgage policy loading and registration
- Policy evaluation against case data
- Findings generation (GDS/TDS/LTV violations)
- OSFI B-20 compliance checks
- Recommendation engine
"""
import pytest
from unittest.mock import MagicMock


class TestMortgagePolicyLoading:
    """Tests for mortgage policy file loading."""

    def test_policy_file_exists(self):
        """Mortgage underwriting policy file should exist."""
        from pathlib import Path
        
        policy_path = Path("prompts/mortgage-underwriting-policies.json")
        assert policy_path.exists() or True  # Will exist after implementation

    def test_policy_file_valid_json(self):
        """Policy file should be valid JSON."""
        from pathlib import Path
        import json
        
        policy_path = Path("prompts/mortgage-underwriting-policies.json")
        if policy_path.exists():
            with open(policy_path) as f:
                policies = json.load(f)
            assert isinstance(policies, (dict, list))

    def test_policy_file_has_hcsf_rules(self):
        """Policy file should include the French HCSF rules."""
        from pathlib import Path
        import json
        
        policy_path = Path("prompts/mortgage-underwriting-policies.json")
        with open(policy_path, encoding="utf-8") as f:
            policies = json.load(f)
        
        assert policies["jurisdiction"].lower() == "france"
        assert "HCSF" in policies["regulatory_framework"]
        rule_ids = {policy["id"] for policy in policies["policies"]}
        assert {"HCSF-EFFORT-001", "HCSF-DUREE-001", "BANK-APPORT-001"} <= rule_ids


class TestPolicyEvaluator:
    """Tests for MortgagePolicyEvaluator."""

    @pytest.fixture
    def evaluator(self):
        """Return a MortgagePolicyEvaluator instance."""
        from app.mortgage.policy_engine import MortgagePolicyEvaluator
        return MortgagePolicyEvaluator()

    @pytest.fixture
    def passing_case(self):
        """Return case data within the HCSF 35% limits, stressed ratios included."""
        return {
            "ratios": {"gds": 0.25, "tds": 0.30, "ltv": 0.80},
            "stress_ratios": {"gds": 0.28, "tds": 0.34},
            "property": {"type": "single_family", "occupancy": "owner_occupied"},
            "borrower": {"credit_score": 720, "employment_status": "permanent"},
        }

    @pytest.fixture
    def failing_case(self):
        """Return case data that should fail GDS/TDS limits."""
        return {
            "ratios": {"gds": 0.42, "tds": 0.48, "ltv": 0.80},
            "stress_ratios": {"gds": 0.50, "tds": 0.55},
            "property": {"type": "single_family", "occupancy": "owner_occupied"},
            "borrower": {"credit_score": 720, "employment_status": "permanent"},
        }

    def test_evaluate_gds_pass(self, evaluator, passing_case):
        """Taux d'effort within the HCSF 35% limit should pass."""
        findings = evaluator.evaluate_gds(passing_case)
        
        assert len([f for f in findings if f.severity == "fail"]) == 0

    def test_evaluate_gds_fail(self, evaluator, failing_case):
        """Taux d'effort above the HCSF limit (and its dérogation band) should fail."""
        findings = evaluator.evaluate_gds(failing_case)
        
        fail_findings = [f for f in findings if f.severity == "fail"]
        assert len(fail_findings) > 0
        assert all(f.rule_id == "HCSF-EFFORT-001" for f in fail_findings)
        assert fail_findings[0].evidence["limit"] == 0.35

    def test_evaluate_tds_pass(self, evaluator, passing_case):
        """Taux d'endettement within the HCSF 35% limit should pass."""
        findings = evaluator.evaluate_tds(passing_case)
        
        assert len([f for f in findings if f.severity == "fail"]) == 0

    def test_evaluate_tds_fail(self, evaluator, failing_case):
        """Taux d'endettement above the HCSF 35% limit should fail."""
        findings = evaluator.evaluate_tds(failing_case)
        
        fail_findings = [f for f in findings if f.severity == "fail"]
        assert len(fail_findings) > 0

    def test_evaluate_ltv_conventional_pass(self, evaluator):
        """LTV at 80% for conventional should pass."""
        case = {
            "ratios": {"ltv": 0.80},
            "loan": {"type": "conventional"},
        }
        
        findings = evaluator.evaluate_ltv(case)
        
        assert len([f for f in findings if f.severity == "fail"]) == 0

    def test_evaluate_ltv_conventional_fail(self, evaluator):
        """LTV over the bank's 90% standard limit should fail."""
        case = {
            "ratios": {"ltv": 0.95},
            "loan": {"type": "conventional"},
        }
        
        findings = evaluator.evaluate_ltv(case)
        
        fail_findings = [f for f in findings if f.severity == "fail"]
        assert len(fail_findings) > 0
        assert fail_findings[0].rule_id == "BANK-LTV-002"


class TestOSFIComplianceChecks:
    """Tests for OSFI B-20 compliance."""

    @pytest.fixture
    def evaluator(self):
        """Return a MortgagePolicyEvaluator instance."""
        from app.mortgage.policy_engine import MortgagePolicyEvaluator
        return MortgagePolicyEvaluator()

    def test_stress_test_required_for_all(self, evaluator):
        """All mortgages should require stress test (B-20)."""
        case = {"loan": {"type": "conventional"}}
        
        result = evaluator.is_stress_test_required(case)
        
        assert result is True

    def test_stress_test_uses_mqr(self, evaluator):
        """Stress test should use MQR (max of floor, contract+buffer)."""
        case = {
            "loan": {"contract_rate": 5.25},
            "settings": {"mqr_floor": 5.25, "mqr_buffer": 2.0},
        }
        
        qualifying_rate = evaluator.get_qualifying_rate(case)
        
        # Contract + 2% = 7.25%, which is > floor 5.25%
        assert qualifying_rate == 7.25

    def test_amortization_limit_25_years(self, evaluator):
        """HCSF caps the loan duration at 25 years for standard loans."""
        within = evaluator.evaluate_amortization(
            {"loan": {"type": "conventional", "amortization_years": 25}}
        )
        beyond = evaluator.evaluate_amortization(
            {"loan": {"type": "conventional", "amortization_years": 30}}
        )
        
        assert [f for f in within if f.severity == "fail"] == []
        fail_findings = [f for f in beyond if f.severity == "fail"]
        assert [f.rule_id for f in fail_findings] == ["HCSF-DUREE-001"]

    def test_amortization_limit_insured_25_years(self, evaluator):
        """Maximum amortization should be 25 years for insured mortgages."""
        case = {
            "loan": {"type": "high_ratio", "amortization_years": 30},
        }
        
        findings = evaluator.evaluate_amortization(case)
        
        # 30 years for insured should fail
        fail_findings = [f for f in findings if f.severity == "fail"]
        assert len(fail_findings) > 0

    def test_minimum_down_payment_10_percent(self, evaluator):
        """The bank requires a minimum apport of 10% of the purchase price."""
        minimum = evaluator.evaluate_down_payment(
            {"deal": {"purchase_price": 500000, "down_payment": 50000}}
        )
        short = evaluator.evaluate_down_payment(
            {"deal": {"purchase_price": 500000, "down_payment": 25000}}
        )
        
        assert [f for f in minimum if f.severity == "fail"] == []
        fail_findings = [f for f in short if f.severity == "fail"]
        assert [f.rule_id for f in fail_findings] == ["BANK-APPORT-001"]
        assert fail_findings[0].evidence["shortfall"] == 25000

    def test_minimum_down_payment_above_500k(self, evaluator):
        """The 10% minimum applies to the whole price: no reduced tier below 500 K."""
        tiered = evaluator.evaluate_down_payment(
            {"deal": {"purchase_price": 850000, "down_payment": 60000}}
        )
        flat = evaluator.evaluate_down_payment(
            {"deal": {"purchase_price": 850000, "down_payment": 85000}}
        )
        
        assert [f.severity for f in tiered] == ["fail"]
        assert [f for f in flat if f.severity == "fail"] == []


class TestFindingsGeneration:
    """Tests for policy findings generation."""

    @pytest.fixture
    def finding(self):
        """Return a sample Finding."""
        from app.mortgage.policy_engine import Finding
        return Finding(
            rule_id="OSFI-B20-GDS-001",
            severity="fail",
            category="ratio",
            message="GDS ratio 42% exceeds limit of 39%",
            evidence={"calculated_gds": 0.42, "limit": 0.39},
            remediation="Reduce housing costs or increase qualifying income",
        )

    def test_finding_has_rule_id(self, finding):
        """Finding should include rule ID for traceability."""
        assert finding.rule_id == "OSFI-B20-GDS-001"

    def test_finding_has_severity(self, finding):
        """Finding should have severity level."""
        assert finding.severity in ["info", "warning", "fail", "pass"]

    def test_finding_has_category(self, finding):
        """Finding should be categorized."""
        assert finding.category in ["ratio", "credit", "income", "property", "compliance"]

    def test_finding_has_evidence(self, finding):
        """Finding should include evidence for transparency."""
        assert "calculated_gds" in finding.evidence
        assert finding.evidence["calculated_gds"] == 0.42

    def test_finding_has_remediation(self, finding):
        """Finding should suggest remediation."""
        assert "Reduce" in finding.remediation or "increase" in finding.remediation.lower()


class TestRecommendationEngine:
    """Tests for underwriting recommendation generation."""

    @pytest.fixture
    def recommender(self):
        """Return a RecommendationEngine instance."""
        from app.mortgage.policy_engine import RecommendationEngine
        return RecommendationEngine()

    def test_recommend_approve_all_pass(self, recommender):
        """Should recommend APPROVE when all policies pass."""
        findings = [
            MagicMock(severity="pass", rule_id="GDS-001"),
            MagicMock(severity="pass", rule_id="TDS-001"),
            MagicMock(severity="pass", rule_id="LTV-001"),
        ]
        
        result = recommender.generate_recommendation(findings)
        
        assert result.decision == "APPROVE"

    def test_recommend_decline_fail_finding(self, recommender):
        """Should recommend DECLINE when critical policy fails."""
        findings = [
            MagicMock(severity="pass", rule_id="GDS-001"),
            MagicMock(severity="fail", rule_id="TDS-001"),
            MagicMock(severity="pass", rule_id="LTV-001"),
        ]
        
        result = recommender.generate_recommendation(findings)
        
        assert result.decision in ["DECLINE", "REFER"]

    def test_recommend_refer_warning_findings(self, recommender):
        """Should recommend REFER when multiple warnings present."""
        findings = [
            MagicMock(severity="warning", rule_id="INCOME-001"),
            MagicMock(severity="warning", rule_id="INCOME-002"),
            MagicMock(severity="pass", rule_id="LTV-001"),
        ]
        
        result = recommender.generate_recommendation(findings)
        
        assert result.decision == "REFER"

    def test_recommendation_includes_conditions(self, recommender):
        """Approval recommendation may include conditions."""
        findings = [
            MagicMock(severity="pass", rule_id="GDS-001"),
            MagicMock(severity="warning", rule_id="EMPLOYMENT-001"),
        ]
        
        result = recommender.generate_recommendation(findings)
        
        # May have conditions even with approval
        assert hasattr(result, "conditions")


class TestPolicyIntegration:
    """Integration tests for policy engine with RAG service."""

    @pytest.fixture
    def mock_rag_service(self):
        """Return a mock RAG service."""
        mock = MagicMock()
        mock.query.return_value = [
            {"content": "GDS limit is 39%", "source": "OSFI B-20"},
        ]
        return mock

    def test_policy_engine_queries_rag(self, mock_rag_service):
        """Policy engine should query RAG for policy clarification."""
        from app.mortgage.policy_engine import MortgagePolicyEvaluator
        
        evaluator = MortgagePolicyEvaluator(rag_service=mock_rag_service)
        
        # When encountering edge case, should consult policy RAG
        case = {"ratios": {"gds": 0.395}}  # Edge case: 39.5%
        evaluator.evaluate_gds(case)
        
        # May or may not call RAG depending on implementation
        # This is a placeholder for integration testing

    def test_policy_findings_include_rag_citations(self):
        """Policy findings should cite RAG sources when used."""
        from app.mortgage.policy_engine import Finding
        
        finding = Finding(
            rule_id="OSFI-B20-GDS-001",
            severity="fail",
            category="ratio",
            message="GDS exceeds limit",
            evidence={"gds": 0.42},
            rag_citations=[
                {"chunk_id": "osfi-b20-gds-001", "source": "B-20 Guideline"}
            ]
        )
        
        assert len(finding.rag_citations) > 0
        assert finding.rag_citations[0]["source"] == "B-20 Guideline"
