#!/usr/bin/env python3
"""
Create custom Content Understanding analyzers for WorkbenchIQ demo use cases.

Creates three analyzers:
1. habitationClaimsAnalyzer — For habitation claims documents (degats des eaux, tempete)
2. habitationClaimsImageAnalyzer — For damage photos (structured image analysis)
3. healthUnderwritingAnalyzer — For health insurance underwriting (souscription sante)

These analyzers extract structured fields from uploaded documents and images with confidence scores.

Usage:
    python scripts/setup_demo_analyzers.py
"""

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_settings
from app.content_understanding_client import (
    get_analyzer,
    _get_auth_token_and_headers,
    _raise_for_status_with_detail,
    poll_result,
)
from app.utils import setup_logging

logger = setup_logging()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Analyzer definitions
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HABITATION_ANALYZER = {
    "analyzerId": "habitationClaimsAnalyzer",
    "body": {
        "baseAnalyzerId": "prebuilt-document",
        "description": "Analyseur de sinistres habitation - declaration de sinistre, degats des eaux, tempete, inventaire",
        "config": {
            "returnDetails": True,
        },
        "fieldSchema": {
            "name": "habitation_claims_schema",
            "description": "Schema pour les declarations de sinistres habitation",
            "fields": {
                "NomAssure": {
                    "type": "string",
                    "method": "extract",
                    "description": "Nom et prenom de l'assure (ex: MERTENS LAFFITE Olivier)",
                },
                "AdresseAssure": {
                    "type": "string",
                    "method": "extract",
                    "description": "Adresse complete de l'assure",
                },
                "EmailAssure": {
                    "type": "string",
                    "method": "extract",
                    "description": "Adresse email de l'assure",
                },
                "TelephoneAssure": {
                    "type": "string",
                    "method": "extract",
                    "description": "Numero de telephone de l'assure",
                },
                "NumeroContrat": {
                    "type": "string",
                    "method": "extract",
                    "description": "Numero du contrat d'assurance habitation (ex: HAB-33-2021-091745)",
                },
                "NumeroSocietaire": {
                    "type": "string",
                    "method": "extract",
                    "description": "Numero de societaire / client de l'assure",
                },
                "FormuleContrat": {
                    "type": "string",
                    "method": "extract",
                    "description": "Formule du contrat (Multirisque Habitation, Confort Plus, etc.)",
                },
                "DateSinistre": {
                    "type": "date",
                    "method": "extract",
                    "description": "Date du sinistre",
                },
                "NatureSinistre": {
                    "type": "string",
                    "method": "classify",
                    "description": "Type de sinistre",
                    "enum": [
                        "Degats des eaux",
                        "Tempete",
                        "Grele",
                        "Catastrophe naturelle",
                        "Incendie",
                        "Vol",
                        "Bris de glace",
                        "Autre",
                    ],
                },
                "LieuSinistre": {
                    "type": "string",
                    "method": "extract",
                    "description": "Lieu exact du sinistre dans le logement (cave, sous-sol, rez-de-chaussee, etc.)",
                },
                "DescriptionSinistre": {
                    "type": "string",
                    "method": "generate",
                    "description": "Resume detaille des circonstances du sinistre en 3-5 phrases",
                },
                "MontantEstime": {
                    "type": "number",
                    "method": "extract",
                    "description": "Montant total estime des dommages en euros",
                },
                "MesuresConservatoires": {
                    "type": "string",
                    "method": "generate",
                    "description": "Mesures conservatoires prises par l'assure (pompage, coupure electricite, etc.)",
                },
                "NombreItemsEndommages": {
                    "type": "number",
                    "method": "extract",
                    "description": "Nombre total de biens endommages dans l'inventaire",
                },
                "FranchiseApplicable": {
                    "type": "string",
                    "method": "extract",
                    "description": "Montant de la franchise applicable selon le contrat",
                },
                "TiersImplique": {
                    "type": "string",
                    "method": "classify",
                    "description": "Y a-t-il un tiers implique dans le sinistre",
                    "enum": ["Oui", "Non", "Non applicable"],
                },
                "NiveauUrgence": {
                    "type": "string",
                    "method": "classify",
                    "description": "Niveau d'urgence du sinistre base sur la description",
                    "enum": ["Faible", "Moyen", "Eleve", "Critique"],
                },
            },
        },
    },
}

