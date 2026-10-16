"""Seed data for 3 claims applications (1 health + 2 automotive).

Provides rich, realistic data matching French insurance scenarios (PrevaIQ demo brand).
Uses PRV-xxx customer references (Customer 360 seed data).
"""

from typing import Any, Dict, List


def _garcia_antonio_auto() -> Dict[str, Any]:
    """PRV-007 GARCIA Antonio — collision arrière mineure à Toulouse, tiers responsable."""
    return {
        "id": "app-sc-auto-001",
        "created_at": "2024-11-18T14:32:00Z",
        "external_reference": "PRV-007",
        "status": "completed",
        "persona": "automotive_claims",
        "files": [
            {"filename": "constat_amiable.pdf", "path": "applications/app-sc-auto-001/constat_amiable.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "rapport_police.pdf", "path": "applications/app-sc-auto-001/rapport_police.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_pare_chocs_arriere.jpg", "path": "applications/app-sc-auto-001/photo_pare_chocs_arriere.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "photo_coffre.jpg", "path": "applications/app-sc-auto-001/photo_coffre.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "devis_reparation.pdf", "path": "applications/app-sc-auto-001/devis_reparation.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "damage_assessment": {
                "visual_damage_analysis": {
                    "section": "damage_assessment",
                    "subsection": "visual_damage_analysis",
                    "raw": (
                        "Véhicule assuré : Renault Clio V (2021), photographié au garage AD "
                        "Toulouse Sud. Impact localisé à l'arrière du véhicule. Le pare-chocs arrière "
                        "présente une déformation modérée avec fissuration le long du bord inférieur "
                        "et un transfert de peinture du véhicule percuteur. Le coffre montre un léger "
                        "flambage sur le bord arrière avec écaillage mineur de peinture. Aucune intrusion "
                        "structurelle dans l'habitacle. Feux arrière intacts. Système d'échappement intact."
                    ),
                    "parsed": {
                        "summary": "Dommages modérés par impact arrière, limités au pare-chocs et au coffre. Cohérent avec une collision à basse vitesse.",
                        "overall_severity": "moderate",
                        "damage_areas": [
                            {"location": "Pare-chocs arrière", "severity": "moderate", "description": "Déformation et fissuration le long du bord inférieur avec transfert de peinture", "estimated_cost": 850.00, "confidence": 0.92},
                            {"location": "Coffre", "severity": "minor", "description": "Léger flambage sur le bord arrière avec écaillage de peinture ; mécanisme de verrouillage fonctionnel", "estimated_cost": 620.00, "confidence": 0.89},
                            {"location": "Traverse arrière", "severity": "minor", "description": "Légère flexion détectée ; remplacement recommandé", "estimated_cost": 430.00, "confidence": 0.85},
                        ],
                        "total_damage_estimate": 1900.00,
                        "airbag_deployment": False,
                        "vehicle_drivable": True,
                        "recommended_action": "Approuver la réparation",
                    },
                },
                "estimate_validation": {
                    "section": "damage_assessment",
                    "subsection": "estimate_validation",
                    "raw": (
                        "Devis du garage AD Toulouse Sud vérifié par rapport aux barèmes PrevaIQ. "
                        "Le tarif des pièces pour Renault Clio V — pare-chocs arrière, traverse et "
                        "coffre — est conforme aux prix catalogue constructeur. La main-d'œuvre de "
                        "6,5 heures correspond aux standards du métier pour démontage/remontage du "
                        "pare-chocs, remise en état et remplacement du coffre. L'allocation peinture "
                        "et matériaux est raisonnable. Aucune substitution de pièces adaptables notée."
                    ),
                    "parsed": {
                        "summary": "Devis conforme aux barèmes pour les réparations décrites sur une Renault Clio V 2021.",
                        "estimate_id": "DEV-AG-2024-0472",
                        "parts_breakdown": 1050.00,
                        "labor_hours": 6.5,
                        "labor_rate_per_hour": 72.00,
                        "labor_cost": 468.00,
                        "sublet_items": [],
                        "paint_materials": 382.00,
                        "estimate_accuracy": "Conforme",
                        "comparison_market": "Dans la fourchette du marché",
                        "recommended_action": "Approuver",
                    },
                },
            },
            "liability_assessment": {
                "fault_determination": {
                    "section": "liability_assessment",
                    "subsection": "fault_determination",
                    "raw": (
                        "Le constat amiable n° CA-2024-TLS-88214 confirme que le véhicule assuré "
                        "était à l'arrêt au feu rouge à l'intersection de l'avenue Jean Jaurès et "
                        "de la rue de Metz à Toulouse lorsqu'il a été percuté par l'arrière par un "
                        "Peugeot 308 (2019). Deux témoins indépendants corroborent que le conducteur "
                        "tiers n'a pas freiné à temps. Le tiers est déclaré entièrement responsable."
                    ),
                    "parsed": {
                        "summary": "Responsabilité claire : assuré 0 % ; tiers 100 % responsable, confirmé par constat amiable et témoignages.",
                        "fault_determination": "0 % — tiers 100 % responsable",
                        "fault_percentage": 0,
                        "contributing_factors": ["Tiers suivant de trop près", "Tiers n'a pas respecté la distance de sécurité"],
                        "liability_risk": "Responsabilité claire",
                        "rationale": "L'assuré était immobilisé au feu rouge. Le tiers l'a percuté par l'arrière.",
                    },
                },
            },
            "fraud_detection": {
                "red_flag_analysis": {
                    "section": "fraud_detection",
                    "subsection": "red_flag_analysis",
                    "raw": (
                        "Aucun indicateur de fraude détecté pour ce sinistre. Le schéma de dommages "
                        "est entièrement cohérent avec la collision arrière décrite. La déclaration "
                        "a été rapide (le jour même). Le constat amiable est conforme et corrobore "
                        "le récit de l'assuré. Aucun antécédent préoccupant. Le devis est dans "
                        "les normes du marché. Aucun lien entre les parties identifié."
                    ),
                    "parsed": {
                        "summary": "Aucun indicateur de fraude. Circonstances, dommages et documentation cohérents et crédibles.",
                        "red_flags": [],
                        "fraud_risk": "Faible",
                        "fraud_score": 0.08,
                        "recommended_action": "Poursuivre le traitement du sinistre",
                    },
                },
            },
            "payout_recommendation": {
                "settlement_analysis": {
                    "section": "payout_recommendation",
                    "subsection": "settlement_analysis",
                    "raw": (
                        "Indemnisation recommandée de 1 900 € pour réparation du pare-chocs arrière, "
                        "de la traverse et du coffre. L'assuré bénéficie d'une franchise de 300 € ; "
                        "cependant, comme il est 0 % responsable, un recours sera engagé contre "
                        "l'assureur du tiers (MAIF, police n° MAIF-2019-337841) pour récupérer "
                        "l'intégralité de l'indemnisation plus la franchise. Aucun dommage corporel."
                    ),
                    "parsed": {
                        "summary": "Approuver l'indemnisation de 1 900 €. Recours contre l'assureur du tiers.",
                        "recommended_amount": 1900.00,
                        "deductible": 300.00,
                        "insured_responsibility": 0.00,
                        "subrogation_target": "MAIF — police MAIF-2019-337841",
                        "final_approval": True,
                        "rationale": "Assuré non responsable. Dommages vérifiés, devis conforme. Recours engagé pour récupération intégrale.",
                        "policy_citations": [
                            {"policy_id": "AC-PRV-001", "title": "Conditions Générales Auto PrevaIQ — Art. 8.2", "section": "Garantie Dommages Collision", "text": "Prise en charge des dommages matériels en cas de collision avec un tiers identifié, sous déduction de la franchise contractuelle.", "relevance": 0.95},
                            {"policy_id": "AC-PRV-002", "title": "Conditions Générales Auto PrevaIQ — Art. 12.1", "section": "Recours et Subrogation", "text": "L'assureur exerce un recours contre le tiers responsable ou son assureur pour le montant des indemnités versées.", "relevance": 0.92},
                        ],
                    },
                },
            },
        },
        "extracted_fields": {
            "constat:NumeroSinistre": {"field_name": "NumeroSinistre", "value": "SIN-AG-241118-01", "confidence": 0.95, "source_file": "constat_amiable.pdf"},
            "constat:NumeroPolice": {"field_name": "NumeroPolice", "value": "AUTO-PRV-7724519", "confidence": 0.97, "source_file": "constat_amiable.pdf"},
            "constat:NomAssure": {"field_name": "NomAssure", "value": "GARCIA Antonio", "confidence": 0.98, "source_file": "constat_amiable.pdf"},
            "constat:DateSinistre": {"field_name": "DateSinistre", "value": "15/11/2024", "confidence": 0.96, "source_file": "constat_amiable.pdf"},
            "DateDeclaration": {"value": "18/11/2024", "confidence": 0.97},
            "DateCloture": {"value": "20/12/2024", "confidence": 0.95},
            "constat:AnneeVehicule": {"field_name": "AnneeVehicule", "value": "2021", "confidence": 0.97, "source_file": "constat_amiable.pdf"},
            "constat:MarqueVehicule": {"field_name": "MarqueVehicule", "value": "Renault", "confidence": 0.96, "source_file": "constat_amiable.pdf"},
            "constat:ModeleVehicule": {"field_name": "ModeleVehicule", "value": "Clio V", "confidence": 0.96, "source_file": "constat_amiable.pdf"},
            "constat:Immatriculation": {"field_name": "Immatriculation", "value": "FG-472-MK", "confidence": 0.93, "source_file": "constat_amiable.pdf"},
            "constat:DescriptionDommages": {"field_name": "DescriptionDommages", "value": "Dommages pare-chocs arrière et coffre suite à collision arrière", "confidence": 0.92, "source_file": "constat_amiable.pdf"},
            "devis:MontantReparation": {"field_name": "MontantReparation", "value": "1900.00", "confidence": 0.95, "source_file": "devis_reparation.pdf"},
            "rapport:NumeroRapport": {"field_name": "NumeroRapport", "value": "PV-2024-TLS-88214", "confidence": 0.94, "source_file": "rapport_police.pdf"},
            "rapport:AssureurTiers": {"field_name": "AssureurTiers", "value": "MAIF", "confidence": 0.91, "source_file": "rapport_police.pdf"},
        },
        "confidence_summary": {
            "total_fields": 12,
            "average_confidence": 0.95,
            "high_confidence_count": 11,
            "medium_confidence_count": 1,
            "low_confidence_count": 0,
            "high_confidence_fields": [
                {"name": "constat:NomAssure", "confidence": 0.98},
                {"name": "constat:NumeroPolice", "confidence": 0.97},
                {"name": "constat:AnneeVehicule", "confidence": 0.97},
                {"name": "constat:MarqueVehicule", "confidence": 0.96},
                {"name": "constat:ModeleVehicule", "confidence": 0.96},
                {"name": "constat:DateSinistre", "confidence": 0.96},
                {"name": "constat:NumeroSinistre", "confidence": 0.95},
                {"name": "devis:MontantReparation", "confidence": 0.95},
                {"name": "rapport:NumeroRapport", "confidence": 0.94},
                {"name": "constat:Immatriculation", "confidence": 0.93},
                {"name": "constat:DescriptionDommages", "confidence": 0.92},
            ],
            "medium_confidence_fields": [
                {"name": "rapport:AssureurTiers", "confidence": 0.91},
            ],
            "low_confidence_fields": [],
        },
    }


def _rousseau_marc_health() -> Dict[str, Any]:
    """PRV-017 ROUSSEAU Marc — hospitalisation genou, actes chirurgicaux remboursés."""
    return {
        "id": "app-mw-hc-001",
        "created_at": "2024-07-10T09:15:00Z",
        "external_reference": "PRV-017",
        "status": "completed",
        "persona": "life_health_claims",
        "files": [
            {"filename": "declaration_sinistre_sante.pdf", "path": "applications/app-mw-hc-001/declaration_sinistre_sante.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "decompte_securite_sociale.pdf", "path": "applications/app-mw-hc-001/decompte_securite_sociale.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "compte_rendu_chirurgical.pdf", "path": "applications/app-mw-hc-001/compte_rendu_chirurgical.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "facture_hospitalisation.pdf", "path": "applications/app-mw-hc-001/facture_hospitalisation.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "clinical_case_notes": {
                "reason_for_visit": {
                    "section": "clinical_case_notes",
                    "subsection": "reason_for_visit",
                    "raw": (
                        "ROUSSEAU Marc, 66 ans, adressé au Dr Laurent MICHAUD (chirurgie orthopédique, "
                        "CHU de Tours) le 15/05/2024 pour gonarthrose invalidante du genou droit. "
                        "Douleurs progressives depuis 2 ans, limitation fonctionnelle croissante à la "
                        "marche (< 500 m), escaliers impossibles. Traitements conservateurs épuisés : "
                        "infiltrations corticoïdes (x3), kinésithérapie (30 séances), antalgiques "
                        "palier II. IRM confirmant arthrose fémoro-tibiale médiale stade IV Kellgren-Lawrence. "
                        "Indication chirurgicale retenue : prothèse totale de genou droit."
                    ),
                    "parsed": {
                        "summary": "Patient adressé pour chirurgie prothétique du genou droit suite à gonarthrose invalidante.",
                        "chief_complaint": "Gonarthrose invalidante du genou droit avec limitation fonctionnelle majeure",
                        "symptom_duration": "Progressive sur 2 ans",
                        "severity": "Sévère",
                        "urgency": "Programmée",
                        "history_of_present_illness": (
                            "Homme de 66 ans avec gonarthrose stade IV Kellgren-Lawrence du genou droit. "
                            "Traitements conservateurs épuisés (infiltrations x3, kiné 30 séances, antalgiques "
                            "palier II). Limitation de marche < 500 m, escaliers impossibles. "
                            "Indication de prothèse totale de genou retenue en RCP."
                        ),
                    },
                },
                "key_diagnoses": {
                    "section": "clinical_case_notes",
                    "subsection": "key_diagnoses",
                    "raw": (
                        "Diagnostic principal : gonarthrose primitive du genou droit, stade IV "
                        "Kellgren-Lawrence avec pincement complet de l'interligne fémoro-tibiale médiale. "
                        "Comorbidités : hypertension artérielle traitée (amlodipine 5 mg), diabète de type 2 "
                        "équilibré (metformine 1000 mg x2/j, HbA1c 6,8 %). Codes CIM-10 : M17.1 (gonarthrose "
                        "primitive), I10 (HTA), E11.9 (diabète type 2)."
                    ),
                    "parsed": {
                        "summary": "Gonarthrose primitive sévère du genou droit. Comorbidités contrôlées (HTA, diabète type 2).",
                        "primary_diagnosis": "M17.1 — Gonarthrose primitive du genou droit",
                        "secondary_diagnoses": ["I10 — Hypertension artérielle essentielle", "E11.9 — Diabète de type 2"],
                        "diagnosis_consistency": "Oui",
                        "coding_accuracy": "Conforme",
                    },
                },
                "medical_necessity": {
                    "section": "clinical_case_notes",
                    "subsection": "medical_necessity",
                    "raw": (
                        "Tous les actes réalisés sont médicalement justifiés compte tenu du tableau "
                        "clinique. L'arthrose stade IV avec épuisement des traitements conservateurs "
                        "constitue une indication chirurgicale validée par la HAS. La consultation "
                        "pré-anesthésique était requise (ASA II). L'hospitalisation de 5 jours est "
                        "conforme aux durées moyennes de séjour (DMS) pour PTG. La rééducation "
                        "post-opératoire de 20 séances est dans les recommandations HAS."
                    ),
                    "parsed": {
                        "summary": "Tous les actes médicalement nécessaires conformément aux recommandations HAS.",
                        "necessity_determination": "Nécessaire",
                        "clinical_rationale": (
                            "Gonarthrose stade IV avec échec des traitements conservateurs. "
                            "Indication chirurgicale validée par la HAS. Hospitalisation conforme "
                            "à la DMS nationale. Rééducation dans les recommandations."
                        ),
                        "services_reviewed": [
                            {"service": "Consultation orthopédique", "code": "CCAM NZQK001", "necessity_status": "Nécessaire", "rationale": "Bilan pré-opératoire et pose d'indication chirurgicale"},
                            {"service": "Consultation pré-anesthésique", "code": "CCAM ZZQM006", "necessity_status": "Nécessaire", "rationale": "Patient ASA II (HTA + diabète), anesthésie générale prévue"},
                            {"service": "Prothèse totale de genou", "code": "CCAM NFKA007", "necessity_status": "Nécessaire", "rationale": "Gonarthrose stade IV, traitements conservateurs épuisés"},
                            {"service": "Hospitalisation 5 jours", "code": "GHS 3682", "necessity_status": "Nécessaire", "rationale": "Conforme à la DMS nationale pour PTG"},
                            {"service": "Rééducation (20 séances)", "code": "CCAM NZRB001", "necessity_status": "Nécessaire", "rationale": "Protocole post-PTG recommandé par la HAS"},
                        ],
                        "documentation_quality": "Complète",
                        "recommended_action": "Approuver tous les actes",
                    },
                },
            },
            "clinical_timeline": {
                "treatment_timeline": {
                    "section": "clinical_timeline",
                    "subsection": "treatment_timeline",
                    "raw": (
                        "Parcours de soins sur 60 jours. 15/05/2024 : consultation orthopédique "
                        "initiale, IRM confirmant indication chirurgicale. 22/05/2024 : consultation "
                        "pré-anesthésique, bilan sanguin pré-opératoire. 03/06/2024 : admission CHU "
                        "Tours, pose PTG genou droit sous AG. 04-07/06/2024 : hospitalisation, "
                        "rééducation initiale. 08/06/2024 : sortie, transfert SSR. 10/06-15/07/2024 : "
                        "20 séances de rééducation en centre SSR Touraine."
                    ),
                    "parsed": {
                        "summary": "Parcours chirurgical complet sur 60 jours avec suites opératoires conformes.",
                        "timeline_events": [
                            {"date": "2024-05-15", "event": "Consultation orthopédique initiale", "event_type": "visit", "description": "Bilan clinique et IRM, indication PTG retenue", "duration_days": 0},
                            {"date": "2024-05-22", "event": "Consultation pré-anesthésique", "event_type": "visit", "description": "Bilan pré-opératoire, patient ASA II", "duration_days": 7},
                            {"date": "2024-06-03", "event": "Chirurgie PTG genou droit", "event_type": "procedure", "description": "Pose de prothèse totale de genou sous anesthésie générale", "duration_days": 19},
                            {"date": "2024-06-08", "event": "Sortie d'hospitalisation", "event_type": "visit", "description": "Sortie J+5, transfert en SSR", "duration_days": 24},
                            {"date": "2024-07-15", "event": "Fin de rééducation", "event_type": "visit", "description": "20 séances de kinésithérapie, récupération fonctionnelle satisfaisante", "duration_days": 61},
                        ],
                        "total_duration": 61,
                        "treatment_pattern": "Chirurgie programmée + rééducation",
                    },
                },
            },
            "benefits_policy": {
                "eligibility_verification": {
                    "section": "benefits_policy",
                    "subsection": "eligibility_verification",
                    "raw": (
                        "Adhérent ROUSSEAU Marc (n° adhérent PRV-SANTE-17892) vérifié comme actif "
                        "au titre du contrat collectif Complémentaire Santé PrevaIQ Vitalia (n° groupe "
                        "PRV-COL-6621). Contrat en vigueur depuis le 20/01/2003, sans date de résiliation. "
                        "Tous les soins dispensés par des praticiens conventionnés secteur 1. Aucune "
                        "coordination inter-mutuelles requise. Cotisations à jour."
                    ),
                    "parsed": {
                        "summary": "Adhérent éligible pour l'ensemble des prestations demandées.",
                        "eligibility_status": "Éligible",
                        "member_info": {"name": "ROUSSEAU Marc", "member_id": "PRV-SANTE-17892", "group": "PRV-COL-6621"},
                        "coverage_dates": {"effective_date": "2003-01-20", "termination_date": "2025-12-31"},
                        "plan_details": {"plan_name": "PrevaIQ Vitalia Confort+", "plan_type": "Complémentaire Santé", "network_status": "Conventionné Secteur 1"},
                        "eligibility_issues": [],
                        "processing_action": "Poursuivre",
                    },
                },
                "exclusions_limitations": {
                    "section": "benefits_policy",
                    "subsection": "exclusions_limitations",
                    "raw": (
                        "Aucune exclusion ou limitation applicable à ce sinistre. Les actes "
                        "chirurgicaux orthopédiques sont couverts au titre de la garantie hospitalisation. "
                        "La gonarthrose a été diagnostiquée bien après l'adhésion (2003). Pas de "
                        "délai de carence applicable. Pas de dépassements d'honoraires (secteur 1)."
                    ),
                    "parsed": {
                        "summary": "Aucune exclusion ni limitation applicable.",
                        "applicable_exclusions": [],
                        "pre_existing_review": "Non applicable — pathologie déclarée en cours de contrat",
                        "waiting_periods": "Aucun applicable",
                        "processing_action": "Approuver",
                    },
                },
                "benefit_limits": {
                    "section": "benefits_policy",
                    "subsection": "benefit_limits",
                    "raw": (
                        "L'adhérent a utilisé 2 hospitalisations sur un maximum annuel de 5. "
                        "Plafond annuel de remboursement de 50 000 € avec 3 240 € utilisés avant "
                        "ce sinistre. Franchise annuelle de 150 € déjà atteinte. Plafond optique/dentaire "
                        "non concerné. Tous les actes sont dans les limites de garantie."
                    ),
                    "parsed": {
                        "summary": "Tous les actes dans les limites de garantie.",
                        "applicable_limits": {"max_hospitalizations": 5, "max_amount": 50000},
                        "deductible_status": "Franchise annuelle atteinte",
                        "oop_maximum": 2500,
                        "limit_concerns": [],
                        "processing_action": "Approuver",
                    },
                },
            },
            "claim_line_evaluation": {
                "line_item_review": {
                    "section": "claim_line_evaluation",
                    "subsection": "line_item_review",
                    "raw": (
                        "Cinq lignes de prestations examinées. Tous les codes CCAM sont appropriés "
                        "pour les actes documentés. La consultation orthopédique (C2 + MPC) est "
                        "justifiée par la complexité du cas. La PTG (NFKA007) et l'hospitalisation "
                        "(GHS 3682) sont des actes distincts. Le bilan pré-anesthésique (ZZQM006) "
                        "est conforme. La rééducation (20 × NZRB001) est dans les recommandations HAS. "
                        "Montants réduits aux tarifs conventionnels Sécurité sociale, complément "
                        "pris en charge par la mutuelle à 100 % du TM."
                    ),
                    "parsed": {
                        "summary": "5 lignes de prestations examinées et approuvées.",
                        "total_billed": 8450.00,
                        "total_allowed": 7200.00,
                        "total_plan_pays": 2160.00,
                        "total_member_pays": 0.00,
                        "claim_lines": [
                            {"line_num": 1, "description": "Consultation orthopédique spécialisée", "code": "CCAM C2+MPC", "billed": "350,00 €", "allowed": "300,00 €", "plan_pays": "90,00 €", "member_pays": "0,00 €", "status": "Approuvé"},
                            {"line_num": 2, "description": "Consultation pré-anesthésique", "code": "CCAM ZZQM006", "billed": "120,00 €", "allowed": "100,00 €", "plan_pays": "30,00 €", "member_pays": "0,00 €", "status": "Approuvé"},
                            {"line_num": 3, "description": "Prothèse totale de genou", "code": "CCAM NFKA007", "billed": "4 800,00 €", "allowed": "4 200,00 €", "plan_pays": "1 260,00 €", "member_pays": "0,00 €", "status": "Approuvé"},
                            {"line_num": 4, "description": "Hospitalisation 5 jours (GHS)", "code": "GHS 3682", "billed": "2 380,00 €", "allowed": "2 000,00 €", "plan_pays": "600,00 €", "member_pays": "0,00 €", "status": "Approuvé"},
                            {"line_num": 5, "description": "Rééducation (20 séances kiné)", "code": "CCAM NZRB001", "billed": "800,00 €", "allowed": "600,00 €", "plan_pays": "180,00 €", "member_pays": "0,00 €", "status": "Approuvé"},
                        ],
                        "coding_issues": [],
                        "bundling_flags": [],
                        "recommended_action": "Approuver toutes les lignes",
                    },
                },
            },
            "tasks_decisions": {
                "final_decision": {
                    "section": "tasks_decisions",
                    "subsection": "final_decision",
                    "raw": (
                        "Sinistre SIN-MR-240710-01 approuvé en totalité. Les cinq lignes de "
                        "prestations sont médicalement justifiées, correctement codifiées et dans "
                        "les garanties du contrat. L'adhérent est éligible et les praticiens sont "
                        "conventionnés secteur 1. Aucune exclusion applicable. Part mutuelle de "
                        "2 160,00 € à verser au CHU de Tours. Reste à charge adhérent : 0,00 €. "
                        "Décompte à adresser à l'adhérent sous 5 jours ouvrés."
                    ),
                    "parsed": {
                        "summary": "Sinistre approuvé en totalité. Tous les actes médicalement justifiés et dans les garanties.",
                        "decision": "Approuvé",
                        "decision_rationale": (
                            "Tous les actes sont médicalement nécessaires pour un patient de 66 ans "
                            "présentant une gonarthrose stade IV avec échec des traitements conservateurs. "
                            "Codification conforme, pas de problème de cumul, praticiens conventionnés. "
                            "Adhérent éligible, franchise atteinte."
                        ),
                        "payment_summary": {"total_plan_pays": 2160.00, "total_member_pays": 0.00, "deductible_applied": 0},
                        "denial_reasons": [],
                        "pend_reasons": [],
                        "appeal_rights": "L'adhérent peut contester dans les 30 jours suivant le décompte",
                        "next_steps": ["Virement au CHU de Tours", "Envoi du décompte à l'adhérent"],
                        "reviewer_notes": "Documentation complète. Parcours de soins conforme aux recommandations HAS.",
                    },
                },
            },
        },
        "extracted_fields": {
            "declaration:NumeroSinistre": {"field_name": "NumeroSinistre", "value": "SIN-MR-240710-01", "confidence": 0.96, "source_file": "declaration_sinistre_sante.pdf"},
            "declaration:NomAdherent": {"field_name": "NomAdherent", "value": "ROUSSEAU Marc", "confidence": 0.98, "source_file": "declaration_sinistre_sante.pdf"},
            "declaration:NumeroAdherent": {"field_name": "NumeroAdherent", "value": "PRV-SANTE-17892", "confidence": 0.97, "source_file": "declaration_sinistre_sante.pdf"},
            "declaration:NumeroGroupe": {"field_name": "NumeroGroupe", "value": "PRV-COL-6621", "confidence": 0.96, "source_file": "declaration_sinistre_sante.pdf"},
            "declaration:NomContrat": {"field_name": "NomContrat", "value": "PrevaIQ Vitalia Confort+", "confidence": 0.95, "source_file": "declaration_sinistre_sante.pdf"},
            "compte_rendu:CodeDiagnostic": {"field_name": "CodeDiagnostic", "value": "M17.1", "confidence": 0.97, "source_file": "compte_rendu_chirurgical.pdf"},
            "compte_rendu:DescriptionDiagnostic": {"field_name": "DescriptionDiagnostic", "value": "Gonarthrose primitive du genou droit", "confidence": 0.94, "source_file": "compte_rendu_chirurgical.pdf"},
            "facture:DateDebut": {"field_name": "DateDebut", "value": "03/06/2024", "confidence": 0.96, "source_file": "facture_hospitalisation.pdf"},
            "facture:DateFin": {"field_name": "DateFin", "value": "08/06/2024", "confidence": 0.95, "source_file": "facture_hospitalisation.pdf"},
            "facture:MontantTotal": {"field_name": "MontantTotal", "value": "8450.00", "confidence": 0.97, "source_file": "facture_hospitalisation.pdf"},
            "facture:NomEtablissement": {"field_name": "NomEtablissement", "value": "CHU de Tours — Service Orthopédie", "confidence": 0.93, "source_file": "facture_hospitalisation.pdf"},
            "decompte:PartSecu": {"field_name": "PartSecu", "value": "5040.00", "confidence": 0.96, "source_file": "decompte_securite_sociale.pdf"},
            "decompte:PartMutuelle": {"field_name": "PartMutuelle", "value": "2160.00", "confidence": 0.96, "source_file": "decompte_securite_sociale.pdf"},
            "decompte:ResteACharge": {"field_name": "ResteACharge", "value": "0.00", "confidence": 0.95, "source_file": "decompte_securite_sociale.pdf"},
            "compte_rendu:Chirurgien": {"field_name": "Chirurgien", "value": "Dr Laurent MICHAUD, CHU Tours", "confidence": 0.94, "source_file": "compte_rendu_chirurgical.pdf"},
            "compte_rendu:ProcedureCodes": {"field_name": "ProcedureCodes", "value": [
                {"valueObject": {"code": {"valueString": "CCAM NFKA007", "confidence": 0.96}, "description": {"valueString": "Prothèse totale de genou"}}},
                {"valueObject": {"code": {"valueString": "CCAM ZZQM006", "confidence": 0.93}, "description": {"valueString": "Consultation pré-anesthésique"}}},
                {"valueObject": {"code": {"valueString": "CCAM NZRB001", "confidence": 0.91}, "description": {"valueString": "Rééducation fonctionnelle"}}},
            ], "confidence": 0.94, "source_file": "compte_rendu_chirurgical.pdf"},
            "DateDeclaration": {"value": "10/07/2024", "confidence": 0.97},
            "DateCloture": {"value": "15/09/2024", "confidence": 0.95},
        },
        "confidence_summary": {
            "total_fields": 15,
            "average_confidence": 0.95,
            "high_confidence_count": 13,
            "medium_confidence_count": 2,
            "low_confidence_count": 0,
            "high_confidence_fields": [
                {"name": "declaration:NomAdherent", "confidence": 0.98},
                {"name": "declaration:NumeroAdherent", "confidence": 0.97},
                {"name": "facture:MontantTotal", "confidence": 0.97},
                {"name": "compte_rendu:CodeDiagnostic", "confidence": 0.97},
                {"name": "declaration:NumeroSinistre", "confidence": 0.96},
                {"name": "declaration:NumeroGroupe", "confidence": 0.96},
                {"name": "facture:DateDebut", "confidence": 0.96},
                {"name": "decompte:PartSecu", "confidence": 0.96},
                {"name": "decompte:PartMutuelle", "confidence": 0.96},
                {"name": "declaration:NomContrat", "confidence": 0.95},
                {"name": "facture:DateFin", "confidence": 0.95},
                {"name": "decompte:ResteACharge", "confidence": 0.95},
                {"name": "compte_rendu:ProcedureCodes", "confidence": 0.94},
            ],
            "medium_confidence_fields": [
                {"name": "compte_rendu:DescriptionDiagnostic", "confidence": 0.94},
                {"name": "facture:NomEtablissement", "confidence": 0.93},
            ],
            "low_confidence_fields": [],
        },
    }


def _arnaud_thierry_auto() -> Dict[str, Any]:
    """PRV-025 ARNAUD Thierry — collision frontale majeure, risque de fraude, enquête SIU."""
    return {
        "id": "app-pp-auto-001",
        "created_at": "2024-12-03T11:48:00Z",
        "external_reference": "PRV-025",
        "status": "under_investigation",
        "persona": "automotive_claims",
        "files": [
            {"filename": "constat_amiable.pdf", "path": "applications/app-pp-auto-001/constat_amiable.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_dommages_avant.jpg", "path": "applications/app-pp-auto-001/photo_dommages_avant.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "photo_dommages_lateral.jpg", "path": "applications/app-pp-auto-001/photo_dommages_lateral.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "devis_reparation.pdf", "path": "applications/app-pp-auto-001/devis_reparation.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "facture_remorquage.pdf", "path": "applications/app-pp-auto-001/facture_remorquage.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "damage_assessment": {
                "visual_damage_analysis": {
                    "section": "damage_assessment",
                    "subsection": "visual_damage_analysis",
                    "raw": (
                        "Véhicule assuré : BMW Série 3 320d (2022), photographié au garage Prestige "
                        "Carrosserie Nancy. Dommages frontaux significatifs : pare-chocs avant détruit, "
                        "calandre brisée, capot plié avec déformation en V profonde. Traverse avant "
                        "repoussée d'environ 15 cm. Les deux blocs optiques fissurés. Ailes avant "
                        "présentant des plis de contrainte. À noter : rayures et oxydation préexistantes "
                        "sur l'aile avant gauche et la portière conducteur — incohérent avec un véhicule "
                        "de 2022 dans l'état déclaré. Le montant A côté droit semble intact, ce qui "
                        "est inhabituel compte tenu du scénario d'évitement déclaré."
                    ),
                    "parsed": {
                        "summary": "Dommages frontaux majeurs sur BMW Série 3. Le schéma de dommages soulève des interrogations — impact frontal direct incohérent avec la manœuvre d'évitement déclarée. Usure préexistante sur panneaux adjacents.",
                        "overall_severity": "severe",
                        "damage_areas": [
                            {"location": "Pare-chocs avant", "severity": "severe", "description": "Complètement détruit ; plastique fragmenté et détaché des points de fixation", "estimated_cost": 2800.00, "confidence": 0.88},
                            {"location": "Capot", "severity": "severe", "description": "Déformation en V profonde indiquant impact frontal direct ; décollement peinture aux pliures", "estimated_cost": 3200.00, "confidence": 0.86},
                            {"location": "Calandre et traverse avant", "severity": "severe", "description": "Calandre brisée ; traverse repoussée d'environ 15 cm vers l'arrière", "estimated_cost": 4500.00, "confidence": 0.84},
                            {"location": "Blocs optiques", "severity": "moderate", "description": "Les deux blocs fissurés ; optique gauche partiellement délogée", "estimated_cost": 1800.00, "confidence": 0.87},
                            {"location": "Ailes avant", "severity": "moderate", "description": "Plis de contrainte des deux côtés ; rayures et oxydation préexistantes sur aile gauche incohérentes avec l'âge du véhicule", "estimated_cost": 2200.00, "confidence": 0.79},
                            {"location": "Portière conducteur", "severity": "minor", "description": "Rayures et oxydation préexistantes — non cohérentes avec un véhicule de 2022", "estimated_cost": 0.00, "confidence": 0.72},
                        ],
                        "total_damage_estimate": 14500.00,
                        "airbag_deployment": False,
                        "vehicle_drivable": False,
                        "recommended_action": "Suspendre pour enquête SIU — incohérences dans le schéma de dommages",
                    },
                },
                "estimate_validation": {
                    "section": "damage_assessment",
                    "subsection": "estimate_validation",
                    "raw": (
                        "Devis du garage Prestige Carrosserie Nancy totalisant 14 500 €. Les tarifs "
                        "pièces OEM pour BMW Série 3 sont dans la fourchette haute mais conformes aux "
                        "prix catalogue BMW. La main-d'œuvre à 35 heures est à la limite supérieure "
                        "pour l'étendue des dommages documentés. Plusieurs postes nécessitent "
                        "des éclaircissements : le devis inclut un raccord peinture sur les panneaux "
                        "arrière qui ne sont pas adjacents à la zone d'impact. Peinture et matériaux "
                        "à 2 200 € dépassant la fourchette habituelle pour une remise en état frontale."
                    ),
                    "parsed": {
                        "summary": "Devis dans la fourchette haute. Plusieurs postes nécessitent justification.",
                        "estimate_id": "DEV-AT-2024-0891",
                        "parts_breakdown": 7800.00,
                        "labor_hours": 35,
                        "labor_rate_per_hour": 85.00,
                        "labor_cost": 2975.00,
                        "sublet_items": ["Equilibrage/géométrie : 350 €"],
                        "paint_materials": 2200.00,
                        "estimate_accuracy": "Fourchette haute — justification requise",
                        "comparison_market": "Au-dessus de la médiane",
                        "recommended_action": "Demander justification avant approbation",
                    },
                },
            },
            "liability_assessment": {
                "fault_determination": {
                    "section": "liability_assessment",
                    "subsection": "fault_determination",
                    "raw": (
                        "Le constat amiable rapporte que l'assuré a effectué une manœuvre d'évitement "
                        "sur la RN57 près de Nancy pour éviter un animal traversant la chaussée. "
                        "Le véhicule aurait percuté un poteau en béton. Aucun témoin indépendant. "
                        "L'absence de traces de freinage et le schéma de dommages (impact frontal "
                        "direct) sont difficiles à concilier avec un scénario d'évitement latéral. "
                        "Les dommages préexistants sur l'aile gauche questionnent l'état antérieur "
                        "du véhicule."
                    ),
                    "parsed": {
                        "summary": "Responsabilité contestée. Le scénario déclaré est incohérent avec les constatations physiques.",
                        "fault_determination": "En cours d'investigation",
                        "fault_percentage": 100,
                        "contributing_factors": [
                            "Aucun témoin indépendant",
                            "Absence de traces de freinage",
                            "Schéma de dommages incohérent avec le scénario déclaré",
                            "Dommages préexistants sur panneaux adjacents",
                        ],
                        "liability_risk": "Investigation requise",
                        "rationale": "Le schéma de dommages frontaux directs est incohérent avec une manœuvre d'évitement latéral.",
                    },
                },
            },
            "fraud_detection": {
                "red_flag_analysis": {
                    "section": "fraud_detection",
                    "subsection": "red_flag_analysis",
                    "raw": (
                        "Plusieurs indicateurs de fraude détectés. 1) Dommages préexistants sur "
                        "un véhicule de 2022 : rayures et oxydation de l'aile gauche et de la portière "
                        "incompatibles avec l'âge du véhicule. 2) Non-déploiement des airbags malgré "
                        "un impact frontal sévère avec traverse repoussée de 15 cm. 3) Incohérence "
                        "entre le scénario déclaré (évitement) et le schéma de dommages (impact "
                        "frontal direct). 4) Historique de sinistres multiples de l'assuré (3 sinistres "
                        "en 2 ans sur 2 véhicules différents). 5) Le devis inclut des réparations hors "
                        "zone d'impact (raccord peinture arrière). Transfert recommandé au Service "
                        "Investigation et Fraude (SIF)."
                    ),
                    "parsed": {
                        "summary": "5 indicateurs de fraude majeurs détectés. Transfert au SIF recommandé.",
                        "red_flags": [
                            {"category": "vehicle_condition", "indicator": "Dommages préexistants (rayures, oxydation) incohérents avec l'âge du véhicule (2022)", "severity": "high"},
                            {"category": "damage_pattern", "indicator": "Non-déploiement airbags malgré impact frontal sévère (traverse 15 cm)", "severity": "high"},
                            {"category": "scenario_inconsistency", "indicator": "Impact frontal direct incohérent avec manœuvre d'évitement déclarée", "severity": "high"},
                            {"category": "claims_history", "indicator": "3 sinistres en 2 ans sur 2 véhicules — fréquence anormale", "severity": "medium"},
                            {"category": "estimate_padding", "indicator": "Devis inclut réparations hors zone d'impact (raccord peinture arrière)", "severity": "medium"},
                        ],
                        "fraud_risk": "Élevé",
                        "fraud_score": 0.82,
                        "recommended_action": "Transférer au Service Investigation et Fraude (SIF)",
                    },
                },
            },
            "payout_recommendation": {
                "settlement_analysis": {
                    "section": "payout_recommendation",
                    "subsection": "settlement_analysis",
                    "raw": (
                        "Suspension de l'indemnisation recommandée en attendant les résultats de "
                        "l'enquête SIF. Le montant demandé de 14 500 € est dans la fourchette haute "
                        "et comporte des postes discutables. Expertise contradictoire recommandée. "
                        "Si le sinistre est confirmé, l'indemnisation devrait être limitée aux dommages "
                        "directement liés à l'accident, excluant les dommages préexistants et les "
                        "réparations hors zone d'impact. Franchise de 600 € applicable (malus suite "
                        "aux sinistres précédents)."
                    ),
                    "parsed": {
                        "summary": "Indemnisation suspendue. Expertise contradictoire et enquête SIF requises.",
                        "recommended_amount": 0.00,
                        "deductible": 600.00,
                        "insured_responsibility": 14500.00,
                        "subrogation_target": "Aucun — sinistre sans tiers identifié",
                        "final_approval": False,
                        "rationale": "Multiples incohérences détectées. Enquête SIF en cours. Expertise contradictoire mandatée.",
                        "policy_citations": [
                            {"policy_id": "AC-PRV-010", "title": "Conditions Générales Auto PrevaIQ — Art. 15.3", "section": "Fraude et fausse déclaration", "text": "En cas de fausse déclaration ou de fraude avérée, l'assureur peut refuser l'indemnisation et résilier le contrat.", "relevance": 0.97},
                            {"policy_id": "AC-PRV-011", "title": "Conditions Générales Auto PrevaIQ — Art. 9.1", "section": "Expertise contradictoire", "text": "L'assureur peut mandater un expert pour vérifier les circonstances du sinistre et le montant des dommages.", "relevance": 0.94},
                            {"policy_id": "AC-PRV-012", "title": "Conditions Générales Auto PrevaIQ — Art. 8.5", "section": "Exclusion dommages préexistants", "text": "Les dommages préexistants au sinistre sont exclus de l'indemnisation.", "relevance": 0.91},
                        ],
                    },
                },
            },
        },
        "extracted_fields": {
            "constat:NumeroSinistre": {"field_name": "NumeroSinistre", "value": "SIN-AT-241203-01", "confidence": 0.95, "source_file": "constat_amiable.pdf"},
            "constat:NumeroPolice": {"field_name": "NumeroPolice", "value": "AUTO-PRV-2538714", "confidence": 0.93, "source_file": "constat_amiable.pdf"},
            "constat:NomAssure": {"field_name": "NomAssure", "value": "ARNAUD Thierry", "confidence": 0.97, "source_file": "constat_amiable.pdf"},
            "constat:DateSinistre": {"field_name": "DateSinistre", "value": "01/12/2024", "confidence": 0.94, "source_file": "constat_amiable.pdf"},
            "constat:AnneeVehicule": {"field_name": "AnneeVehicule", "value": "2022", "confidence": 0.96, "source_file": "constat_amiable.pdf"},
            "constat:MarqueVehicule": {"field_name": "MarqueVehicule", "value": "BMW", "confidence": 0.97, "source_file": "constat_amiable.pdf"},
            "constat:ModeleVehicule": {"field_name": "ModeleVehicule", "value": "Série 3 320d", "confidence": 0.95, "source_file": "constat_amiable.pdf"},
            "constat:Immatriculation": {"field_name": "Immatriculation", "value": "GH-892-LP", "confidence": 0.91, "source_file": "constat_amiable.pdf"},
            "constat:Circonstances": {"field_name": "Circonstances", "value": "Manœuvre d'évitement d'un animal sur RN57 — impact poteau béton", "confidence": 0.88, "source_file": "constat_amiable.pdf"},
            "devis:MontantReparation": {"field_name": "MontantReparation", "value": "14500.00", "confidence": 0.94, "source_file": "devis_reparation.pdf"},
            "remorquage:Montant": {"field_name": "Montant", "value": "285.00", "confidence": 0.92, "source_file": "facture_remorquage.pdf"},
            "remorquage:Societe": {"field_name": "Societe", "value": "Lorraine Dépannage Auto", "confidence": 0.65, "source_file": "facture_remorquage.pdf"},
            "DateDeclaration": {"value": "03/12/2024", "confidence": 0.96},
        },
        "confidence_summary": {
            "total_fields": 12,
            "average_confidence": 0.92,
            "high_confidence_count": 8,
            "medium_confidence_count": 3,
            "low_confidence_count": 1,
            "high_confidence_fields": [
                {"name": "constat:NomAssure", "confidence": 0.97},
                {"name": "constat:MarqueVehicule", "confidence": 0.97},
                {"name": "constat:AnneeVehicule", "confidence": 0.96},
                {"name": "constat:NumeroSinistre", "confidence": 0.95},
                {"name": "constat:ModeleVehicule", "confidence": 0.95},
                {"name": "devis:MontantReparation", "confidence": 0.94},
                {"name": "constat:DateSinistre", "confidence": 0.94},
                {"name": "constat:NumeroPolice", "confidence": 0.93},
            ],
            "medium_confidence_fields": [
                {"name": "remorquage:Montant", "confidence": 0.92},
                {"name": "constat:Immatriculation", "confidence": 0.91},
                {"name": "constat:Circonstances", "confidence": 0.88},
            ],
            "low_confidence_fields": [
                {"name": "remorquage:Societe", "confidence": 0.65},
            ],
        },
    }


def _girard_laurent_habitation() -> Dict[str, Any]:
    """PRV-013 GIRARD Laurent — habitation tempête février 2024 à Versailles."""
    return {
        "id": "app-house-hab-001",
        "created_at": "2024-02-15T09:30:00Z",
        "external_reference": "PRV-013",
        "status": "completed",
        "persona": "habitation_claims",
        "files": [
            {"filename": "declaration_sinistre.pdf", "path": "applications/app-house-hab-001/declaration_sinistre.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "attestation_tempete.pdf", "path": "applications/app-house-hab-001/attestation_tempete.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_toiture.jpg", "path": "applications/app-house-hab-001/photo_toiture.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "photo_tuiles_endommagees.jpg", "path": "applications/app-house-hab-001/photo_tuiles_endommagees.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "rapport_expert.pdf", "path": "applications/app-house-hab-001/rapport_expert.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "extraction_summary": {
                "document_analysis": {
                    "section": "extraction_summary",
                    "raw": (
                        "Dossier sinistre habitation : tempête du 12 février 2024 à Versailles. "
                        "Dégâts à la toiture avec tuiles endommagées et infiltration d'eau. "
                        "Expert mobilisé le 13 février. Assuré Laurent GIRARD, police MRH-PRV-001245."
                    ),
                    "parsed": {
                        "summary": "Tempête habitation 12/02/2024 — dégâts toiture — couvert par contrat MRH",
                        "nature_sinistre": "Tempête",
                        "date_sinistre": "12/02/2024",
                        "lieu_sinistre": "22 chemin de Ronde, 78000 Versailles",
                        "assuré": "GIRARD Laurent",
                        "numero_police": "MRH-PRV-001245",
                        "montant_estime": "8500€",
                    },
                },
            },
            "alert_signals": {
                "weather_analysis": {
                    "section": "alert_signals",
                    "raw": "Tempête avec vents > 100 km/h attestée par Météo-France. Alerte tempête active.",
                    "parsed": {
                        "alert_type": "Tempête",
                        "severity": "high",
                        "indicators": ["Vents violents > 100 km/h", "Certificat Météo-France"],
                        "policy_coverage": "Couverte sous HAB-TMP-001",
                        "confidence": 0.98,
                    },
                },
            },
            "timeline": {
                "event_sequence": {
                    "section": "timeline",
                    "raw": "12/02 14:30 tempête observée, 13/02 09:00 appel assuré, 13/02 14:00 visite expert",
                    "parsed": [
                        {
                            "date": "12/02/2024 14:30",
                            "event": "Tempête observée — premiers dégâts constatés",
                            "source": "déclaration_assuré",
                        },
                        {
                            "date": "12/02/2024 18:00",
                            "event": "Infiltration d'eau constatée dans salon",
                            "source": "rapport_expert",
                        },
                        {
                            "date": "13/02/2024 09:00",
                            "event": "Appel assureur — sinistre déclaré",
                            "source": "declaration_sinistre",
                        },
                        {
                            "date": "13/02/2024 14:00",
                            "event": "Expert mobilisé sur site",
                            "source": "rapport_expert",
                        },
                    ],
                },
            },
            "responsibility_evaluation": {
                "coverage_determination": {
                    "section": "responsibility_evaluation",
                    "raw": (
                        "Sinistre causé par tempête couverte sous la clause HAB-TMP-001. "
                        "Assuré n'a pas commis de faute. Couverture complète recommandée."
                    ),
                    "parsed": {
                        "is_covered": True,
                        "confidence": 0.96,
                        "policy_id": "HAB-TMP-001",
                        "policy_name": "Couverture Tempête",
                        "reason": "Tempête couverte sans franchise spéciale tempête",
                        "franchise": "300€ franchise standard",
                        "applicable_clauses": [
                            "Art. 5.2 : Garantie Dommages Tempête",
                            "Art. 8.1 : Franchise Standard",
                        ],
                    },
                },
            },
        },
        "extracted_fields": {
            "AssuréNom": {"field_name": "AssuréNom", "value": "GIRARD Laurent", "confidence": 0.99, "source_file": "declaration_sinistre.pdf"},
            "DateSinistre": {"field_name": "DateSinistre", "value": "12/02/2024", "confidence": 0.97, "source_file": "declaration_sinistre.pdf"},
            "NatureSinistre": {"field_name": "NatureSinistre", "value": "Tempête", "confidence": 0.98, "source_file": "attestation_tempete.pdf"},
            "LieuSinistre": {"field_name": "LieuSinistre", "value": "22 chemin de Ronde, 78000 Versailles", "confidence": 0.96, "source_file": "declaration_sinistre.pdf"},
            "NumeroPolice": {"field_name": "NumeroPolice", "value": "MRH-PRV-001245", "confidence": 0.99, "source_file": "declaration_sinistre.pdf"},
            "DescriptionSinistre": {"field_name": "DescriptionSinistre", "value": "Dégâts à la toiture avec tuiles endommagées suite à tempête, infiltrations d'eau", "confidence": 0.94, "source_file": "declaration_sinistre.pdf"},
            "MontantEstime": {"field_name": "MontantEstime", "value": "8500€", "confidence": 0.87, "source_file": "rapport_expert.pdf"},
            "DateConstat": {"field_name": "DateConstat", "value": "13/02/2024", "confidence": 0.98, "source_file": "rapport_expert.pdf"},
            "DateDeclaration": {"value": "15/02/2024", "confidence": 0.97},
            "DateCloture": {"value": "18/04/2024", "confidence": 0.96},
        },
        "confidence_summary": {
            "total_fields": 8,
            "average_confidence": 0.96,
            "high_confidence_count": 7,
            "medium_confidence_count": 1,
            "high_confidence_fields": [
                {"name": "AssuréNom", "confidence": 0.99},
                {"name": "NumeroPolice", "confidence": 0.99},
                {"name": "DateSinistre", "confidence": 0.97},
                {"name": "NatureSinistre", "confidence": 0.98},
                {"name": "DateConstat", "confidence": 0.98},
                {"name": "LieuSinistre", "confidence": 0.96},
                {"name": "DescriptionSinistre", "confidence": 0.94},
            ],
            "medium_confidence_fields": [
                {"name": "MontantEstime", "confidence": 0.87},
            ],
        },
    }


# =========================================================================
# Additional Sinistres Santé — 4 more apps to reach 5 total
# =========================================================================

def _petit_sophie_health() -> Dict[str, Any]:
    """PRV-004 PETIT Sophie — remboursement optique, lunettes progressives."""
    return {
        "id": "app-hc-002",
        "created_at": "2025-09-22T10:30:00Z",
        "external_reference": "PRV-004",
        "status": "completed",
        "persona": "life_health_claims",
        "files": [
            {"filename": "facture_opticien.pdf", "path": "applications/app-hc-002/facture_opticien.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "ordonnance_ophtalmo.pdf", "path": "applications/app-hc-002/ordonnance_ophtalmo.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview", "raw": "Mme PETIT Sophie, 57 ans, retraitée à Aix-en-Provence. Demande de remboursement pour lunettes progressives. Ordonnance Dr Faure du 15/09/2025 : correction OD +2.50 / OG +2.75, addition +2.00. Facture Optic 2000 Aix : 485€ (verres progressifs Essilor 320€ + monture 165€). Contrat PrevaIQ Santé Sérénité depuis 2008 — forfait optique annuel 300€.", "parsed": {"summary": "Remboursement optique — lunettes progressives Essilor", "claim_amount": 485.00, "policy_coverage": 300.00, "ss_reimbursement": 7.10, "net_assureur": 292.90, "patient_reste": 185.00, "status": "conforme"}}},
            "coverage_check": {"policy_match": {"section": "coverage_check", "subsection": "policy_match", "raw": "Contrat Sérénité couvre optique jusqu'à 300€/an. Dernier remboursement optique : mars 2023 (>2 ans). Éligibilité renouvellement confirmée selon réforme 100% Santé.", "parsed": {"eligible": True, "plafond": 300.00, "last_claim_date": "2023-03-15", "waiting_period_met": True}}},
        },
        "extracted_fields": {"beneficiaire": {"value": "PETIT Sophie", "confidence": 0.97}, "montant_facture": {"value": "485,00 €", "confidence": 0.98}, "acte": {"value": "Lunettes progressives + monture", "confidence": 0.95}, "DateDeclaration": {"value": "22/09/2025", "confidence": 0.97}, "DateCloture": {"value": "06/10/2025", "confidence": 0.96}},
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
    }


def _dubois_philippe_health() -> Dict[str, Any]:
    """PRV-009 DUBOIS Philippe — hospitalisation cardiaque, pose de stent."""
    return {
        "id": "app-hc-003",
        "created_at": "2025-11-05T08:45:00Z",
        "external_reference": "PRV-009",
        "status": "completed",
        "persona": "life_health_claims",
        "files": [
            {"filename": "compte_rendu_hospitalisation.pdf", "path": "applications/app-hc-003/compte_rendu_hospitalisation.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "facture_clinique.pdf", "path": "applications/app-hc-003/facture_clinique.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "decompte_secu.pdf", "path": "applications/app-hc-003/decompte_secu.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview", "raw": "M. DUBOIS Philippe, 65 ans, hospitalisé du 28/10 au 02/11/2025 à la Clinique Saint-Louis Strasbourg. Motif : angor instable. Acte : coronarographie + pose de stent actif (DES). Séjour 5 nuits en chambre particulière. Facture clinique : 8 420€. Décompte Sécurité Sociale : 6 230€ remboursés (74% tarif convention). Reste à charge avant mutuelle : 2 190€. Contrat PrevaIQ Santé Plus — hospitalisation 100% BR + chambre particulière 80€/j (5 × 80 = 400€).", "parsed": {"summary": "Hospitalisation cardiaque — coronarographie + stent DES", "claim_amount": 8420.00, "ss_reimbursement": 6230.00, "complement_assureur": 2190.00, "chambre_particuliere": 400.00, "total_assureur": 2590.00, "duree_sejour": 5, "status": "conforme"}}},
        },
        "extracted_fields": {"beneficiaire": {"value": "DUBOIS Philippe", "confidence": 0.98}, "etablissement": {"value": "Clinique Saint-Louis Strasbourg", "confidence": 0.96}, "montant_total": {"value": "8 420,00 €", "confidence": 0.99}, "acte_ccam": {"value": "DDAF006 — Dilatation coronaire + pose endoprothèse", "confidence": 0.93}, "DateDeclaration": {"value": "05/11/2025", "confidence": 0.98}, "DateCloture": {"value": "10/12/2025", "confidence": 0.96}},
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
    }


def _fontaine_aurelie_health() -> Dict[str, Any]:
    """PRV-016 FONTAINE Aurélie — maternité, forfait naissance."""
    return {
        "id": "app-hc-004",
        "created_at": "2026-01-20T14:00:00Z",
        "external_reference": "PRV-016",
        "status": "completed",
        "persona": "life_health_claims",
        "files": [
            {"filename": "certificat_accouchement.pdf", "path": "applications/app-hc-004/certificat_accouchement.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "facture_maternite.pdf", "path": "applications/app-hc-004/facture_maternite.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview", "raw": "Mme FONTAINE Aurélie, 32 ans. Accouchement le 15/01/2026 à l'Hôpital Femme Mère Enfant Lyon (voie basse, sans complication). Séjour 3 nuits. Facture maternité : 3 200€. SS rembourse 2 880€ (prise en charge à 100% maternité). Complément chambre individuelle : 120€ (3 × 40€). Forfait naissance PrevaIQ : 500€ (prime de naissance contractuelle).", "parsed": {"summary": "Maternité — accouchement + forfait naissance", "claim_amount": 3200.00, "ss_reimbursement": 2880.00, "forfait_naissance": 500.00, "complement_chambre": 120.00, "total_assureur": 940.00, "status": "conforme"}}},
        },
        "extracted_fields": {"beneficiaire": {"value": "FONTAINE Aurélie", "confidence": 0.99}, "date_accouchement": {"value": "15/01/2026", "confidence": 0.98}, "etablissement": {"value": "Hôpital Femme Mère Enfant Lyon", "confidence": 0.97}, "DateDeclaration": {"value": "20/01/2026", "confidence": 0.98}, "DateCloture": {"value": "05/02/2026", "confidence": 0.97}},
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
    }


def _moreau_isabelle_health() -> Dict[str, Any]:
    """PRV-006 MOREAU Isabelle — soins dentaires, couronne + bridge (devis préalable)."""
    return {
        "id": "app-hc-005",
        "created_at": "2026-03-05T11:15:00Z",
        "external_reference": "PRV-006",
        "status": "pending_review",
        "persona": "life_health_claims",
        "files": [
            {"filename": "devis_dentaire.pdf", "path": "applications/app-hc-005/devis_dentaire.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "panoramique_dentaire.jpg", "path": "applications/app-hc-005/panoramique_dentaire.jpg", "content_type": "image/jpeg", "media_type": "image"},
        ],
        "llm_outputs": {
            "claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview", "raw": "Mme MOREAU Isabelle, 53 ans, Paris 8e. Devis préalable Dr Blanchard (chirurgien-dentiste). Couronne céramo-métallique dent 16 : 650€. Bridge 3 éléments (14-15-16) : 1 950€. Total devis : 2 600€. Base de remboursement SS : 107,50€ × 3 = 322,50€ remboursé à 70% = 225,75€. Reste : 2 374,25€. Contrat PrevaIQ Santé Plus — dentaire 200% BR = 645€ max PrevaIQ.", "parsed": {"summary": "Dentaire — couronne + bridge 3 éléments (devis préalable)", "claim_amount": 2600.00, "ss_base": 322.50, "ss_reimbursement": 225.75, "assureur_200pc_br": 645.00, "patient_reste": 1729.25, "status": "devis_prealable"}}},
        },
        "extracted_fields": {"beneficiaire": {"value": "MOREAU Isabelle", "confidence": 0.98}, "praticien": {"value": "Dr Blanchard — Paris 8e", "confidence": 0.95}, "montant_devis": {"value": "2 600,00 €", "confidence": 0.99}, "DateDeclaration": {"value": "05/03/2026", "confidence": 0.98}},
        "risk_analysis": {"risk_level": "low", "decision": "conditions", "fraud_indicators": []},
    }


# =========================================================================
# Additional Sinistres Auto — 3 more apps to reach 5 total
# =========================================================================

def _bernard_thomas_auto() -> Dict[str, Any]:
    """PRV-003 BERNARD Thomas — accrochage parking Lyon, jeune conducteur."""
    return {
        "id": "app-auto-003",
        "created_at": "2025-06-12T16:20:00Z",
        "external_reference": "PRV-003",
        "status": "completed",
        "persona": "automotive_claims",
        "files": [
            {"filename": "constat_amiable.pdf", "path": "applications/app-auto-003/constat_amiable.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_aile_droite.jpg", "path": "applications/app-auto-003/photo_aile_droite.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "devis_carrosserie.pdf", "path": "applications/app-auto-003/devis_carrosserie.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "damage_assessment": {"visual_damage_analysis": {"section": "damage_assessment", "subsection": "visual_damage_analysis", "raw": "Véhicule assuré : Peugeot 208 (2023), immatriculée FS-234-AB. Accrochage en marche arrière au parking du centre commercial La Part-Dieu, Lyon. Rayure profonde aile avant droite (40 cm) avec enfoncement léger + déformation pare-chocs avant droit. Peinture arrachée jusqu'au métal. Responsabilité 100% assuré (case 15 constat amiable — marche arrière). Véhicule tiers : Renault Twingo stationné, aile AR gauche rayée. Devis Carrosserie Lyonnaise : 980€.", "parsed": {"summary": "Accrochage parking — rayure profonde aile droite + pare-chocs", "overall_severity": "minor", "total_damage_estimate": 980.00, "vehicle_drivable": True, "liability": "100% assuré", "recommended_action": "Approuver — appliquer franchise"}}},
            "liability_assessment": {"fault_determination": {"section": "liability_assessment", "subsection": "fault_determination", "raw": "Constat amiable signé des deux parties. Case 15 cochée (marche arrière). Article IRSA : responsabilité entière du véhicule en marche arrière. Bonus-malus actuel : 0.50 (jeune conducteur 3e année). Impact : +0.125 → nouveau CRM 0.625.", "parsed": {"liability": "100% assuré", "fault_code": "case_15", "conventional_rule": "IRSA art.15 — véhicule en recul", "crm_before": 0.50, "crm_after": 0.625}}},
        },
        "extracted_fields": {"assure": {"value": "BERNARD Thomas", "confidence": 0.97}, "vehicule": {"value": "Peugeot 208 (2023)", "confidence": 0.96}, "montant_devis": {"value": "980,00 €", "confidence": 0.98}, "DateDeclaration": {"value": "12/06/2025", "confidence": 0.97}, "DateCloture": {"value": "28/06/2025", "confidence": 0.96}},
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
    }


def _lefebvre_nathalie_auto() -> Dict[str, Any]:
    """PRV-010 LEFEBVRE Nathalie — bris de glace pare-brise A1 Lille–Paris."""
    return {
        "id": "app-auto-004",
        "created_at": "2025-10-08T09:00:00Z",
        "external_reference": "PRV-010",
        "status": "completed",
        "persona": "automotive_claims",
        "files": [
            {"filename": "declaration_bris_glace.pdf", "path": "applications/app-auto-004/declaration_bris_glace.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "facture_carglass.pdf", "path": "applications/app-auto-004/facture_carglass.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "damage_assessment": {"visual_damage_analysis": {"section": "damage_assessment", "subsection": "visual_damage_analysis", "raw": "Véhicule assuré : Citroën C3 Aircross (2020), immatriculée EK-567-CD. Impact gravillons sur autoroute A1 Lille–Paris le 05/10/2025 km 178. Éclat pare-brise côté conducteur avec fissuration progressive (30 cm en 3 jours). Remplacement complet pare-brise athermique. Intervention Carglass Lille Euralille. Facture : 620€ TTC. Garantie bris de glace sans franchise (contrat tous risques PrevaIQ).", "parsed": {"summary": "Bris de glace pare-brise — impact gravillons autoroute, remplacement Carglass", "overall_severity": "minor", "total_damage_estimate": 620.00, "franchise": 0.00, "recommended_action": "Prise en charge directe réseau Carglass"}}},
        },
        "extracted_fields": {"assure": {"value": "LEFEBVRE Nathalie", "confidence": 0.98}, "vehicule": {"value": "Citroën C3 Aircross (2020)", "confidence": 0.97}, "montant_facture": {"value": "620,00 €", "confidence": 0.99}, "DateDeclaration": {"value": "08/10/2025", "confidence": 0.98}, "DateCloture": {"value": "22/10/2025", "confidence": 0.97}},
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
    }


def _roux_frederic_auto() -> Dict[str, Any]:
    """PRV-011 ROUX Frédéric — vol Golf retrouvé endommagé, enquête SIU."""
    return {
        "id": "app-auto-005",
        "created_at": "2026-02-18T07:30:00Z",
        "external_reference": "PRV-011",
        "status": "under_investigation",
        "persona": "automotive_claims",
        "files": [
            {"filename": "depot_plainte.pdf", "path": "applications/app-auto-005/depot_plainte.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_vehicule_retrouve.jpg", "path": "applications/app-auto-005/photo_vehicule_retrouve.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "rapport_expert.pdf", "path": "applications/app-auto-005/rapport_expert.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {
            "damage_assessment": {"visual_damage_analysis": {"section": "damage_assessment", "subsection": "visual_damage_analysis", "raw": "Véhicule assuré : Volkswagen Golf 8 GTD (2021), immatriculée FT-890-EF. Déclaré volé le 15/02/2026 à Bordeaux (6 rue Victor Hugo, domicile de l'assuré). Retrouvé le 17/02 à Mérignac, parking zone industrielle, abandonné. Dommages constatés : colonne de direction forcée, barillet serrure conducteur arraché, neiman cassé. Compteur +550 km en 2 jours. Rayures multiples carrosserie. Intérieur souillé (mégots, canettes). Rapport expert Mondéal : réparations estimées 4 800€. Point d'attention : aucune trace de bris de vitre — mode d'effraction indéterminé.", "parsed": {"summary": "Vol véhicule retrouvé endommagé — expertise + enquête SIU", "overall_severity": "significant", "total_damage_estimate": 4800.00, "vehicle_drivable": False, "fraud_flags": ["Aucun bris de vitre malgré vol déclaré", "Compteur +550 km en 2 jours", "Véhicule retrouvé à 15 km du domicile"], "recommended_action": "Enquête SIU — demander géolocalisation GPS assureur"}}},
        },
        "extracted_fields": {"assure": {"value": "ROUX Frédéric", "confidence": 0.97}, "vehicule": {"value": "Volkswagen Golf 8 GTD (2021)", "confidence": 0.98}, "date_vol": {"value": "15/02/2026", "confidence": 0.96}, "lieu_vol": {"value": "6 rue Victor Hugo, 33000 Bordeaux", "confidence": 0.94}, "DateDeclaration": {"value": "18/02/2026", "confidence": 0.97}},
        "risk_analysis": {"risk_level": "high", "decision": "investigate", "fraud_indicators": ["Absence de bris de vitre", "Kilométrage suspect (+550 km)", "Véhicule retrouvé intact hormis colonne direction"]},
    }


# =========================================================================
# Additional seed dossiers — Auto (3 new)
# =========================================================================

def _vincent_emilie_auto() -> Dict[str, Any]:
    return {
        "id": "app-auto-006", "created_at": "2025-08-14T11:00:00Z",
        "external_reference": "PRV-018", "status": "completed",
        "persona": "automotive_claims",
        "files": [{"filename": "constat_amiable.pdf", "path": "applications/app-auto-006/constat_amiable.pdf", "content_type": "application/pdf", "media_type": "document"}],
        "llm_outputs": {"damage_assessment": {"visual_damage_analysis": {"section": "damage_assessment", "subsection": "visual_damage_analysis",
            "raw": "Véhicule assuré : Toyota Yaris Cross (2023), immatriculée GH-123-IJ. Accrochage sur la Promenade des Anglais, Nice. Rayure portière passager + rétroviseur cassé. Tiers identifié. Devis Carrosserie Azur : 1 350€.",
            "parsed": {"summary": "Accrochage latéral Promenade des Anglais — rayure portière + rétroviseur", "overall_severity": "minor", "total_damage_estimate": 1350.00, "vehicle_drivable": True, "liability": "tiers 100%", "recommended_action": "Approuver + recours tiers"}}}},
        "extracted_fields": {"assure": {"value": "VINCENT Émilie", "confidence": 0.97}, "vehicule": {"value": "Toyota Yaris Cross (2023)", "confidence": 0.98}, "montant_devis": {"value": "1 350,00 €", "confidence": 0.98}, "DateDeclaration": {"value": "14/08/2025", "confidence": 0.97}, "DateCloture": {"value": "20/09/2025", "confidence": 0.96}},
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 3, "average_confidence": 0.98, "high_confidence_count": 3},
    }


def _fournier_camille_auto() -> Dict[str, Any]:
    return {
        "id": "app-auto-007", "created_at": "2025-12-01T08:30:00Z",
        "external_reference": "PRV-012", "status": "error",
        "persona": "automotive_claims",
        "files": [{"filename": "declaration_sinistre.pdf", "path": "applications/app-auto-007/declaration_sinistre.pdf", "content_type": "application/pdf", "media_type": "document"}],
        "llm_outputs": {},
        "extracted_fields": {},
        "risk_analysis": {"risk_level": "unknown", "decision": "retry"},
        "confidence_summary": {"total_fields": 0, "average_confidence": 0.0, "high_confidence_count": 0},
        "processing_error": "Erreur extraction : document numérisé illisible (résolution < 150 DPI). Veuillez rescanner en 300 DPI.",
    }


def _renard_christophe_auto() -> Dict[str, Any]:
    return {
        "id": "app-auto-008", "created_at": "2026-03-22T15:45:00Z",
        "external_reference": "PRV-023", "status": "pending",
        "persona": "automotive_claims",
        "files": [{"filename": "declaration_flotte.pdf", "path": "applications/app-auto-008/declaration_flotte.pdf", "content_type": "application/pdf", "media_type": "document"}, {"filename": "photos_dommages.zip", "path": "applications/app-auto-008/photos_dommages.zip", "content_type": "application/zip", "media_type": "document"}],
        "llm_outputs": {"damage_assessment": {"visual_damage_analysis": {"section": "damage_assessment", "subsection": "visual_damage_analysis",
            "raw": "Véhicule flotte : Renault Kangoo (2022) immatriculée HJ-456-KL. Collision en marche arrière lors de livraison. Pare-chocs arrière + feux de recul. Contrat flotte PrevaIQ PRO. Devis initial : 1 680€. En attente validation responsable flotte.",
            "parsed": {"summary": "Sinistre flotte — Kangoo livraison, collision marche arrière", "overall_severity": "minor", "total_damage_estimate": 1680.00, "vehicle_drivable": True, "liability": "100% assuré", "recommended_action": "En attente approbation responsable"}}}},
        "extracted_fields": {"assure": {"value": "RENARD Christophe (flotte SARL Renard Transport)", "confidence": 0.96}, "vehicule": {"value": "Renault Kangoo (2022)", "confidence": 0.97}, "montant_devis": {"value": "1 680,00 €", "confidence": 0.97}, "DateDeclaration": {"value": "22/03/2026", "confidence": 0.97}},
        "risk_analysis": {"risk_level": "low", "decision": "pending_approval", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 3, "average_confidence": 0.97, "high_confidence_count": 3},
    }


# =========================================================================
# Additional seed dossiers — Health (3 new)
# =========================================================================

def _picard_delphine_health() -> Dict[str, Any]:
    return {
        "id": "app-hc-006", "created_at": "2025-11-15T09:20:00Z",
        "external_reference": "PRV-026", "status": "completed",
        "persona": "life_health_claims",
        "files": [{"filename": "facture_dentiste.pdf", "path": "applications/app-hc-006/facture_dentiste.pdf", "content_type": "application/pdf", "media_type": "document"}],
        "llm_outputs": {"claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview",
            "raw": "Mme PICARD Delphine, 31 ans. Soins dentaires conservateurs : 2 caries composites + détartrage. Cabinet Dr. Bourgeois, Grenoble. Facture : 195€. SS rembourse 70% BR = 45,15€. PrevaIQ complète 100% BR = 64,50€ PrevaIQ. Reste : 85,35€ patient.",
            "parsed": {"summary": "Soins dentaires conservateurs — 2 composites + détartrage", "claim_amount": 195.00, "ss_reimbursement": 45.15, "complement_assureur": 64.50, "patient_reste": 85.35, "status": "conforme"}}}},
        "extracted_fields": {"beneficiaire": {"value": "PICARD Delphine", "confidence": 0.98}, "montant_facture": {"value": "195,00 €", "confidence": 0.99}, "acte": {"value": "Soins conservateurs dentaires", "confidence": 0.96}, "DateDeclaration": {"value": "15/11/2025", "confidence": 0.98}, "DateCloture": {"value": "28/11/2025", "confidence": 0.97}},
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 3, "average_confidence": 0.98, "high_confidence_count": 3},
    }


def _lemaire_sylvie_health() -> Dict[str, Any]:
    return {
        "id": "app-hc-007", "created_at": "2026-01-08T14:10:00Z",
        "external_reference": "PRV-024", "status": "completed",
        "persona": "life_health_claims",
        "files": [{"filename": "facture_cardiologue.pdf", "path": "applications/app-hc-007/facture_cardiologue.pdf", "content_type": "application/pdf", "media_type": "document"}, {"filename": "ordonnance.pdf", "path": "applications/app-hc-007/ordonnance.pdf", "content_type": "application/pdf", "media_type": "document"}],
        "llm_outputs": {"claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview",
            "raw": "Mme LEMAIRE Sylvie, 56 ans. Consultation cardiologue (secteur 2) Dr. Renault, Paris 16e. Honoraires : 120€ (dépassement 70€). Ordonnance ECG d'effort. SS rembourse 30% × 25€ = 7,50€. PrevaIQ 200% BR couvre 50€. Dépassements couverts jusqu'à 150% BR. Reste patient : 62,50€.",
            "parsed": {"summary": "Consultation cardiologie secteur 2 — ECG d'effort prescrit", "claim_amount": 120.00, "ss_reimbursement": 7.50, "complement_assureur": 50.00, "patient_reste": 62.50, "status": "conforme"}}}},
        "extracted_fields": {"beneficiaire": {"value": "LEMAIRE Sylvie", "confidence": 0.98}, "praticien": {"value": "Dr. Renault — Cardiologue, Paris 16e", "confidence": 0.95}, "montant_honoraires": {"value": "120,00 €", "confidence": 0.99}, "DateDeclaration": {"value": "08/01/2026", "confidence": 0.98}, "DateCloture": {"value": "20/01/2026", "confidence": 0.97}},
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 3, "average_confidence": 0.97, "high_confidence_count": 3},
    }


def _fournier_camille_health() -> Dict[str, Any]:
    return {
        "id": "app-hc-008", "created_at": "2026-03-28T10:00:00Z",
        "external_reference": "PRV-012", "status": "pending",
        "persona": "life_health_claims",
        "files": [{"filename": "prescription_irm.pdf", "path": "applications/app-hc-008/prescription_irm.pdf", "content_type": "application/pdf", "media_type": "document"}],
        "llm_outputs": {"claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview",
            "raw": "Mme FOURNIER Camille, 33 ans. Prescription IRM genou gauche par Dr. Martin (médecin traitant) suite à douleurs persistantes post-course à pied. Devis Centre d'Imagerie Médicale Mérignac : 380€. En attente entente préalable pour IRM hors parcours coordonné.",
            "parsed": {"summary": "IRM genou — en attente entente préalable", "claim_amount": 380.00, "status": "entente_prealable"}}}},
        "extracted_fields": {"beneficiaire": {"value": "FOURNIER Camille", "confidence": 0.98}, "montant_devis": {"value": "380,00 €", "confidence": 0.99}, "DateDeclaration": {"value": "28/03/2026", "confidence": 0.98}},
        "risk_analysis": {"risk_level": "low", "decision": "pending", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 2, "average_confidence": 0.99, "high_confidence_count": 2},
    }


