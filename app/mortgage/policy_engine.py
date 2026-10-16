"""
Mortgage Policy Engine for French HCSF / internal bank rules compliance.

Evaluates mortgage applications against French regulatory policies
(Haut Conseil de Stabilité Financière) and the bank's internal rules,
and generates findings with remediation guidance in French.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from enum import Enum


class Severity(str, Enum):
    """Finding severity levels."""
    PASS = "pass"
    INFO = "info"
    WARNING = "warning"
    FAIL = "fail"


class Category(str, Enum):
    """Finding categories."""
    RATIO = "ratio"
    CREDIT = "credit"
    INCOME = "income"
    PROPERTY = "property"
    COMPLIANCE = "compliance"


class Decision(str, Enum):
    """Underwriting decision types."""
    APPROVE = "APPROVE"
    REFER = "REFER"
    DECLINE = "DECLINE"


# HCSF / internal bank limits
GDS_LIMIT = 0.35  # Taux d'effort HCSF (charges logement / revenus nets)
TDS_LIMIT = 0.35  # Taux d'endettement HCSF (charges totales / revenus nets)
LTV_CONVENTIONAL_MAX = 0.90  # France: financement jusqu'à 90% courant
LTV_INSURED_MAX = 1.00  # France: financement à 100% rare mais possible
AMORTIZATION_INSURED_MAX = 25  # Durée maximum HCSF (années)
AMORTIZATION_UNINSURED_MAX = 25  # Durée maximum HCSF (années)
MQR_FLOOR = 5.25  # legacy (pas de norme officielle en France)
MQR_BUFFER = 1.0  # Sensibilité +1pt taux (pratique de place)

# Types de prêt à fort apport (placeholders pour compat retro)
INSURED_TYPES = {"high_ratio", "pret_amortissable"}


@dataclass
class Finding:
    """
    Policy evaluation finding.
    
    Represents a single policy check result with evidence and remediation.
    """
    rule_id: str
    severity: str  # pass, info, warning, fail
    category: str  # ratio, credit, income, property, compliance
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    remediation: str = ""
    rag_citations: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class Recommendation:
    """
    Underwriting recommendation.
    
    Generated from policy findings with decision and conditions.
    """
    decision: str  # APPROVE, REFER, DECLINE
    confidence: float = 1.0
    reasons: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    findings_summary: Dict[str, int] = field(default_factory=dict)


class MortgagePolicyEvaluator:
    """
    Evaluates mortgage applications against French HCSF and internal bank policies.

    Generates findings for taux d'effort, taux d'endettement, LTV, durée
    et apport personnel.
    """
    
    def __init__(self, rag_service: Optional[Any] = None):
        """
        Initialize policy evaluator.
        
        Args:
            rag_service: Optional RAG service for policy clarification
        """
        self.rag_service = rag_service
    
    def evaluate_gds(self, case: Dict[str, Any]) -> List[Finding]:
        """
        Evaluate Gross Debt Service ratio against limits.
        
        Args:
            case: Case data with ratios.gds
            
        Returns:
            List of findings
        """
        findings = []
        ratios = case.get("ratios", {})
        gds = ratios.get("gds", 0)
        
        # Check stress test GDS if available
        stress_ratios = case.get("stress_ratios", {})
        stress_gds = stress_ratios.get("gds", gds)
        
        # Use stressed GDS for evaluation (OSFI B-20 requirement)
        eval_gds = max(gds, stress_gds)
        
        if eval_gds <= GDS_LIMIT:
            findings.append(Finding(
                rule_id="HCSF-EFFORT-001",
                severity="pass",
                category="ratio",
                message=f"Taux d'effort {eval_gds:.1%} dans la limite HCSF de {GDS_LIMIT:.0%}",
                evidence={"calculated_gds": eval_gds, "calculated_value": eval_gds, "limit": GDS_LIMIT},
            ))
        elif eval_gds <= GDS_LIMIT + 0.03:  # Up to 3% over - warning (dérogation HCSF possible)
            findings.append(Finding(
                rule_id="HCSF-EFFORT-001",
                severity="warning",
                category="ratio",
                message=f"Taux d'effort {eval_gds:.1%} légèrement au-dessus de la limite HCSF de {GDS_LIMIT:.0%} (dérogation possible)",
                evidence={"calculated_gds": eval_gds, "calculated_value": eval_gds, "limit": GDS_LIMIT},
                remediation="Envisager des facteurs compensatoires (apport, épargne résiduelle) ou réduire les charges de logement",
            ))
        else:
            findings.append(Finding(
                rule_id="HCSF-EFFORT-001",
                severity="fail",
                category="ratio",
                message=f"Taux d'effort {eval_gds:.1%} dépasse la limite HCSF de {GDS_LIMIT:.0%}",
                evidence={"calculated_gds": eval_gds, "calculated_value": eval_gds, "limit": GDS_LIMIT},
                remediation="Réduire les charges de logement ou augmenter les revenus pris en compte",
            ))
        
        return findings
    
    def evaluate_tds(self, case: Dict[str, Any]) -> List[Finding]:
        """
        Evaluate Total Debt Service ratio against limits.
        
        Args:
            case: Case data with ratios.tds
            
        Returns:
            List of findings
        """
        findings = []
        ratios = case.get("ratios", {})
        tds = ratios.get("tds", 0)
        
        # Check stress test TDS if available
        stress_ratios = case.get("stress_ratios", {})
        stress_tds = stress_ratios.get("tds", tds)
        
        # Use stressed TDS for evaluation
        eval_tds = max(tds, stress_tds)
        
        if eval_tds <= TDS_LIMIT:
            findings.append(Finding(
                rule_id="HCSF-ENDETT-001",
                severity="pass",
                category="ratio",
                message=f"Taux d'endettement {eval_tds:.1%} dans la limite HCSF de {TDS_LIMIT:.0%}",
                evidence={"calculated_tds": eval_tds, "calculated_value": eval_tds, "limit": TDS_LIMIT},
            ))
        elif eval_tds <= TDS_LIMIT + 0.02:  # Up to 2% over - warning
            findings.append(Finding(
                rule_id="HCSF-ENDETT-001",
                severity="warning",
                category="ratio",
                message=f"Taux d'endettement {eval_tds:.1%} légèrement au-dessus de la limite HCSF de {TDS_LIMIT:.0%} (dérogation possible)",
                evidence={"calculated_tds": eval_tds, "calculated_value": eval_tds, "limit": TDS_LIMIT},
                remediation="Consolider les crédits existants ou augmenter les revenus",
            ))
        else:
            findings.append(Finding(
                rule_id="HCSF-ENDETT-001",
                severity="fail",
                category="ratio",
                message=f"Taux d'endettement {eval_tds:.1%} dépasse la limite HCSF de {TDS_LIMIT:.0%}",
                evidence={"calculated_tds": eval_tds, "calculated_value": eval_tds, "limit": TDS_LIMIT},
                remediation="Réduire les charges d'endettement ou augmenter les revenus pris en compte",
            ))
        
        return findings
    
    def evaluate_ltv(self, case: Dict[str, Any]) -> List[Finding]:
        """
        Evaluate Loan-to-Value ratio against limits.
        
        Args:
            case: Case data with ratios.ltv and loan.type
            
        Returns:
            List of findings
        """
        findings = []
        ratios = case.get("ratios", {})
        ltv = ratios.get("ltv", 0)
        
        loan = case.get("loan", {})
        loan_type = loan.get("type", "conventional").lower()
        is_insured = loan_type in INSURED_TYPES
        
        if is_insured:
            # Prêt à fort LTV (>90%)
            if ltv <= LTV_INSURED_MAX:
                findings.append(Finding(
                    rule_id="BANK-LTV-001",
                    severity="pass",
                    category="ratio",
                    message=f"LTV {ltv:.1%} dans la limite étendue de {LTV_INSURED_MAX:.0%}",
                    evidence={"calculated_ltv": ltv, "calculated_value": ltv, "limit": LTV_INSURED_MAX, "loan_type": loan_type},
                ))
            else:
                findings.append(Finding(
                    rule_id="BANK-LTV-001",
                    severity="fail",
                    category="ratio",
                    message=f"LTV {ltv:.1%} dépasse la limite maximale de {LTV_INSURED_MAX:.0%}",
                    evidence={"calculated_ltv": ltv, "calculated_value": ltv, "limit": LTV_INSURED_MAX, "loan_type": loan_type},
                    remediation="Augmenter l'apport personnel pour ramener le LTV sous le seuil",
                ))
        else:
            # Prêt amortissable standard
            if ltv <= LTV_CONVENTIONAL_MAX:
                findings.append(Finding(
                    rule_id="BANK-LTV-002",
                    severity="pass",
                    category="ratio",
                    message=f"LTV {ltv:.1%} dans la limite standard de {LTV_CONVENTIONAL_MAX:.0%}",
                    evidence={"calculated_ltv": ltv, "calculated_value": ltv, "limit": LTV_CONVENTIONAL_MAX, "loan_type": loan_type},
                ))
            else:
                findings.append(Finding(
                    rule_id="BANK-LTV-002",
                    severity="fail",
                    category="ratio",
                    message=f"LTV {ltv:.1%} dépasse la limite standard de {LTV_CONVENTIONAL_MAX:.0%}",
                    evidence={"calculated_ltv": ltv, "calculated_value": ltv, "limit": LTV_CONVENTIONAL_MAX, "loan_type": loan_type},
                    remediation="Augmenter l'apport personnel ou contracter une assurance emprunteur renforcée",
                ))
        
        return findings
    
    def evaluate_amortization(self, case: Dict[str, Any]) -> List[Finding]:
        """
        Evaluate amortization period against limits.
        
        Args:
            case: Case data with loan.amortization_years and loan.type
            
        Returns:
            List of findings
        """
        findings = []
        loan = case.get("loan", {})
        amort_years = loan.get("amortization_years", 25)
        loan_type = loan.get("type", "conventional").lower()
        is_insured = loan_type in INSURED_TYPES
        
        max_amort = AMORTIZATION_INSURED_MAX if is_insured else AMORTIZATION_UNINSURED_MAX
        
        if amort_years <= max_amort:
            findings.append(Finding(
                rule_id="HCSF-DUREE-001",
                severity="pass",
                category="compliance",
                message=f"Durée du prêt {amort_years} ans dans la limite HCSF de {max_amort} ans",
                evidence={
                    "amortization_years": amort_years,
                    "limit": max_amort,
                    "loan_type": loan_type,
                    "is_insured": is_insured,
                },
            ))
        else:
            findings.append(Finding(
                rule_id="HCSF-DUREE-001",
                severity="fail",
                category="compliance",
                message=f"Durée du prêt {amort_years} ans dépasse la limite HCSF de {max_amort} ans",
                evidence={
                    "amortization_years": amort_years,
                    "limit": max_amort,
                    "loan_type": loan_type,
                    "is_insured": is_insured,
                },
                remediation=f"Réduire la durée du prêt à {max_amort} ans maximum (dérogation HCSF possible pour primo-accédants jusqu'à 27 ans)",
            ))
        
        return findings
    
    def evaluate_down_payment(self, case: Dict[str, Any]) -> List[Finding]:
        """
        Évalue l'apport personnel par rapport aux exigences internes de la banque.

        Règles internes de la banque :
        - Apport personnel minimum : 10% du prix d'acquisition
        - Apport recommandé : 20% (couvre frais de notaire + garantie)
        - Frais notaire ancien ~8%, neuf ~2.5%

        Args:
            case: Case data with deal.purchase_price and deal.down_payment

        Returns:
            List of findings
        """
        findings = []
        deal = case.get("deal", {})
        purchase_price = deal.get("purchase_price", 0)
        down_payment = deal.get("down_payment", 0)

        if purchase_price <= 0:
            return findings

        # Apport minimum (règles internes de la banque) : 10%
        min_dp = purchase_price * 0.10
        recommended_dp = purchase_price * 0.20

        dp_percent = down_payment / purchase_price
        min_percent = min_dp / purchase_price

        if down_payment >= recommended_dp:
            findings.append(Finding(
                rule_id="BANK-APPORT-001",
                severity="pass",
                category="compliance",
                message=f"Apport personnel {dp_percent:.1%} supérieur au seuil recommandé (20%)",
                evidence={
                    "down_payment": down_payment,
                    "minimum_required": min_dp,
                    "recommended": recommended_dp,
                    "purchase_price": purchase_price,
                    "down_payment_percent": dp_percent,
                },
            ))
        elif down_payment >= min_dp:
            findings.append(Finding(
                rule_id="BANK-APPORT-001",
                severity="warning",
                category="compliance",
                message=f"Apport personnel {dp_percent:.1%} suffisant mais sous le seuil recommandé (20%)",
                evidence={
                    "down_payment": down_payment,
                    "minimum_required": min_dp,
                    "recommended": recommended_dp,
                    "purchase_price": purchase_price,
                    "down_payment_percent": dp_percent,
                },
                remediation="Envisager un apport complémentaire pour couvrir les frais de notaire et garantie",
            ))
        else:
            shortfall = min_dp - down_payment
            findings.append(Finding(
                rule_id="BANK-APPORT-001",
                severity="fail",
                category="compliance",
                message=f"Apport personnel {down_payment:,.0f} € ({dp_percent:.1%}) inférieur au minimum requis {min_dp:,.0f} € ({min_percent:.1%})",
                evidence={
                    "down_payment": down_payment,
                    "minimum_required": min_dp,
                    "shortfall": shortfall,
                    "purchase_price": purchase_price,
                },
                remediation=f"Augmenter l'apport d'au moins {shortfall:,.0f} € (PEL, CEL, donation familiale, vente d'un bien)",
            ))

        return findings
    
    def is_stress_test_required(self, case: Dict[str, Any]) -> bool:
        """
        Determine if stress test is required.
        
        Per OSFI B-20, stress test is required for ALL mortgages
        from federally regulated lenders.
        
        Args:
            case: Case data
            
        Returns:
            True (always required under B-20)
        """
        return True
    
    def get_qualifying_rate(self, case: Dict[str, Any]) -> float:
        """
        Get the Minimum Qualifying Rate (MQR).
        
        MQR = max(contract_rate + buffer, floor_rate)
        
        Args:
            case: Case data with loan.contract_rate and optional settings
            
        Returns:
            The qualifying rate to use for stress testing
        """
        loan = case.get("loan", {})
        contract_rate = loan.get("contract_rate", 5.25)
        
        settings = case.get("settings", {})
        floor_rate = settings.get("mqr_floor", MQR_FLOOR)
        buffer = settings.get("mqr_buffer", MQR_BUFFER)
        
        buffered_rate = contract_rate + buffer
        return max(buffered_rate, floor_rate)
    
    def consult_rag(self, query: str) -> Dict[str, Any]:
        """
        Consult RAG service for policy guidance on edge cases.
        
        Args:
            query: Natural language query about policy
            
        Returns:
            Dict with 'guidance' and 'source' keys
        """
        if self.rag_service is None:
            return {
                "guidance": "RAG service not configured",
                "source": None,
            }
        
        # Query the RAG service
        results = self.rag_service.query(
            query=query,
            persona="mortgage_underwriting",
        )
        
        if not results:
            return {
                "guidance": "No relevant policy guidance found",
                "source": None,
            }
        
        top_result = results[0]
        return {
            "guidance": top_result.get("content", ""),
            "source": top_result.get("source", "Unknown"),
            "score": top_result.get("score", 0.0),
        }
    
    def evaluate_all(self, case: Dict[str, Any]) -> List[Finding]:
        """
        Run all policy evaluations on a case.
        
        Args:
            case: Complete case data
            
        Returns:
            List of all findings
        """
        findings = []
        findings.extend(self.evaluate_gds(case))
        findings.extend(self.evaluate_tds(case))
        findings.extend(self.evaluate_ltv(case))
        findings.extend(self.evaluate_amortization(case))
        findings.extend(self.evaluate_down_payment(case))
        return findings


class RecommendationEngine:
    """
    Generates underwriting recommendations based on policy findings.
    """
    
    def __init__(self):
        """Initialize recommendation engine."""
        pass
    
    def generate_recommendation(self, findings: List[Finding]) -> Recommendation:
        """
        Generate underwriting recommendation from findings.
        
        Decision logic:
        - APPROVE: All pass, or pass with minor warnings
        - REFER: Multiple warnings or edge cases
        - DECLINE: Any fail findings
        
        Args:
            findings: List of policy findings
            
        Returns:
            Recommendation with decision and conditions
        """
        # Count findings by severity
        counts = {"pass": 0, "info": 0, "warning": 0, "fail": 0}
        for f in findings:
            severity = f.severity if isinstance(f.severity, str) else f.severity
            counts[severity] = counts.get(severity, 0) + 1
        
        reasons = []
        conditions = []
        
        # Determine decision
        if counts["fail"] > 0:
            decision = Decision.DECLINE.value
            fail_findings = [f for f in findings if f.severity == "fail"]
            reasons = [f.message for f in fail_findings]
        elif counts["warning"] >= 2:
            decision = Decision.REFER.value
            warning_findings = [f for f in findings if f.severity == "warning"]
            reasons = [f"Plusieurs alertes : {len(warning_findings)} éléments à examiner"]
            conditions = [f.remediation for f in warning_findings if f.remediation]
        elif counts["warning"] == 1:
            decision = Decision.APPROVE.value
            warning_findings = [f for f in findings if f.severity == "warning"]
            conditions = [f.remediation for f in warning_findings if f.remediation]
            if conditions:
                reasons = ["Accord sous conditions"]
        else:
            decision = Decision.APPROVE.value
            reasons = ["Tous les contrôles de politique sont conformes"]
        
        # Calculate confidence
        total = sum(counts.values())
        if total > 0:
            confidence = counts["pass"] / total
        else:
            confidence = 0.0
        
        return Recommendation(
            decision=decision,
            confidence=confidence,
            reasons=reasons,
            conditions=conditions,
            findings_summary=counts,
        )
