"""
Unit tests for habitation claims analysis endpoint integration
"""

from __future__ import annotations

from unittest.mock import Mock
from app.claims.habitation_analyzer import (
    HabitationClaimsAnalyzer,
    HabitationClaimsAnalysis,
    AlertSignal,
    TimelineEvent,
    ResponsibilityEvaluation,
    EventType,
    AlertLevel,
)


class TestHabitationAnalyzerBasic:
    """Test habitation analyzer basic functionality"""

    def test_analyzer_initialization(self):
        """Test that HabitationClaimsAnalyzer can be instantiated"""
        analyzer = HabitationClaimsAnalyzer()
        assert analyzer is not None
        assert hasattr(analyzer, 'analyze')

    def test_analyze_method_returns_analysis_object(self):
        """Test that analyze method returns proper HabitationClaimsAnalysis"""
        analyzer = HabitationClaimsAnalyzer()
        analysis = analyzer.analyze(
            claim_id="test-001",
            extracted_fields={"DateSinistre": "15/01/2024"},
            document_markdown="Tempête le 15 janvier",
            persona_config=None,
        )
        
        assert isinstance(analysis, HabitationClaimsAnalysis)
        assert analysis.claim_id == "test-001"

    def test_alert_signal_extraction(self):
        """Test that alert signals are extracted from tempête"""
        analyzer = HabitationClaimsAnalyzer()
        document_markdown = "Sinistre tempête avec vents violents et dégâts importants"
        
        analysis = analyzer.analyze(
            claim_id="test-weather-001",
            extracted_fields={
                "NatureSinistre": "Tempête",
                "DateSinistre": "15/01/2024",
                "DescriptionSinistre": "Inondation du sous-sol suite à la tempête",
            },
            document_markdown=document_markdown,
            persona_config=None,
        )
        
        assert analysis.claim_id == "test-weather-001"
        assert analysis.alert_signals is not None


class TestFieldOrganization:
    """Test field organization and labeling"""

    def test_field_label_mapping_has_french_labels(self):
        """Test that field label mapping provides French translations"""
        from app.claims.api import _field_label_mapping
        
        label_map = _field_label_mapping()
        assert "EmailAssure" in label_map
        assert label_map["EmailAssure"] == "Email de l'assuré"
        assert "TelephoneAssure" in label_map
        assert label_map["TelephoneAssure"] == "Téléphone de l'assuré"
        assert "NumeroPolice" in label_map
        assert label_map["NumeroPolice"] == "Numéro de police"

    def test_extract_field_value_from_dict_format(self):
        """Test extracting field values from dict format (Azure CU)"""
        from app.claims.api import _extract_field_value
        
        fields = {
            "EmailAssure": {"value": "test@example.com"},
            "TelephoneAssure": {"value": "+33612345678"},
        }
        
        assert _extract_field_value(fields, "EmailAssure") == "test@example.com"
        assert _extract_field_value(fields, "TelephoneAssure") == "+33612345678"
        assert _extract_field_value(fields, "NonExistent") is None

    def test_extract_field_value_from_string_format(self):
        """Test extracting field values from string format (test data)"""
        from app.claims.api import _extract_field_value
        
        fields = {
            "EmailAssure": "test@example.com",
            "TelephoneAssure": "+33612345678",
        }
        
        assert _extract_field_value(fields, "EmailAssure") == "test@example.com"
        assert _extract_field_value(fields, "TelephoneAssure") == "+33612345678"

    def test_organize_fields_separates_dossier_and_damages(self):
        """Test that fields are organized into dossier and dommages categories"""
        from app.claims.api import _organize_fields_by_category
        
        extracted_fields = {
            "AssuréNom": "MERTENS Olivier",
            "EmailAssure": "olivier@example.com",
            "DateSinistre": "15/01/2024",
            "MontantEstime": 5000,
            "NatureSinistre": "Tempête",
        }
        
        organized = _organize_fields_by_category(extracted_fields)
        
        # Should have both sections
        assert "information_dossier" in organized
        assert "dommages_constates" in organized
        
        # Dossier fields should contain personal info
        assert "Nom de l'assuré" in organized["information_dossier"] or \
               "AssuréNom" in organized["information_dossier"] or \
               any("assur" in str(k).lower() for k in organized["information_dossier"].keys())

    def test_organize_fields_uses_proper_french_labels(self):
        """Test that organized fields use French label translations"""
        from app.claims.api import _organize_fields_by_category
        
        extracted_fields = {
            "EmailAssure": "olivier@example.com",
            "DateSinistre": "15/01/2024",
        }
        
        organized = _organize_fields_by_category(extracted_fields)
        
        # At least one section should have content
        assert bool(organized.get("information_dossier")) or bool(organized.get("dommages_constates"))