# =========================================================================
# Additional seed dossiers — Habitation (6 new)
# =========================================================================

def _leroy_jeanmarc_habitation() -> Dict[str, Any]:
    return {
        "id": "app-hab-002", "created_at": "2025-04-18T09:00:00Z",
        "external_reference": "PRV-005", "status": "completed",
        "persona": "habitation_claims",
        "files": [
            {"filename": "declaration_dde.pdf", "path": "applications/app-hab-002/declaration_dde.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_parquet_gonflé.jpg", "path": "applications/app-hab-002/photo_parquet_gonflé.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "photo_plafond_voisin.jpg", "path": "applications/app-hab-002/photo_plafond_voisin.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "devis_remise_en_etat.pdf", "path": "applications/app-hab-002/devis_remise_en_etat.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {"claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview",
            "raw": "M. LEROY Jean-Marc, propriétaire T3 à Dijon. Dégât des eaux : fuite joint machine à laver. Parquet flottant cuisine gonflé (8 m²) + plinthe. Plafond voisin du dessous taché. Intervention plombier urgente. Constat amiable DDE signé avec voisin. Devis remise en état Entreprise Morel : 3 200€ TTC. Franchise contrat MRH : 250€. Net PrevaIQ : 2 950€. Recours voisin non applicable (responsabilité assuré).",
            "parsed": {"summary": "Dégât des eaux — fuite machine à laver, parquet 8m² + plafond voisin", "claim_amount": 3200.00, "franchise": 250.00, "net_claim": 2950.00, "status": "conforme"}}}},
        "extracted_fields": {
            "NomAssure": {"value": "LEROY Jean-Marc", "confidence": 0.98},
            "NumeroContrat": {"value": "GH-2020-21-0045", "confidence": 0.97},
            "DateSinistre": {"value": "15/04/2025", "confidence": 0.99},
            "NatureSinistre": {"value": "Dégât des eaux — fuite joint machine à laver", "confidence": 0.97},
            "LieuSinistre": {"value": "17 Rue de la Liberté, 21000 Dijon — Cuisine", "confidence": 0.96},
            "DescriptionSinistre": {"value": "Fuite joint arrivée d'eau machine à laver. Parquet flottant gonflé 8m², plinthes décollées. Plafond voisin du dessous taché sur 3m². Constat amiable DDE signé.", "confidence": 0.95},
            "MontantEstime": {"value": "3 200,00 €", "confidence": 0.97},
            "FranchiseApplicable": {"value": "250,00 €", "confidence": 0.98},
            "TiersImplique": {"value": "Voisin du dessous — dommages plafond", "confidence": 0.94},
            "MesuresConservatoires": {"value": "Coupure arrivée d'eau, intervention plombier urgente, bâchage parquet", "confidence": 0.93},
            "NiveauUrgence": {"value": "Moyen", "confidence": 0.96},
            "DateDeclaration": {"value": "18/04/2025", "confidence": 0.97},
            "DateCloture": {"value": "02/06/2025", "confidence": 0.96},
        },
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 11, "average_confidence": 0.96, "high_confidence_count": 11},
    }


