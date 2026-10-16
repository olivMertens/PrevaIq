"""
Habitation Claims Enhanced Analysis

Improves extraction and analysis of habitation claims with:
- Alert signals detection (weather, value, fraud indicators)
- Chronology timeline extraction from documents
- Responsibility evaluation based on policy conditions
- Policy PDF reference links
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

import logging

logger = logging.getLogger(__name__)


class AlertLevel(str, Enum):
    """Alert severity levels"""
    HIGH = "high"  # Red
    MEDIUM = "medium"  # Orange/Yellow
    LOW = "low"  # Green
    NONE = "none"  # No alert


class EventType(str, Enum):
    """Types of events in a habitation claim"""
    CLAIM_DATE = "claim_date"  # Date of the incident
    CLIENT_CALL = "client_call"  # Client notification
    INSPECTION = "inspection"  # Expert inspection
    DAMAGE_DISCOVERY = "damage_discovery"  # When damage was discovered
    REMEDIAL_ACTION = "remedial_action"  # Actions taken (pumping, drying, etc.)
    OTHER = "other"


@dataclass
class AlertSignal:
    """A risk or alert signal in a claim"""
    signal_type: str  # "weather", "high_value", "fraud_indicator", "timeline_gap", etc.
    level: AlertLevel
    description: str
    evidence: str = ""  # Supporting text from document
    policy_ref: str = ""  # Which policy condition this relates to


@dataclass
class TimelineEvent:
    """An event in the claim chronology"""
    event_type: EventType
    date: Optional[str] = None  # ISO format or "DD/MM/YYYY"
    description: str = ""
    evidence: str = ""  # Quote from document
    document_section: str = ""  # Which field/section in extracted data


@dataclass
class ResponsibilityEvaluation:
    """Evaluation of policy responsibility"""
    is_covered: bool
    confidence: float  # 0.0 - 1.0
    policy_id: str = ""
    policy_name: str = ""
    reason: str = ""
    exceptions: List[str] = field(default_factory=list)  # If not covered
    supporting_clauses: List[str] = field(default_factory=list)


@dataclass
class HabitationClaimsAnalysis:
    """Enhanced analysis output for habitation claims"""
    claim_id: str
    alert_signals: List[AlertSignal] = field(default_factory=list)
    timeline: List[TimelineEvent] = field(default_factory=list)
    responsibility_evaluation: Optional[ResponsibilityEvaluation] = None
    policy_links: Dict[str, str] = field(default_factory=dict)  # {policy_id: pdf_url}
    extracted_data_quality: Dict[str, float] = field(default_factory=dict)  # {field: confidence}


class HabitationClaimsAnalyzer:
    """Analyze extracted habitation claims data and improve output"""

    def __init__(self):
        """Initialize the analyzer"""
        self.weather_keywords = [
            "tempête", "tempête", "grêle", "neige",  # French
            "pluie", "inondation", "submersion",
            "infiltration", "dégâts des eaux",
            "cyclone", "ouragan", "vent",
            "thunder", "wind", "rain", "flood", "hail", "storm", "snow"  # English
        ]
        
        self.date_patterns = [
            r'(\d{1,2}[/-]?\d{1,2}[/-]?\d{4})',  # DD/MM/YYYY or similar
            r'(\d{4}[/-]?\d{1,2}[/-]?\d{1,2})',  # YYYY-MM-DD
            r'(\d{1,2}\s+(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})',
        ]
        
        self.event_keywords = {
            EventType.CLIENT_CALL: ["appel", "contact", "déclaration", "contacté", "call", "called"],
            EventType.INSPECTION: ["expert", "inspection", "visite", "examen", "survey"],
            EventType.REMEDIAL_ACTION: ["pompage", "dessication", "assèchement", "réparation", "pumped", "drying", "fixed"],
            EventType.DAMAGE_DISCOVERY: ["découverte", "constaté", "remarqué", "trouvé", "discovered", "found", "noted"],
        }

    def _extract_field_value(self, field: Any) -> str:
        """
        Extract value from a field, handling both dict and string formats.
        
        Args:
            field: Either a dict with 'value' key (from CU API) or a plain string
        
        Returns:
            String value or empty string if not found
        """
        if not field:
            return ""
        # If it's a dict with 'value' key (from CU API)
        if isinstance(field, dict):
            return str(field.get("value", "")).lower()
        # If it's a string
        if isinstance(field, str):
            return field.lower() if field.strip() else ""
        return ""

    def analyze(
        self,
        claim_id: str,
        extracted_fields: Dict[str, Any],
        document_markdown: str,
        persona_config: Optional[Dict[str, Any]] = None,
    ) -> HabitationClaimsAnalysis:
        """
        Analyze habitation claim data and generate enhanced analysis.

        Args:
            claim_id: Unique claim identifier
            extracted_fields: Fields extracted from CU
            document_markdown: Full document text from CU
            persona_config: Optional persona-specific configuration

        Returns:
            HabitationClaimsAnalysis with signals, timeline, and responsibility
        """
        analysis = HabitationClaimsAnalysis(claim_id=claim_id)

        # 1. Extract alert signals
        analysis.alert_signals = self._extract_alert_signals(
            extracted_fields, document_markdown, persona_config
        )

        # 2. Build timeline from extracted data
        analysis.timeline = self._build_timeline(
            extracted_fields, document_markdown
        )

        # 3. Evaluate responsibility
        analysis.responsibility_evaluation = self._evaluate_responsibility(
            extracted_fields, document_markdown, analysis.alert_signals
        )

        # 4. Generate policy links
        analysis.policy_links = self._generate_policy_links(
            extracted_fields, analysis.alert_signals
        )

        # 5. Assess data quality
        analysis.extracted_data_quality = self._assess_data_quality(extracted_fields)

        return analysis

    def _extract_alert_signals(
        self,
        extracted_fields: Dict[str, Any],
        document_markdown: str,
        persona_config: Optional[Dict[str, Any]] = None,
    ) -> List[AlertSignal]:
        """Extract alert signals from claim data"""
        signals: List[AlertSignal] = []

        # Signal 1: Weather event type detection
        nature = self._extract_field_value(extracted_fields.get("NatureSinistre", ""))
        if any(keyword in nature for keyword in self.weather_keywords):
            event_type = "Dégâts des eaux"
            if "tempête" in nature:
                event_type = "Tempête"
            elif "grêle" in nature:
                event_type = "Grêle"
            elif "neige" in nature:
                event_type = "Neige"
            
            signals.append(AlertSignal(
                signal_type="weather_event",
                level=AlertLevel.HIGH,
                description=f"Événement climatique: {event_type}",
                evidence=nature,
                policy_ref="HAB-TMP-001 ou HAB-INOND-002"
            ))

        # Signal 2: High value claims
        amount = extracted_fields.get("MontantEstime", {})
        if amount:
            # Handle both dict and string format
            amount_str = amount.get("value", "") if isinstance(amount, dict) else str(amount)
            try:
                amount_val = float(str(amount_str).replace("€", "").replace(",", "."))
                if amount_val > 5000:
                    signals.append(AlertSignal(
                        signal_type="high_value",
                        level=AlertLevel.MEDIUM if amount_val < 20000 else AlertLevel.HIGH,
                        description=f"Sinistre de valeur élevée: {amount_val}€",
                        evidence=f"Montant estimé: {amount_str}",
                        policy_ref="Mandate expert si > 5000€"
                    ))
            except ValueError:
                pass

        # Signal 3: Timeline gaps (discovery delay)
        date_sinistre_raw = extracted_fields.get("DateSinistre", "")
        date_declaration_raw = extracted_fields.get("DateDeclaration", "")
        
        date_sinistre = self._extract_field_value(date_sinistre_raw)
        date_declaration = self._extract_field_value(date_declaration_raw)
        
        if date_sinistre and date_declaration:
            # Parse dates and check gap
            try:
                # Parse dates (handle both DD/MM/YYYY and ISO formats)
                d1 = self._parse_date(date_sinistre)
                d2 = self._parse_date(date_declaration)
                if d1 and d2:
                    gap_days = (d2 - d1).days
                    if gap_days > 30:
                        signals.append(AlertSignal(
                            signal_type="timeline_gap",
                            level=AlertLevel.MEDIUM,
                            description=f"Délai entre sinistre et déclaration: {gap_days} jours",
                            evidence=f"Sinistre: {date_sinistre}, Déclaration: {date_declaration}",
                            policy_ref="Convention IRSI: déclaration rapide attendue"
                        ))
            except Exception as e:
                logger.debug(f"Error parsing dates for timeline gap: {e}")

        # Signal 4: Fraud indicators
        description_raw = extracted_fields.get("DescriptionSinistre", "")
        description = self._extract_field_value(description_raw)
        fraud_keywords = [
            "récent", "neuf", "amélioration", "rénovation", "changement",
            "suspicious", "unusual", "recent", "new", "upgrade"
        ]
        if any(keyword in description[:100] for keyword in fraud_keywords):
            signals.append(AlertSignal(
                signal_type="fraud_indicator",
                level=AlertLevel.LOW,
                description="Termes suspects détectés - inspection recommandée",
                evidence=description[:100],
                policy_ref="Vérification Anti-fraude"
            ))

        # Signal 5: Missing critical data
        critical_fields = [
            "NatureSinistre", "DateSinistre", "LieuSinistre",
            "MontantEstime", "DescriptionSinistre"
        ]
        missing = [
            f for f in critical_fields 
            if not self._extract_field_value(extracted_fields.get(f, ""))
        ]
        if len(missing) > 2:
            signals.append(AlertSignal(
                signal_type="missing_data",
                level=AlertLevel.MEDIUM,
                description=f"Données manquantes: {', '.join(missing)}",
                evidence="",
                policy_ref="Demander complément de dossier"
            ))

        # Signal 6: Water damage without deductible mention
        if "dégâts des eaux" in nature and "franchise" not in document_markdown.lower():
            signals.append(AlertSignal(
                signal_type="deductible_unclear",
                level=AlertLevel.LOW,
                description="Franchise Dégâts des Eaux non confirmée",
                evidence="",
                policy_ref="Convention IRSI: franchises applicables"
            ))

        return signals

    def _build_timeline(
        self,
        extracted_fields: Dict[str, Any],
        document_markdown: str,
    ) -> List[TimelineEvent]:
        """Build chronology timeline from extracted data"""
        events: List[TimelineEvent] = []

        # Event 1: Date of incident (sinistre)
        date_sinistre_raw = extracted_fields.get("DateSinistre", "")
        date_sinistre = self._extract_field_value(date_sinistre_raw) if date_sinistre_raw else None
        if date_sinistre and date_sinistre.strip():
            # Get the original format for display
            date_display = date_sinistre_raw.get("value") if isinstance(date_sinistre_raw, dict) else date_sinistre_raw
            events.append(TimelineEvent(
                event_type=EventType.CLAIM_DATE,
                date=str(date_display),
                description="Date du sinistre",
                evidence=str(date_display),
                document_section="DateSinistre"
            ))

        # Event 2: Client declaration date
        date_declaration_raw = extracted_fields.get("DateDeclaration", "")
        date_declaration = self._extract_field_value(date_declaration_raw) if date_declaration_raw else None
        if date_declaration and date_declaration.strip():
            date_display = date_declaration_raw.get("value") if isinstance(date_declaration_raw, dict) else date_declaration_raw
            events.append(TimelineEvent(
                event_type=EventType.CLIENT_CALL,
                date=str(date_display),
                description="Déclaration du sinistre par l'assuré",
                evidence=str(date_display),
                document_section="DateDeclaration"
            ))

        # Event 3: Inspection/Expert visit
        date_expert_raw = extracted_fields.get("DateExpert", "")
        date_expert = self._extract_field_value(date_expert_raw) if date_expert_raw else None
        if date_expert and date_expert.strip():
            date_display = date_expert_raw.get("value") if isinstance(date_expert_raw, dict) else date_expert_raw
            events.append(TimelineEvent(
                event_type=EventType.INSPECTION,
                date=str(date_display),
                description="Visite de l'expert",
                evidence=str(date_display),
                document_section="DateExpert"
            ))

        # Event 4: Remedial actions (if mentioned)
        measures_raw = extracted_fields.get("MeuresConservatoires", "")
        measures = self._extract_field_value(measures_raw) if measures_raw else ""
        if measures and ("pompage" in measures or "assèchement" in measures):
            # Try to find date mention in document
            remedy_dates = self._find_dates_in_text(measures)
            if remedy_dates:
                events.append(TimelineEvent(
                    event_type=EventType.REMEDIAL_ACTION,
                    date=remedy_dates[0],
                    description=f"Actions conservatoires: {measures}",
                    evidence=measures,
                    document_section="MeuresConservatoires"
                ))

        # Sort by date
        events.sort(key=lambda e: self._parse_date(e.date) or datetime.min)

        return events

    def _evaluate_responsibility(
        self,
        extracted_fields: Dict[str, Any],
        document_markdown: str,
        alert_signals: List[AlertSignal],
    ) -> ResponsibilityEvaluation:
        """Evaluate responsibility based on policy conditions"""

        nature_raw = extracted_fields.get("NatureSinistre", "")
        lieu_raw = extracted_fields.get("LieuSinistre", "")
        
        nature = self._extract_field_value(nature_raw)
        lieu = self._extract_field_value(lieu_raw)

        # Default evaluation
        is_covered = False
        policy_id = ""
        policy_name = ""
        confidence = 0.5
        reason = ""
        exceptions: List[str] = []
        supporting_clauses: List[str] = []

        # Evaluate based on event nature
        if "tempête" in nature:
            is_covered = True
            policy_id = "HAB-TMP-001"
            policy_name = "Garantie Tempête, Grêle et Neige"
            confidence = 0.95
            reason = "Événement climatique couvert par la garantie tempête"
            supporting_clauses = [
                "Article 3.4 — Tempête, grêle, neige des CG Habitation",
                "Convention IRSI pour détermination du sinistre"
            ]
            
            # Check for exclusions
            if "franchise" in document_markdown.lower():
                exceptions.append("Franchise tempête applicable (380€ minimum)")
            if "défaut d'entretien" in nature:
                exceptions.append("Réduction possible pour défaut d'entretien caractérisé")

        elif "inondation" in nature or "infiltration" in nature or "dégâts des eaux" in nature:
            is_covered = True
            policy_id = "HAB-INOND-002"
            policy_name = "Garantie Dégâts des Eaux"
            confidence = 0.90
            reason = "Dégâts des eaux couverts par la garantie inondation"
            supporting_clauses = [
                "Article 3.2 — Inondation des CG Habitation",
                "Article 3.3 — Dégâts des eaux internes"
            ]
            
            # Check for exclusions
            if "infiltration" in nature and "défaut d'entretien" in nature:
                is_covered = False
                reason = "Infiltration due à défaut d'entretien non couverte"
                confidence = 0.80
                exceptions.append("Exclusion: infiltrations dues à défaut d'entretien")

        elif "cambriolage" in nature or "vol" in nature:
            is_covered = True
            policy_id = "HAB-VOL-003"
            policy_name = "Garantie Vol et Cambriolage"
            confidence = 0.85
            reason = "Vol ou cambriolage couvert par la garantie vol"
            
            # Check police report requirement
            if "plainte" not in document_markdown.lower():
                exceptions.append("Dépôt de plainte requis pour indemnisation")

        else:
            is_covered = False
            reason = f"Nature du sinistre '{nature}' non couverte ou non déterminée"
            confidence = 0.40
            exceptions.append("Besoin de clarification sur la nature du sinistre")

        # Check for high-risk alert signals that may affect coverage
        for signal in alert_signals:
            if signal.signal_type == "fraud_indicator":
                confidence = max(0.0, confidence - 0.15)
            elif signal.signal_type == "timeline_gap":
                if signal.level == AlertLevel.HIGH:
                    exceptions.append("Délai de déclaration dépassant Convention IRSI")

        return ResponsibilityEvaluation(
            is_covered=is_covered,
            confidence=confidence,
            policy_id=policy_id,
            policy_name=policy_name,
            reason=reason,
            exceptions=exceptions,
            supporting_clauses=supporting_clauses,
        )

    def _generate_policy_links(
        self,
        extracted_fields: Dict[str, Any],
        alert_signals: List[AlertSignal],
    ) -> Dict[str, str]:
        """Generate links to relevant policy PDFs (requires POLICY_PDF_BASE_URL)."""
        links: Dict[str, str] = {}
        base_url = os.getenv("POLICY_PDF_BASE_URL", "").rstrip("/")
        if not base_url:
            return links

        # Map policy IDs to PDF links
        policy_pdf_map = {
            "HAB-TMP-001": f"{base_url}/habitation-tempete-grele-neige.pdf",
            "HAB-INOND-002": f"{base_url}/habitation-inondation-degats-eaux.pdf",
            "HAB-VOL-003": f"{base_url}/habitation-vol-cambriolage.pdf",
            "HAB-FRAUD": f"{base_url}/habitation-procedures-fraude.pdf",
        }

        # Add relevant policy links based on alert signals and nature
        for signal in alert_signals:
            if signal.policy_ref:
                policy_id = signal.policy_ref.split()[0]
                if policy_id in policy_pdf_map:
                    links[policy_id] = policy_pdf_map[policy_id]

        # Always include multi-risk contract summary
        links["HAB-MULTIRISQUE"] = f"{base_url}/habitation-conditions-generales.pdf"

        return links

    def _assess_data_quality(self, extracted_fields: Dict[str, Any]) -> Dict[str, float]:
        """Assess quality/confidence of extracted fields"""
        quality: Dict[str, float] = {}

        important_fields = [
            "NatureSinistre",
            "DateSinistre",
            "LieuSinistre",
            "MontantEstime",
            "DescriptionSinistre",
            "AssuréNom",
            "NumeroPolice",
        ]

        for field_name in important_fields:
            field_data = extracted_fields.get(field_name, {})
            # Handle both dict and string formats
            if isinstance(field_data, dict):
                value = field_data.get("value")
                confidence = field_data.get("confidence", 0.5)
            else:
                # String format
                value = field_data
                confidence = 0.8  # Assume good confidence for string values
            
            # If field has a value, use confidence; otherwise 0
            quality[field_name] = confidence if value else 0.0

        return quality

    def _find_dates_in_text(self, text: str) -> List[str]:
        """Find all dates in text"""
        dates: List[str] = []
        for pattern in self.date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)
        return list(set(dates))  # Remove duplicates

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date string to datetime object"""
        if not date_str:
            return None

        # Try different date formats
        formats = [
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y-%m-%d",
            "%d.%m.%Y",
            "%d %m %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        logger.debug(f"Could not parse date: {date_str}")
        return None


# Export main analyzer
__all__ = [
    "HabitationClaimsAnalyzer",
    "HabitationClaimsAnalysis",
    "AlertSignal",
    "AlertLevel",
    "TimelineEvent",
    "ResponsibilityEvaluation",
    "EventType",
]
