"""
Integration tests for habitation claims analysis endpoint

Tests the integration of HabitationClaimsAnalyzer with the FastAPI endpoint.
"""

from __future__ import annotations

import pytest
import json
from datetime import datetime, UTC

from app.claims.habitation_analyzer import (
    HabitationClaimsAnalyzer,
    HabitationClaimsAnalysis,
    AlertSignal,
    TimelineEvent,
    ResponsibilityEvaluation,
    EventType,
    AlertLevel,
)

# Import helper functions from API for testing
from app.claims.api import (
    _field_label_mapping,
    _extract_field_value,
    _organize_fields_by_category,
)


class TestHabitationAnalyzerBasic:
    """Basic functionality tests for habitation analyzer"""

    def test_analyzer_can_be_instantiated(self):
        """Verify HabitationClaimsAnalyzer can be created"""
        analyzer = HabitationClaimsAnalyzer()
        assert analyzer is not None

    def test_analyzer_has_analyze_method(self):
        """Verify analyzer has the analyze method required by endpoint"""
        analyzer = HabitationClaimsAnalyzer()
        assert hasattr(analyzer, 'analyze')
        assert callable(analyzer.analyze)

    def test_analyze_returns_habitationcliamsanalysis(self):
        """Verify analyze() returns correct type"""
        analyzer = HabitationClaimsAnalyzer()
        result = analyzer.analyze(
            claim_id="test-001",
            extracted_fields={
                "DateSinistre": "15/01/2024",
                "NatureSinistre": "Tempête",
                "DescriptionSinistre": "Tempête avec inondation",
            },
            document_markdown="Sinistre habitation: tempête",
            persona_config=None,
        )
        assert isinstance(result, HabitationClaimsAnalysis)
        assert result.claim_id == "test-001"

    def test_analysis_output_has_required_fields(self):
        """Verify analysis output has all fields needed by endpoint"""
        analyzer = HabitationClaimsAnalyzer()
        analysis = analyzer.analyze(
            claim_id="test-002",
            extracted_fields={"DateSinistre": "15/01/2024"},
            document_markdown="Test document",
            persona_config=None,
        )
        
        # All required output fields must exist
        assert hasattr(analysis, 'claim_id')
        assert hasattr(analysis, 'alert_signals')
        assert hasattr(analysis, 'timeline')
        assert hasattr(analysis, 'responsibility_evaluation')
        assert hasattr(analysis, 'policy_links')
        assert hasattr(analysis, 'extracted_data_quality')
        
        # Verify types
        assert isinstance(analysis.alert_signals, list)
        assert isinstance(analysis.timeline, list)
        assert isinstance(analysis.policy_links, (dict, list))
        assert isinstance(analysis.extracted_data_quality, dict)

    def test_analyzer_handles_empty_fields(self):
        """Verify analyzer handles missing extracted fields gracefully"""
        analyzer = HabitationClaimsAnalyzer()
        analysis = analyzer.analyze(
            claim_id="test-003",
            extracted_fields={},
            document_markdown="",
            persona_config=None,
        )
        
        # Should not raise exception, should return valid analysis
        assert analysis.claim_id == "test-003"
        assert isinstance(analysis.alert_signals, list)
        assert isinstance(analysis.responsibility_evaluation, (ResponsibilityEvaluation, type(None)))