def _lambert_sebastien_habitation() -> Dict[str, Any]:
    return {
        "id": "app-hab-003", "created_at": "2025-07-02T14:30:00Z",
        "external_reference": "PRV-015", "status": "completed",
        "persona": "habitation_claims",
        "files": [
            {"filename": "declaration_vol.pdf", "path": "applications/app-hab-003/declaration_vol.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "depot_plainte.pdf", "path": "applications/app-hab-003/depot_plainte.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_serrure_intacte.jpg", "path": "applications/app-hab-003/photo_serrure_intacte.jpg", "content_type": "image/jpeg", "media_type": "image"},
        ],
        "llm_outputs": {"claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview",
            "raw": "M. LAMBERT Sébastien. Déclaration cambriolage appartement T2 Toulouse. Objets volés déclarés : TV LG 65\" (1 200€), MacBook Pro M3 (2 500€), bijoux (valeur déclarée 8 000€), numéraire 500€. Total déclaré : 12 200€. ALERTES FRAUDE : aucune trace d'effraction constatée, serrure intacte, pas de témoin. 2ème sinistre vol en 18 mois sur même adresse. Bijoux non photographiés, pas de factures. Investigation SIU recommandée.",
            "parsed": {"summary": "Cambriolage déclaré — FRAUDE SUSPECTÉE : absence effraction, récidive 18 mois", "claim_amount": 12200.00, "status": "investigation", "fraud_flags": ["Absence traces effraction", "Serrure intacte", "2ème vol 18 mois", "Bijoux sans justificatif d'achat", "Pas de témoin"]}}}},
        "extracted_fields": {
            "NomAssure": {"value": "LAMBERT Sébastien", "confidence": 0.97},
            "NumeroContrat": {"value": "GH-2023-31-0067", "confidence": 0.96},
            "DateSinistre": {"value": "30/06/2025", "confidence": 0.98},
            "NatureSinistre": {"value": "Vol / Cambriolage — fraude suspectée", "confidence": 0.95},
            "LieuSinistre": {"value": "23 Allée des Violettes, 31400 Toulouse", "confidence": 0.97},
            "DescriptionSinistre": {"value": "Déclaration de cambriolage. Objets : TV LG 65\", MacBook Pro, bijoux, numéraire. Aucune trace d'effraction, serrure intacte. 2ème sinistre identique en 18 mois.", "confidence": 0.94},
            "MontantEstime": {"value": "12 200,00 €", "confidence": 0.90},
            "NiveauUrgence": {"value": "Élevé — Investigation", "confidence": 0.96},
            "NombreItemsEndommages": {"value": "4 objets déclarés volés", "confidence": 0.95},
            "DateDeclaration": {"value": "02/07/2025", "confidence": 0.97},
        },
        "risk_analysis": {"risk_level": "high", "decision": "investigate", "fraud_indicators": ["Absence effraction", "Récidive 18 mois", "Bijoux sans justificatif", "Serrure intacte"]},
        "confidence_summary": {"total_fields": 9, "average_confidence": 0.95, "high_confidence_count": 9},
    }


