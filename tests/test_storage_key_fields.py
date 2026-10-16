from __future__ import annotations

import json

from app.claims.api import _extract_damage_areas_from_metadata
from app.storage import (
    ApplicationMetadata,
    StoredFile,
    invalidate_applications_cache,
    list_applications,
    load_application,
    sanitize_extracted_fields,
    _extract_key_fields,
)


def test_extract_key_fields_supports_automotive_claimant_object() -> None:
    metadata = {
        "persona": "automotive_claims",
        "extracted_fields": {
            "thread2-01-client-accident-auto.pdf:Claimant": {
                "value": {
                    "name": "DURAND Claire",
                    "phone": "+33 6 12 34 56 78",
                    "role": "Driver",
                }
            },
            "thread2-01-client-accident-auto.pdf:IncidentDescription": {
                "value": "Accident de stationnement - portière enfoncée"
            },
            "thread2-01-client-accident-auto.pdf:ClaimNumber": {"value": "AUTO-2026-042"},
            "thread2-01-client-accident-auto.pdf:VehicleMake": {"value": "Peugeot"},
            "thread2-01-client-accident-auto.pdf:VehicleModel": {"value": "308"},
        },
    }

    key_fields = _extract_key_fields(metadata)

    assert key_fields["Claimant"] == "DURAND Claire"
    assert key_fields["IncidentDescription"] == "Accident de stationnement - portière enfoncée"
    assert key_fields["ClaimNumber"] == "AUTO-2026-042"
    assert key_fields["VehicleMake"] == "Peugeot"
    assert key_fields["VehicleModel"] == "308"


def test_extract_key_fields_falls_back_to_llm_key_fields_for_underwriting() -> None:
    metadata = {
        "persona": "underwriting",
        "extracted_fields": {},
        "llm_outputs": {
            "application_summary": {
                "customer_profile": {
                    "parsed": {
                        "summary": "Profil de souscription santé.",
                        "key_fields": [
                            {"label": "Nom du client", "value": "Antoine LEFEVRE"},
                            {"label": "Produit demandé", "value": "Équilibre Plus"},
                        ],
                    }
                }
            }
        },
    }

    key_fields = _extract_key_fields(metadata)

    assert key_fields["ApplicantName"] == "Antoine LEFEVRE"
    assert key_fields["PolicyProduct"] == "Équilibre Plus"


def test_extract_key_fields_falls_back_to_markdown_for_extraction_only_underwriting() -> None:
    metadata = {
        "persona": "underwriting",
        "extracted_fields": {},
        "document_markdown": """
# Bulletin de souscription
Nom du client : Marie Dupont
Produit : Garantie Santé Essentielle
""",
    }

    key_fields = _extract_key_fields(metadata)

    assert key_fields["ApplicantName"] == "Marie Dupont"
    assert key_fields["PolicyProduct"] == "Garantie Santé Essentielle"


def test_load_application_resolves_short_id_and_external_reference(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.storage._get_provider", lambda: None)
    app_id = "b6a0f8bf-1234-4567-89ab-000000000001"
    app_dir = tmp_path / "brands" / "prevaiq" / "applications" / app_id
    app_dir.mkdir(parents=True)
    metadata = {
        "id": app_id,
        "created_at": "2026-01-01T00:00:00Z",
        "external_reference": "SIN-AUTO-2026-042",
        "status": "completed",
        "files": [],
        "persona": "automotive_claims",
        "brand": "PrevaIQ",
    }
    (app_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    assert load_application(str(tmp_path), "b6a0f8bf").id == app_id
    assert load_application(str(tmp_path), "SIN-AUTO-2026-042").id == app_id


def test_list_applications_uses_storage_id_when_metadata_id_is_short(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.storage._get_provider", lambda: None)
    invalidate_applications_cache()
    app_id = "5bb5bcf6-1234-4567-89ab-000000000001"
    app_dir = tmp_path / "brands" / "prevaiq" / "applications" / app_id
    app_dir.mkdir(parents=True)
    metadata = {
        "id": "5bb5bcf6",
        "created_at": "2026-06-10T11:04:00Z",
        "status": "extracted",
        "files": [],
        "persona": "underwriting",
        "brand": "PrevaIQ",
        "document_markdown": "Nom du client : Marie Dupont",
    }
    (app_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    apps = list_applications(str(tmp_path), persona="underwriting")

    assert apps[0]["id"] == app_id
    assert apps[0]["key_fields"]["ApplicantName"] == "Marie Dupont"
    invalidate_applications_cache()


def test_sanitize_extracted_fields_removes_html_only_fragments() -> None:
    fields = {
        "claim.pdf:NomAssure": {"value": "</td>", "confidence": 0.8},
        "claim.pdf:NatureSinistre": {"value": "<td>Dégât des eaux</td>", "confidence": 0.9},
        "claim.pdf:Pieces": {"value": ["<tr>", "Facture expert"], "confidence": 0.7},
    }

    sanitized = sanitize_extracted_fields(fields)

    assert sanitized is not None
    assert "claim.pdf:NomAssure" not in sanitized
    assert sanitized["claim.pdf:NatureSinistre"]["value"] == "Dégât des eaux"
    assert sanitized["claim.pdf:Pieces"]["value"] == ["Facture expert"]


def test_extract_damage_areas_supports_llm_and_extracted_field_variants() -> None:
    app_md = ApplicationMetadata(
        id="claim-1",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="completed",
        files=[],
        llm_outputs={
            "damage_assessment": {
                "visual_damage_assessment": {
                    "parsed": {
                        "zones_endommagees": [
                            {
                                "zone": "Pare-chocs avant",
                                "gravite": "grave",
                                "cout_estime": "1 250 €",
                                "description": "Pare-chocs fissuré",
                            }
                        ]
                    }
                }
            }
        },
        extracted_fields={
            "photo.jpg:DamageAreas": {
                "value": [
                    {
                        "location": "Aile droite",
                        "severity": "minor",
                        "estimated_cost": 450,
                        "description": "Rayures visibles",
                    }
                ]
            }
        },
    )

    damage_areas = _extract_damage_areas_from_metadata(app_md, "claim-1")

    assert [area["location"] for area in damage_areas] == ["Pare-chocs avant", "Aile droite"]
    assert damage_areas[0]["severity"] == "severe"
    assert damage_areas[0]["estimated_cost"] == 1250


def test_extract_damage_areas_falls_back_to_evidence_filename() -> None:
    app_md = ApplicationMetadata(
        id="claim-2",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="completed",
        files=[
            StoredFile(
                filename="crash_portière_enfoncée.png",
                path="/tmp/crash_portière_enfoncée.png",
                url=None,
            )
        ],
        llm_outputs={},
        extracted_fields={},
    )

    damage_areas = _extract_damage_areas_from_metadata(app_md, "claim-2")

    assert len(damage_areas) == 1
    assert damage_areas[0]["location"] == "Portière"
    assert damage_areas[0]["severity"] == "moderate"