HABITATION_CLAIMS_IMAGE_ANALYZER = {
    "analyzerId": "habitationClaimsImageAnalyzer",
    "body": {
        "baseAnalyzerId": "prebuilt-image",
        "description": "Analyseur de photos de dommages habitation - photos de sinistres, degats, assessement dommages",
        "config": {
            "returnDetails": True,
        },
        "fieldSchema": {
            "name": "habitation_claims_image_schema",
            "description": "Schema pour l'analyse de photos de dommages habitation",
            "fields": {
                "PhotoType": {
                    "type": "string",
                    "method": "classify",
                    "description": "Type de dommage visible sur la photo",
                    "enum": [
                        "Dégâts des eaux",
                        "Dommages tempête",
                        "Incendie",
                        "Vol",
                        "Bris de glace",
                        "Effondrement",
                        "Autre",
                    ],
                },
                "AffectedArea": {
                    "type": "string",
                    "method": "generate",
                    "description": "Zone du logement affectée (cave, sous-sol, rez-de-chaussée, cuisine, chambre, salle de bain, etc.)",
                },
                "DamageSeverity": {
                    "type": "string",
                    "method": "classify",
                    "description": "Niveau de gravité des dommages visibles",
                    "enum": ["Mineur", "Modéré", "Important", "Critique"],
                },
                "DamageDescription": {
                    "type": "string",
                    "method": "generate",
                    "description": "Description détaillée des dommages visibles sur la photo (1-3 phrases)",
                },
                "AffectedMaterials": {
                    "type": "string",
                    "method": "generate",
                    "description": "Matériaux ou éléments endommagés (cloisons, plafond, murs, mobilier, revêtements, etc.)",
                },
                "WaterLevel": {
                    "type": "string",
                    "method": "generate",
                    "description": "Hauteur approximative d'eau si dégâts des eaux (ex: jusqu'aux chevilles, à hauteur de genou, plus haut)",
                },
                "VisibleContamination": {
                    "type": "string",
                    "method": "classify",
                    "description": "Contamination visible (boue, moisissure, débris, cendres, etc.)",
                    "enum": ["Aucune", "Légère", "Modérée", "Importante"],
                },
                "PreexistingDamage": {
                    "type": "string",
                    "method": "classify",
                    "description": "Bien y a-t-il des dommages préexistants visibles sur la photo (fissures, taches, usure, etc.)",
                    "enum": ["Aucun", "Possible", "Probable", "Certain"],
                },
                "PhotoQuality": {
                    "type": "string",
                    "method": "classify",
                    "description": "Qualité de la photo pour l'évaluation des sinistres",
                    "enum": ["Mauvaise", "Acceptable", "Bonne", "Excellente"],
                },
                "EstimatedRepairCostRange": {
                    "type": "string",
                    "method": "classify",
                    "description": "Fourchette estimée du coût de réparation basée sur les dommages visibles",
                    "enum": ["< 500 EUR", "500-2000 EUR", "2000-5000 EUR", "5000-10000 EUR", "> 10000 EUR"],
                },
            },
        },
    },
}