def _lecomte_sandrine_habitation() -> Dict[str, Any]:
    return {
        "id": "app-hab-004", "created_at": "2025-10-30T16:00:00Z",
        "external_reference": "PRV-020", "status": "completed",
        "persona": "habitation_claims",
        "files": [
            {"filename": "declaration_inondation.pdf", "path": "applications/app-hab-004/declaration_inondation.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "rapport_expert.pdf", "path": "applications/app-hab-004/rapport_expert.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_cave_inondee.jpg", "path": "applications/app-hab-004/photo_cave_inondee.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "photo_murs_rdc.jpg", "path": "applications/app-hab-004/photo_murs_rdc.jpg", "content_type": "image/jpeg", "media_type": "image"},
        ],
        "llm_outputs": {"claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview",
            "raw": "Mme LECOMTE Sandrine. Inondation cave et RDC maison individuelle à Albi suite fortes pluies 28/10/2025. Arrêté catastrophe naturelle du 15/11/2025 publié au JO. Dommages constatés : cave (mobilier stocké détruit, électroménager HS), remontées capillaires murs RDC sur 1,20m de hauteur. Rapport expert Mondéal n°EXP-2025-4523 : dommages confirmés 7 500€. Franchise cat-nat légale : 380€. Net PrevaIQ : 7 120€.",
            "parsed": {"summary": "Inondation cave + RDC — catastrophe naturelle confirmée (arrêté JO)", "claim_amount": 7500.00, "franchise_catnat": 380.00, "net_claim": 7120.00, "status": "conforme"}}}},
        "extracted_fields": {
            "NomAssure": {"value": "LECOMTE Sandrine", "confidence": 0.98},
            "NumeroContrat": {"value": "GH-2020-81-0023", "confidence": 0.97},
            "DateSinistre": {"value": "28/10/2025", "confidence": 0.99},
            "NatureSinistre": {"value": "Inondation — Catastrophe Naturelle (arrêté du 15/11/2025)", "confidence": 0.98},
            "LieuSinistre": {"value": "10 Chemin de Falgarde, 81000 Albi — Cave + RDC", "confidence": 0.96},
            "DescriptionSinistre": {"value": "Fortes pluies du 28/10. Cave inondée 60 cm d'eau : mobilier, vélos, électroménager détruits. Remontées capillaires murs RDC (1,20m). Pompage + déshumidification. Arrêté cat-nat publié.", "confidence": 0.96},
            "MontantEstime": {"value": "7 500,00 €", "confidence": 0.97},
            "FranchiseApplicable": {"value": "380,00 € (franchise cat-nat légale)", "confidence": 0.99},
            "ExpertNom": {"value": "Cabinet Mondéal — Rapport EXP-2025-4523", "confidence": 0.95},
            "MesuresConservatoires": {"value": "Pompage cave, déshumidification, déplacement mobilier non atteint", "confidence": 0.93},
            "NombreItemsEndommages": {"value": "12 biens endommagés (cave + RDC)", "confidence": 0.92},
            "NiveauUrgence": {"value": "Élevé", "confidence": 0.97},
            "DateDeclaration": {"value": "30/10/2025", "confidence": 0.98},
            "DateCloture": {"value": "15/01/2026", "confidence": 0.96},
        },
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 12, "average_confidence": 0.96, "high_confidence_count": 12},
    }