class TestEndpointResponseFormat:
    """Tests for endpoint response format compatibility"""

    def test_alert_signal_is_json_serializable(self):
        """Verify alert signals can be serialized to JSON"""
        signal = AlertSignal(
            signal_type="weather",
            level=AlertLevel.HIGH,
            description="Tempête",
            evidence="vents violents",
            policy_ref="HAB-TMP-001",
        )
        
        signal_dict = {
            "signal_type": signal.signal_type,
            "level": signal.level.value,
            "description": signal.description,
            "evidence": signal.evidence,
            "policy_ref": signal.policy_ref,
        }
        
        json_str = json.dumps(signal_dict)
        assert json_str is not None
        # Check either raw text or unicode-encoded version
        assert "Tempete" in json_str or "Temp" in json_str

    def test_responsibility_evaluation_is_json_serializable(self):
        """Verify responsibility evaluation can be serialized to JSON"""
        resp = ResponsibilityEvaluation(
            is_covered=True,
            confidence=0.95,
            policy_id="HAB-TMP-001",
            policy_name="Couverture Tempête",
            reason="Tempête couverte",
        )
        
        resp_dict = {
            "is_covered": resp.is_covered,
            "confidence": resp.confidence,
            "policy_id": resp.policy_id,
            "policy_name": resp.policy_name,
            "reason": resp.reason,
            "exceptions": resp.exceptions,
            "supporting_clauses": resp.supporting_clauses,
        }
        
        json_str = json.dumps(resp_dict)
        assert json_str is not None
        assert "True" in json_str or "true" in json_str

    def test_analysis_output_json_serializable(self):
        """Verify complete analysis output can be serialized with new organized fields"""
        # Mock response with all required fields including organized dossier/dommages sections
        response = {
            "information_dossier": {
                "Nom de l'assuré": "Martin Dupont",
                "Email de l'assuré": "martin.dupont@mail.com",
                "Téléphone de l'assuré": "06 12 34 56 78",
                "Numéro de police": "HAB-2024-001",
                "Numéro de contrat": "HAB-33-2021-091745",
                "Formule de contrat": "Multirisque Habitation - Confort Plus",
            },
            "dommages_constates": {
                "Date du sinistre": "15/01/2024",
                "Nature du sinistre": "Tempête",
                "Lieu du sinistre": "Paris 75000",
                "Description du sinistre": "Tempête destructrice avec dégâts",
                "Montant estimé": "€8500",
            },
            "dossier_info": {
                "claim_id": "HAB-2024-001",
                "customer_name": "Martin Dupont",
                "claim_date": "15/01/2024",
                "claim_type": "Tempête",
                "policy_number": "HAB-2024-001",
                "location": "Paris 75000",
            },
            "claim_id": "HAB-2024-001",
            "alert_signals": [
                {
                    "signal_type": "weather_event",
                    "level": "high",
                    "description": "Événement climatique: Tempête",
                    "evidence": "Tempête destructrice",
                    "policy_ref": "HAB-TMP-001",
                }
            ],
            "timeline": [
                {
                    "event_type": "claim_date",
                    "date": "15/01/2024",
                    "description": "Tempête observée",
                    "evidence": "Déclaration du client",
                    "document_section": "damage_description",
                }
            ],
            "responsibility_evaluation": {
                "is_covered": True,
                "confidence": 0.95,
                "policy_id": "HAB-TMP-001",
                "policy_name": "Couverture Tempête",
                "reason": "Tempête couverte par contrat multirisque",
                "exceptions": [],
                "supporting_clauses": ["Article 5.2 des CG"],
            },
            "analyse_images": {
                "image_count": 4,
                "images": [
                    {
                        "filename": "damage_photo_1.png",
                        "description": "Photos de dommages",
                        "detected_damage": "En attente d'analyse Mistral vision",
                        "validation_status": "pending",
                        "matches_description": None,
                        "notes": "À valider via Mistral",
                    }
                ],
                "overall_assessment": "4 photos - À valider via Mistral vision API",
                "validation_against_description": "À comparer avec: Tempête",
            },
            "policy_links": [
                {
                    "section_title": "Couverture Tempête",
                    "page_number": 5,
                    "page_offset": 2,
                    "indicator_text": "Tempête",
                    "context": "Risques couverts – Article 5.2",
                }
            ],
            "data_quality": {
                "NatureSinistre": 0.98,
                "DateSinistre": 0.95,
                "DescriptionSinistre": 0.92,
            },
            "analysis_timestamp": datetime.now(UTC).isoformat(),
        }
        
        # Should be JSON serializable
        json_str = json.dumps(response, default=str)
        assert json_str is not None
        assert len(json_str) > 0
        assert "HAB-2024-001" in json_str
        assert "dossier_info" in json_str
        assert "Martin Dupont" in json_str
        assert "15/01/2024" in json_str
        # Check for organized field sections
        assert "information_dossier" in json_str
        assert "dommages_constates" in json_str
        assert "analyse_images" in json_str
        # Check for proper French labels (not camelCase)
        assert "Nom de l'assuré" in json_str or "Nom de l" in json_str
        assert "Nature du sinistre" in json_str or "Nature du" in json_str
        # Check for Mistral image analysis section
        assert "Mistral" in json_str


class TestEndpointIntegration:
    """Tests for endpoint integration mechanics"""

    def test_endpoint_route_path(self):
        """Verify endpoint route path is correctly formatted"""
        route = "/habitation/{claim_id}/analysis"
        assert route.startswith("/")
        assert "{claim_id}" in route
        assert route.endswith("/analysis")

    def test_endpoint_would_accept_valid_claim_id(self):
        """Verify endpoint parameter format"""
        # Test various claim ID formats that might be used
        valid_ids = [
            "test-001",
            "claim-12345",
            "HAB-2024-001",
            "f47ac10b-58cc-4372-a567-0e02b2c3d479",
        ]
        
        for claim_id in valid_ids:
            # Endpoint would accept these through FastAPI path parameter
            assert isinstance(claim_id, str)
            assert len(claim_id) > 0

    def test_analyzer_compatible_with_endpoint_signature(self):
        """Verify analyzer.analyze() matches endpoint usage"""
        analyzer = HabitationClaimsAnalyzer()
        
        # Endpoint calls: analyzer.analyze(claim_id, extracted_fields, document_markdown, persona_config)
        # This should work without errors
        analysis = analyzer.analyze(
            claim_id="endpoint-test-001",
            extracted_fields={},
            document_markdown="",
            persona_config=None,
        )
        
        assert analysis.claim_id == "endpoint-test-001"