HEALTH_UNDERWRITING_ANALYZER = {
    "analyzerId": "healthUnderwritingAnalyzer",
    "body": {
        "baseAnalyzerId": "prebuilt-document",
        "description": "Analyseur de souscription complementaire sante - questionnaire de sante, antecedents medicaux",
        "config": {
            "returnDetails": True,
        },
        "fieldSchema": {
            "name": "health_underwriting_schema",
            "description": "Schema pour les demandes de souscription complementaire sante",
            "fields": {
                "NomSouscripteur": {
                    "type": "string",
                    "method": "extract",
                    "description": "Nom et prenom du souscripteur",
                },
                "DateNaissance": {
                    "type": "date",
                    "method": "extract",
                    "description": "Date de naissance du souscripteur",
                },
                "Age": {
                    "type": "number",
                    "method": "extract",
                    "description": "Age du souscripteur en annees",
                },
                "Profession": {
                    "type": "string",
                    "method": "extract",
                    "description": "Profession du souscripteur",
                },
                "EmailSouscripteur": {
                    "type": "string",
                    "method": "extract",
                    "description": "Adresse email du souscripteur",
                },
                "NumeroSecuriteSociale": {
                    "type": "string",
                    "method": "extract",
                    "description": "Numero de securite sociale",
                },
                "FormuleDemandee": {
                    "type": "string",
                    "method": "extract",
                    "description": "Formule de complementaire sante demandee (Equilibre Plus, Confort, etc.)",
                },
                "CotisationMensuelle": {
                    "type": "number",
                    "method": "extract",
                    "description": "Cotisation mensuelle estimee en euros",
                },
                "Taille": {
                    "type": "string",
                    "method": "extract",
                    "description": "Taille du souscripteur (en cm)",
                },
                "Poids": {
                    "type": "string",
                    "method": "extract",
                    "description": "Poids du souscripteur (en kg)",
                },
                "IMC": {
                    "type": "number",
                    "method": "extract",
                    "description": "Indice de Masse Corporelle",
                },
                "StatutTabac": {
                    "type": "string",
                    "method": "classify",
                    "description": "Statut tabagique du souscripteur",
                    "enum": ["Non-fumeur", "Ancien fumeur", "Fumeur actif"],
                },
                "TraitementEnCours": {
                    "type": "string",
                    "method": "extract",
                    "description": "Traitement medicamenteux en cours (nom du medicament, posologie)",
                },
                "PathologieDeclaree": {
                    "type": "string",
                    "method": "generate",
                    "description": "Resume des pathologies declarees par le souscripteur (hypertension, diabete, etc.)",
                },
                "AntecedentsFamiliaux": {
                    "type": "string",
                    "method": "generate",
                    "description": "Resume des antecedents medicaux familiaux significatifs",
                },
                "AllergiesConnues": {
                    "type": "string",
                    "method": "extract",
                    "description": "Allergies connues du souscripteur",
                },
                "Hospitalisations": {
                    "type": "string",
                    "method": "extract",
                    "description": "Historique des hospitalisations (dates, raisons)",
                },
                "NiveauRisque": {
                    "type": "string",
                    "method": "classify",
                    "description": "Niveau de risque global du profil medical",
                    "enum": ["Faible", "Modere", "Eleve", "Tres eleve"],
                },
                "ResumeQuestionnaireSante": {
                    "type": "string",
                    "method": "generate",
                    "description": "Resume complet du questionnaire de sante en 5-8 phrases, identifiant les facteurs de risque principaux et les points d'attention pour le souscripteur",
                },
            },
        },
    },
}


def create_analyzer(settings, analyzer_def):
    """Create a single analyzer via REST API."""
    analyzer_id = analyzer_def["analyzerId"]
    body = analyzer_def["body"]

    endpoint = settings.content_understanding.endpoint.rstrip("/")
    url = f"{endpoint}/contentunderstanding/analyzers/{analyzer_id}"
    params = {"api-version": settings.content_understanding.api_version}

    _, headers = _get_auth_token_and_headers(settings.content_understanding)
    headers["Content-Type"] = "application/json"

    # Check if already exists
    existing = get_analyzer(settings.content_understanding, analyzer_id)
    if existing:
        logger.info(f"  Analyzer '{analyzer_id}' already exists — deleting for update...")
        del_resp = requests.delete(url, params=params, headers=headers, timeout=30)
        _raise_for_status_with_detail(del_resp)
        time.sleep(2)

    # Create
    logger.info(f"  Creating analyzer '{analyzer_id}'...")
    resp = requests.put(url, params=params, headers=headers, json=body, timeout=60)
    _raise_for_status_with_detail(resp)

    # Poll until ready
    if resp.status_code == 201:
        result = poll_result(resp, headers, timeout_seconds=120)
        logger.info(f"  Analyzer '{analyzer_id}' created successfully")
        return result
    else:
        logger.info(f"  Analyzer '{analyzer_id}' created (HTTP {resp.status_code})")
        return resp.json()


def main():
    settings = load_settings()

    if not settings.content_understanding.endpoint:
        logger.error("AZURE_CONTENT_UNDERSTANDING_ENDPOINT not set")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("WorkbenchIQ — Content Understanding Analyzer Setup")
    logger.info(f"Endpoint: {settings.content_understanding.endpoint}")
    logger.info("=" * 60)

    for analyzer_def in [HABITATION_ANALYZER, HABITATION_CLAIMS_IMAGE_ANALYZER, HEALTH_UNDERWRITING_ANALYZER]:
        aid = analyzer_def["analyzerId"]
        field_count = len(analyzer_def["body"]["fieldSchema"]["fields"])
        logger.info(f"\n>>> {aid} ({field_count} fields)")
        try:
            create_analyzer(settings, analyzer_def)
        except Exception as e:
            logger.error(f"  Failed: {e}")

    logger.info("\n" + "=" * 60)
    logger.info("Setup complete")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