def _schmitt_eric_habitation() -> Dict[str, Any]:
    return {
        "id": "app-hab-005", "created_at": "2025-06-20T10:15:00Z",
        "external_reference": "PRV-028", "status": "completed",
        "persona": "habitation_claims",
        "files": [
            {"filename": "declaration_grele.pdf", "path": "applications/app-hab-005/declaration_grele.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_toiture_tuiles.jpg", "path": "applications/app-hab-005/photo_toiture_tuiles.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "photo_gouttiere.jpg", "path": "applications/app-hab-005/photo_gouttiere.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "photo_velux_fissure.jpg", "path": "applications/app-hab-005/photo_velux_fissure.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "devis_couvreur.pdf", "path": "applications/app-hab-005/devis_couvreur.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {"claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview",
            "raw": "M. SCHMITT Éric. Dommages toiture suite épisode de grêle du 18/06/2025 à Colmar. Constat : 15 tuiles mécaniques cassées, gouttière zinc enfoncée sur 3 mètres linéaires, velux chambre fissuré (infiltration constatée). Devis Couvreur Haas Colmar : remplacement tuiles 1 800€, gouttière 1 200€, velux 1 100€. Total : 4 100€ TTC. Franchise contrat tempête/grêle : 300€. Net PrevaIQ : 3 800€.",
            "parsed": {"summary": "Grêle toiture — 15 tuiles, gouttière, velux fissuré", "claim_amount": 4100.00, "franchise": 300.00, "net_claim": 3800.00, "status": "conforme"}}}},
        "extracted_fields": {
            "NomAssure": {"value": "SCHMITT Éric", "confidence": 0.98},
            "NumeroContrat": {"value": "GH-2019-68-0056", "confidence": 0.97},
            "DateSinistre": {"value": "18/06/2025", "confidence": 0.99},
            "NatureSinistre": {"value": "Grêle — dommages toiture", "confidence": 0.99},
            "LieuSinistre": {"value": "6 Rue du Vignoble, 68000 Colmar — Toiture", "confidence": 0.97},
            "DescriptionSinistre": {"value": "Épisode de grêle violent. 15 tuiles mécaniques cassées, gouttière zinc enfoncée (3 ml), velux chambre fissuré avec infiltration. Données météo Colmar : grêlons 2-3 cm, rafales 80 km/h.", "confidence": 0.96},
            "MontantEstime": {"value": "4 100,00 €", "confidence": 0.98},
            "FranchiseApplicable": {"value": "300,00 € (franchise tempête/grêle)", "confidence": 0.98},
            "NombreItemsEndommages": {"value": "3 éléments (tuiles, gouttière, velux)", "confidence": 0.97},
            "MesuresConservatoires": {"value": "Bâchage toiture provisoire, seau sous velux", "confidence": 0.94},
            "NiveauUrgence": {"value": "Moyen — infiltration active velux", "confidence": 0.96},
            "DateDeclaration": {"value": "20/06/2025", "confidence": 0.98},
            "DateCloture": {"value": "25/07/2025", "confidence": 0.97},
        },
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 11, "average_confidence": 0.97, "high_confidence_count": 11},
    }


