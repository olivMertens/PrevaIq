"""
Constants and enums for French Mortgage Underwriting (HCSF / internal bank rules).
"""

from enum import Enum


class MortgageCaseStatus(str, Enum):
    """Status values for mortgage applications."""
    INTAKE = "intake"
    DRAFT = "draft"
    SUBMITTED = "submitted"
    IN_REVIEW = "in_review"
    PENDING_DOCUMENTS = "pending_documents"
    APPROVED = "approved"
    CONDITIONALLY_APPROVED = "conditionally_approved"
    DECLINED = "declined"
    WITHDRAWN = "withdrawn"
    FUNDED = "funded"


class MortgageDocType(str, Enum):
    """Document types for mortgage applications."""
    # Application documents
    APPLICATION = "application"
    CREDIT_REPORT = "credit_report"
    APPRAISAL = "appraisal"
    
    # Income documents
    PAYSTUB = "paystub"
    T4 = "t4"
    NOA = "noa"  # Notice of Assessment
    EMPLOYMENT_LETTER = "employment_letter"
    T1_GENERAL = "t1_general"  # Self-employed
    FINANCIAL_STATEMENTS = "financial_statements"  # Self-employed
    
    # Property documents
    PURCHASE_AGREEMENT = "purchase_agreement"
    PROPERTY_TAX_BILL = "property_tax_bill"
    TITLE_SEARCH = "title_search"
    HOMEOWNERS_INSURANCE = "homeowners_insurance"
    CONDO_DOCUMENTS = "condo_documents"
    
    # Asset/liability documents
    BANK_STATEMENTS = "bank_statements"
    RRSP_STATEMENT = "rrsp_statement"
    GIFT_LETTER = "gift_letter"
    DOWN_PAYMENT_VERIFICATION = "down_payment_verification"
    
    # Other
    ID_VERIFICATION = "id_verification"
    VOID_CHEQUE = "void_cheque"
    OTHER = "other"


class MortgageProductType(str, Enum):
    """Mortgage product types."""
    CONVENTIONAL = "conventional"  # LTV <= 80%
    HIGH_RATIO = "high_ratio"  # LTV > 80%, requires insurance
    CMHC_INSURED = "cmhc_insured"  # CMHC insurance
    GENWORTH_INSURED = "genworth_insured"  # Genworth insurance
    CANADA_GUARANTY_INSURED = "canada_guaranty_insured"  # Canada Guaranty
    REFINANCE = "refinance"
    RENEWAL = "renewal"
    SWITCH = "switch"  # Transfer to another lender


class PropertyType(str, Enum):
    """Property types for Canadian real estate."""
    SINGLE_FAMILY_DETACHED = "single_family_detached"
    SEMI_DETACHED = "semi_detached"
    TOWNHOUSE = "townhouse"
    CONDOMINIUM = "condominium"
    DUPLEX = "duplex"
    TRIPLEX = "triplex"
    FOURPLEX = "fourplex"
    MOBILE_HOME = "mobile_home"
    MODULAR_HOME = "modular_home"
    MIXED_USE = "mixed_use"


class PropertyOccupancy(str, Enum):
    """Property occupancy types."""
    OWNER_OCCUPIED = "owner_occupied"  # Primary residence
    SECOND_HOME = "second_home"  # Vacation property
    INVESTMENT_RENTAL = "investment_rental"  # Rental property


class EmploymentType(str, Enum):
    """Employment types for income qualification."""
    PERMANENT_FULL_TIME = "permanent_full_time"
    PERMANENT_PART_TIME = "permanent_part_time"
    CONTRACT = "contract"
    SELF_EMPLOYED = "self_employed"
    COMMISSION = "commission"
    RETIRED = "retired"
    UNEMPLOYED = "unemployed"
    OTHER = "other"


class IncomeType(str, Enum):
    """Income source types."""
    SALARY = "salary"
    HOURLY = "hourly"
    BONUS = "bonus"
    COMMISSION = "commission"
    OVERTIME = "overtime"
    SELF_EMPLOYED = "self_employed"
    RENTAL = "rental"
    PENSION = "pension"
    DISABILITY = "disability"
    CHILD_SUPPORT = "child_support"
    ALIMONY = "alimony"
    INVESTMENT = "investment"
    OTHER = "other"


class RateType(str, Enum):
    """Mortgage interest rate types."""
    VARIABLE = "variable"
    FIXED_1_YEAR = "fixed_1_year"
    FIXED_2_YEAR = "fixed_2_year"
    FIXED_3_YEAR = "fixed_3_year"
    FIXED_4_YEAR = "fixed_4_year"
    FIXED_5_YEAR = "fixed_5_year"
    FIXED_7_YEAR = "fixed_7_year"
    FIXED_10_YEAR = "fixed_10_year"


class UnderwritingDecision(str, Enum):
    """Final underwriting decisions."""
    APPROVE = "approve"
    APPROVE_WITH_CONDITIONS = "approve_with_conditions"
    REFER = "refer"  # Requires senior underwriter review
    DECLINE = "decline"
    COUNTEROFFER = "counteroffer"  # Offer different terms