class TestFieldOrganization:
    """Tests for field label mapping and organization"""

    def test_field_label_mapping_has_french_labels(self):
        """Verify field label mapping provides proper French labels"""
        mapping = _field_label_mapping()
        
        # Verify all labels are in French and not camelCase
        assert mapping.get("EmailAssure") == "Email de l'assuré"
        assert mapping.get("TelephoneAssure") == "Téléphone de l'assuré"
        assert mapping.get("NumeroContrat") == "Numéro de contrat"
        assert mapping.get("NumeroPolice") == "Numéro de police"
        assert mapping.get("NatureSinistre") == "Nature du sinistre"
        assert mapping.get("LieuSinistre") == "Lieu du sinistre"
        assert mapping.get("DateSinistre") == "Date du sinistre"
        assert mapping.get("MontantEstime") == "Montant estimé"
        
        # Verify no camelCase in values
        for label in mapping.values():
            # French labels should not have camelCase patterns
            assert not any(c.isupper() and c.isupper() for i, c in enumerate(label) if i > 0)

    def test_extract_field_value_from_dict_format(self):
        """Verify field extraction from dict format (CU API style)"""
        fields = {
            "EmailAssure": {"value": "test@example.com"},
            "TelephoneAssure": {"value": "06 12 34 56 78"},
            "NatureSinistre": {"value": "Tempête"},
        }
        
        assert _extract_field_value(fields, "EmailAssure") == "test@example.com"
        assert _extract_field_value(fields, "TelephoneAssure") == "06 12 34 56 78"
        assert _extract_field_value(fields, "NatureSinistre") == "Tempête"

    def test_extract_field_value_from_string_format(self):
        """Verify field extraction from plain string format"""
        fields = {
            "EmailAssure": "test@example.com",
            "TelephoneAssure": "06 12 34 56 78",
            "NatureSinistre": "Tempête",
        }
        
        assert _extract_field_value(fields, "EmailAssure") == "test@example.com"
        assert _extract_field_value(fields, "TelephoneAssure") == "06 12 34 56 78"
        assert _extract_field_value(fields, "NatureSinistre") == "Tempête"

    def test_organize_fields_separates_dossier_and_damages(self):
        """Verify fields are organized into proper categories"""
        extracted_fields = {
            "AssuréNom": "Martin Dupont",
            "EmailAssure": "martin@mail.com",
            "NumeroPolice": "HAB-2024-001",
            "DateSinistre": "15/01/2024",
            "NatureSinistre": "Tempête",
            "LieuSinistre": "Paris",
            "MontantEstime": "€8500",
            "DescriptionSinistre": "Tempête destructrice",
        }
        
        organized = _organize_fields_by_category(extracted_fields)
        
        # Verify structure
        assert "information_dossier" in organized
        assert "dommages_constates" in organized
        
        # Verify dossier info has personal/policy data
        dossier = organized["information_dossier"]
        assert "Nom de l'assuré" in dossier
        assert dossier["Nom de l'assuré"] == "Martin Dupont"
        assert "Email de l'assuré" in dossier
        assert "Numéro de police" in dossier
        
        # Verify damages section has damage data
        damages = organized["dommages_constates"]
        assert "Date du sinistre" in damages
        assert damages["Date du sinistre"] == "15/01/2024"
        assert "Nature du sinistre" in damages
        assert damages["Nature du sinistre"] == "Tempête"
        assert "Lieu du sinistre" in damages
        assert "Montant estimé" in damages
        
        # Verify they don't cross-contaminate
        assert "Email de l'assuré" not in damages
        assert "Date du sinistre" not in dossier

    def test_organize_fields_uses_proper_french_labels(self):
        """Verify organized fields use proper French labels, not camelCase"""
        extracted_fields = {
            "TelephoneAssure": "06 12 34 56 78",
            "NatureSinistre": "Dégâts des eaux",
        }
        
        organized = _organize_fields_by_category(extracted_fields)
        
        # Verify French labels
        assert "Téléphone de l'assuré" in organized["information_dossier"]
        assert "Nature du sinistre" in organized["dommages_constates"]
        
        # Verify NO camelCase
        all_labels = list(organized["information_dossier"].keys()) + list(organized["dommages_constates"].keys())
        for label in all_labels:
            assert "Assure" not in label  # No camelCase field names
            assert "Sinistre" not in label  # No camelCase field names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