def _martin_claire_habitation() -> Dict[str, Any]:
    return {
        "id": "app-hab-006", "created_at": "2026-02-05T12:00:00Z",
        "external_reference": "PRV-008", "status": "completed",
        "persona": "habitation_claims",
        "files": [
            {"filename": "declaration_sinistre.pdf", "path": "applications/app-hab-006/declaration_sinistre.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_fissure_mur.jpg", "path": "applications/app-hab-006/photo_fissure_mur.jpg", "content_type": "image/jpeg", "media_type": "image"},
        ],
        "llm_outputs": {"claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview",
            "raw": "Mme MARTIN Claire, nouveau client PrevaIQ depuis 2024. Déclaration de sinistre : fissure mur porteur salon (2 mètres, orientation 45°) apparue suite travaux terrassement voisin (fondation piscine). Expertise structurelle à programmer. Montant non estimé — en attente rapport expert.",
            "parsed": {"summary": "Fissure mur porteur salon — travaux voisin, expertise à programmer", "claim_amount": None, "status": "en_attente_expertise"}}}},
        "extracted_fields": {
            "NomAssure": {"value": "MARTIN Claire", "confidence": 0.99},
            "NumeroContrat": {"value": "GH-2024-69-0089", "confidence": 0.97},
            "DateSinistre": {"value": "01/02/2026", "confidence": 0.98},
            "NatureSinistre": {"value": "Dommages structure — travaux voisinage", "confidence": 0.95},
            "LieuSinistre": {"value": "5 Place Bellecour, 69002 Lyon — Salon", "confidence": 0.96},
            "DescriptionSinistre": {"value": "Fissure mur porteur salon : 2m de long, orientation 45°, largeur 3-5mm. Apparue progressivement depuis début travaux terrassement chez voisin (fondation piscine). Expertise structurelle requise.", "confidence": 0.94},
            "TiersImplique": {"value": "Voisin — travaux terrassement piscine (responsabilité à déterminer)", "confidence": 0.93},
            "NiveauUrgence": {"value": "Élevé — mur porteur", "confidence": 0.97},
            "DateDeclaration": {"value": "05/02/2026", "confidence": 0.98},
        },
        "risk_analysis": {"risk_level": "medium", "decision": "pending", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 8, "average_confidence": 0.96, "high_confidence_count": 8},
    }