class FindingSeverity(str, Enum):
    """Severity levels for policy findings."""
    PASS = "pass"
    INFO = "info"
    WARNING = "warning"
    FAIL = "fail"


class RiskLevel(str, Enum):
    """Overall risk levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


# ---------------------------------------------------------------------------
# French HCSF / internal bank mortgage constants (PRIMARY — used by policy engine)
# ---------------------------------------------------------------------------

# HCSF — Haut Conseil de Stabilité Financière
HCSF_EFFORT_LIMIT = 0.35  # Taux d'effort maximum (charges logement + autres crédits / revenus nets)
HCSF_DUREE_MAX = 25  # Durée maximale du prêt en années
HCSF_DEROGATION_PCT = 0.20  # 20% de flexibilité hors normes HCSF (80% des dossiers conformes)

# Sensibilité (stress test français — pas de norme officielle, pratique de place)
TAUX_SENSIBILITE_BUFFER_PCT = 1.0  # +1 pt de taux pour test de sensibilité
CHARGES_SENSIBILITE_PCT = 0.20  # +20% sur les charges pour test de sensibilité

# Règles internes de la banque
BANK_APPORT_MIN = 0.10  # Apport personnel minimum 10%
BANK_APPORT_RECOMMANDE = 0.20  # Apport recommandé 20%
BANK_RESERVE_MIN_MOIS = 3  # Réserve de précaution en mois de revenus

# Décotes sur revenus variables (pratique bancaire française)
DECOTE_PRIMES = 0.50  # 50% sur primes et bonus
DECOTE_VARIABLE = 0.50  # 50% sur revenus variables/commissions
DECOTE_LOCATIF = 0.30  # 30% sur revenus locatifs (vacance + charges)
DECOTE_INDEP_MOYENNE_ANS = 3  # Moyenne sur 3 dernières années pour indépendants

# Assurance emprunteur (loi Lemoine 2022)
TAEA_REFERENCE = 0.0036  # 0.36% taux annuel effectif assurance de référence
TAEA_MAX_OBSERVE = 0.0080  # 0.80% TAEA plafond observé

# Score crédit FICP/Banque de France
SCORE_BDF_FAVORABLE = 680
SCORE_BDF_NEUTRE = 620
SCORE_BDF_DEFAVORABLE = 580
SCORE_BDF_MIN_BANK = 600

# Apport — seuils en euros
APPORT_RESIDENCE_PRINCIPALE_MIN_PCT = 0.10
APPORT_INVESTISSEMENT_LOCATIF_MIN_PCT = 0.10
FRAIS_NOTAIRE_ANCIEN_PCT = 0.08  # 7-8% pour l'ancien
FRAIS_NOTAIRE_NEUF_PCT = 0.025  # 2-3% pour le neuf

# Usure (Banque de France — taux maximum légal, mis à jour trimestriellement)
TAUX_USURE_REFERENCE = 0.0556  # Exemple T1 2025 prêts >20 ans — placeholder configurable


# ---------------------------------------------------------------------------
# Legacy Canadian aliases (kept for backwards-compatibility with stored data;
# policy engine now emits French rule IDs only).
# ---------------------------------------------------------------------------
OSFI_B20_GDS_LIMIT = HCSF_EFFORT_LIMIT
OSFI_B20_TDS_LIMIT = HCSF_EFFORT_LIMIT
OSFI_MQR_FLOOR_RATE = 5.25  # legacy — no French equivalent
OSFI_MQR_BUFFER = TAUX_SENSIBILITE_BUFFER_PCT

# LTV (kept for legacy callers)
LTV_CONVENTIONAL_MAX = 0.90  # France: souvent 90% financement possible
LTV_INSURED_MAX = 1.00  # France: financement à 100% rare mais possible
LTV_REFINANCE_MAX = 0.80

# Durée
MAX_AMORTIZATION_INSURED = HCSF_DUREE_MAX
MAX_AMORTIZATION_UNINSURED = HCSF_DUREE_MAX

# Apport
MIN_DOWN_PAYMENT_PERCENTAGE = BANK_APPORT_MIN
DOWN_PAYMENT_THRESHOLD_1 = 500_000
DOWN_PAYMENT_THRESHOLD_2 = 1_000_000

# Décotes (aliases)
HAIRCUT_BONUS = DECOTE_PRIMES
HAIRCUT_COMMISSION = DECOTE_VARIABLE
HAIRCUT_OVERTIME = DECOTE_PRIMES
HAIRCUT_RENTAL = DECOTE_LOCATIF

# Score crédit (aliases)
CREDIT_SCORE_EXCELLENT = SCORE_BDF_FAVORABLE + 60
CREDIT_SCORE_GOOD = SCORE_BDF_FAVORABLE
CREDIT_SCORE_FAIR = SCORE_BDF_NEUTRE
CREDIT_SCORE_SUBPRIME = SCORE_BDF_DEFAVORABLE
CREDIT_SCORE_MIN_INSURED = SCORE_BDF_FAVORABLE
CREDIT_SCORE_MIN_CONVENTIONAL = SCORE_BDF_MIN_BANK

# RRSP HBP — pas d'équivalent direct en France (PEL/CEL different); kept as 0
HBP_MAX_PER_PERSON = 0
HBP_MAX_COUPLE = 0