def _dasilva_carlos_habitation() -> Dict[str, Any]:
    return {
        "id": "app-hab-007", "created_at": "2025-09-10T11:30:00Z",
        "external_reference": "PRV-030", "status": "completed",
        "persona": "habitation_claims",
        "files": [
            {"filename": "constat_dde.pdf", "path": "applications/app-hab-007/constat_dde.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "photo_plafond_chambre.jpg", "path": "applications/app-hab-007/photo_plafond_chambre.jpg", "content_type": "image/jpeg", "media_type": "image"},
            {"filename": "facture_plombier.pdf", "path": "applications/app-hab-007/facture_plombier.pdf", "content_type": "application/pdf", "media_type": "document"},
            {"filename": "devis_peintre.pdf", "path": "applications/app-hab-007/devis_peintre.pdf", "content_type": "application/pdf", "media_type": "document"},
        ],
        "llm_outputs": {"claim_summary": {"overview": {"section": "claim_summary", "subsection": "overview",
            "raw": "M. DA SILVA Carlos, locataire T2 à Rennes. Dégât des eaux provenant appartement au-dessus (fuite ballon d'eau chaude voisin Mme Kerouac). Dommages : peinture plafond chambre cloquée (6 m²), tache humidité mur (2 m²). Constat amiable DDE signé. Intervention plombier Duval (recherche de fuite) : 180€. Devis peintre Ateliers Bretons : 950€. Total : 1 130€. Recours contre assurance voisin (MACIF, contrat n° MAC-2021-35-7812).",
            "parsed": {"summary": "DDE locataire — fuite ballon voisin, recours MACIF", "claim_amount": 1130.00, "status": "conforme", "recours": "MACIF contrat MAC-2021-35-7812"}}}},
        "extracted_fields": {
            "NomAssure": {"value": "DA SILVA Carlos", "confidence": 0.98},
            "NumeroContrat": {"value": "GH-2021-35-0078", "confidence": 0.97},
            "DateSinistre": {"value": "08/09/2025", "confidence": 0.99},
            "NatureSinistre": {"value": "Dégât des eaux — fuite ballon eau chaude voisin du dessus", "confidence": 0.97},
            "LieuSinistre": {"value": "22 Rue Jean Moulin, 35000 Rennes — Chambre", "confidence": 0.96},
            "DescriptionSinistre": {"value": "Fuite ballon d'eau chaude appartement Mme Kerouac (dessus). Peinture plafond chambre cloquée 6m², tache humidité mur 2m². Constat DDE signé. Plombier + peintre.", "confidence": 0.95},
            "MontantEstime": {"value": "1 130,00 €", "confidence": 0.98},
            "TiersImplique": {"value": "Mme KEROUAC — assurance MACIF n° MAC-2021-35-7812", "confidence": 0.94},
            "MesuresConservatoires": {"value": "Coupure eau voisin, séchage naturel, aération", "confidence": 0.93},
            "NiveauUrgence": {"value": "Faible — dommages esthétiques uniquement", "confidence": 0.97},
            "DateDeclaration": {"value": "10/09/2025", "confidence": 0.98},
            "DateCloture": {"value": "08/11/2025", "confidence": 0.96},
        },
        "risk_analysis": {"risk_level": "low", "decision": "approve", "fraud_indicators": []},
        "confidence_summary": {"total_fields": 10, "average_confidence": 0.96, "high_confidence_count": 10},
    }


def get_claims_apps() -> List[Dict[str, Any]]:
    """Return seed data for claims: 7 habitation + 8 health + 8 automotive."""
    return [
        _girard_laurent_habitation(),
        _leroy_jeanmarc_habitation(),
        _lambert_sebastien_habitation(),
        _lecomte_sandrine_habitation(),
        _schmitt_eric_habitation(),
        _martin_claire_habitation(),
        _dasilva_carlos_habitation(),
        # Sinistres Santé (8)
        _rousseau_marc_health(),
        _petit_sophie_health(),
        _dubois_philippe_health(),
        _fontaine_aurelie_health(),
        _moreau_isabelle_health(),
        _picard_delphine_health(),
        _lemaire_sylvie_health(),
        _fournier_camille_health(),
        # Sinistres Auto (8)
        _garcia_antonio_auto(),
        _arnaud_thierry_auto(),
        _bernard_thomas_auto(),
        _lefebvre_nathalie_auto(),
        _roux_frederic_auto(),
        _vincent_emilie_auto(),
        _fournier_camille_auto(),
        _renard_christophe_auto(),
    ]
