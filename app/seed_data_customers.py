"""Seed data for Customer 360 demo customers by brand."""

from __future__ import annotations

from app.brands import BrandProfile, get_current_brand_profile
from app.customer360 import (
    CustomerJourneyEvent,
    CustomerProfile,
    RiskCorrelation,
    save_customer_journey,
    save_customer_profile,
    save_customer_risk_correlations,
)

# Base fictitious dataset. IDs use the "PRV" template prefix and app IDs the "prv-"
# prefix; both are rewritten from the active brand profile at seed time.
_TEMPLATE_ID_PREFIX = "PRV"
_TEMPLATE_APP_PREFIX = "prv-"

DEMO_CUSTOMERS: list[dict] = [
    {
        "id": "PRV-001",
        "name": "MARTIN Camille",
        "dob": "1984-05-12",
        "email": "camille.martin@example.fr",
        "phone": "06 41 52 63 74",
        "addr": "18 rue des Tilleuls, 69006 Lyon",
        "since": "2022-04-05",
        "risk": "low",
        "tags": ["multi-contrats", "sante", "auto"],
    },
    {
        "id": "PRV-002",
        "name": "DUBOIS Karim",
        "dob": "1979-11-03",
        "email": "karim.dubois@example.fr",
        "phone": "06 52 63 74 85",
        "addr": "24 avenue Carnot, 31000 Toulouse",
        "since": "2020-09-18",
        "risk": "medium",
        "tags": ["habitation", "sinistre-recent", "pret-immobilier"],
    },
    {
        "id": "PRV-003",
        "name": "LEGRAND Sophie",
        "dob": "1991-02-27",
        "email": "sophie.legrand@example.fr",
        "phone": "06 63 74 85 96",
        "addr": "7 place Saint-Pierre, 44000 Nantes",
        "since": "2023-01-12",
        "risk": "high",
        "tags": ["auto", "sinistre-auto", "revue-portefeuille"],
    },
    {
        "id": "PRV-004",
        "name": "BERTRAND Hugo",
        "dob": "1988-08-21",
        "email": "hugo.bertrand@example.fr",
        "phone": "06 74 85 96 07",
        "addr": "12 boulevard Vauban, 59000 Lille",
        "since": "2021-06-30",
        "risk": "low",
        "tags": ["sante", "famille", "prevention"],
    },
    {
        "id": "PRV-005",
        "name": "MOREL Ines",
        "dob": "1974-12-09",
        "email": "ines.morel@example.fr",
        "phone": "06 85 96 07 18",
        "addr": "5 rue du Palais, 33000 Bordeaux",
        "since": "2019-03-25",
        "risk": "medium",
        "tags": ["habitation", "cat-nat", "multi-contrats"],
    },
    {
        "id": "PRV-006",
        "name": "DUPONT Jean",
        "dob": "1979-04-12",
        "email": "jean.dupont@example.fr",
        "phone": "06 84 21 55 09",
        "addr": "27 rue de Vaugirard, 75015 Paris",
        "since": "2022-09-05",
        "risk": "medium",
        "tags": ["auto", "habitation", "multi-contrats"],
        "souscria_ref": "SOC-001",
    },
]


DEMO_JOURNEYS: dict[str, list[dict]] = {
    "PRV-001": [
        {"date": "2025-02-11", "persona": "life_health_claims", "application_id": "prv-sante-001", "event_type": "remboursement_sante", "title": "Demande remboursement santé", "summary": "Consultation spécialiste et lunettes. Remboursement calculé selon contrat {brand} demo.", "status": "traité", "risk_level": "low"},
        {"date": "2025-05-04", "persona": "automotive_claims", "application_id": "prv-auto-001", "event_type": "sinistre_auto", "title": "Sinistre auto — accrochage urbain", "summary": "Accrochage sans blessé, responsabilité tiers partagée. Estimation 1 250€.", "status": "clos", "risk_level": "low"},
    ],
    "PRV-002": [
        {"date": "2025-10-16", "persona": "habitation_claims", "application_id": "prv-hab-001", "event_type": "sinistre_habitation", "title": "Dégât des eaux habitation", "summary": "Fuite cuisine avec dommages au parquet. Expertise planifiée.", "status": "en_cours", "risk_level": "medium"},
        {"date": "2026-01-08", "persona": "mortgage_underwriting", "application_id": "prv-mtg-001", "event_type": "demande_pret", "title": "Demande prêt immobilier", "summary": "Projet résidence principale. LTV 78%, pièces justificatives complètes.", "status": "approuve", "risk_level": "low"},
    ],
    "PRV-003": [
        {"date": "2026-02-20", "persona": "automotive_claims", "application_id": "prv-auto-002", "event_type": "sinistre_auto_investigation", "title": "Sinistre auto — revue approfondie", "summary": "Troisième sinistre auto en douze mois. Vérifications complémentaires recommandées.", "status": "investigation", "risk_level": "high"},
    ],
    "PRV-004": [
        {"date": "2025-07-15", "persona": "life_health_claims", "application_id": "prv-sante-002", "event_type": "prevention_sante", "title": "Parcours prévention santé", "summary": "Bilan annuel et recommandation de suivi préventif.", "status": "traité", "risk_level": "low"},
    ],
    "PRV-005": [
        {"date": "2025-11-02", "persona": "habitation_claims", "application_id": "prv-hab-002", "event_type": "sinistre_catnat", "title": "Sinistre habitation — inondation", "summary": "Dossier catastrophe naturelle fictif, mobilier et sous-sol impactés.", "status": "en_cours", "risk_level": "medium"},
    ],
}


def _brand_customer_id(template_id: str, brand: BrandProfile) -> str:
    return template_id.replace(_TEMPLATE_ID_PREFIX, brand.brand_key[:3].upper(), 1)


def _brand_app_id(template_app_id: str, brand: BrandProfile) -> str:
    return template_app_id.replace(_TEMPLATE_APP_PREFIX, f"{brand.brand_key[:3]}-", 1)


def create_brand_customers(storage_root: str) -> int:
    """Seed fictitious Customer 360 profiles and journeys for the current brand."""
    brand = get_current_brand_profile()
    count = 0

    for c in DEMO_CUSTOMERS:
        customer_id = _brand_customer_id(c["id"], brand)
        profile = CustomerProfile(
            id=customer_id,
            name=c["name"],
            date_of_birth=c["dob"],
            email=c["email"].replace("@example.fr", f"@{brand.brand_key}.example.fr"),
            phone=c["phone"],
            address=c["addr"],
            customer_since=c["since"],
            risk_tier=c["risk"],
            brand=brand.brand_name,
            tags=c["tags"],
            notes=f"Données fictives pour démonstration {brand.app_name}.",
            souscria_ref=c.get("souscria_ref", ""),
        )
        save_customer_profile(storage_root, profile)

        events = [
            CustomerJourneyEvent(
                date=e["date"],
                persona=e["persona"],
                application_id=_brand_app_id(e["application_id"], brand),
                event_type=e["event_type"],
                title=e["title"],
                summary=e["summary"].format(brand=brand.app_name),
                status=e["status"],
                risk_level=e.get("risk_level"),
            )
            for e in DEMO_JOURNEYS.get(c["id"], [])
        ]
        if events:
            save_customer_journey(storage_root, customer_id, events)

        if c["risk"] == "high":
            save_customer_risk_correlations(
                storage_root,
                customer_id,
                [
                    RiskCorrelation(
                        severity="warning",
                        title=f"Revue portefeuille — {c['name']}",
                        description="Plusieurs signaux de fréquence sinistre justifient une revue fictive du portefeuille.",
                        personas_involved=list({e.persona for e in events}) or ["automotive_claims"],
                    )
                ],
            )

        count += 1

    return count


def _build_seeded_dossier_map() -> dict[str, list[dict]]:
    brand = get_current_brand_profile()
    return {
        _brand_customer_id(customer_id, brand): [
            {"app_id": _brand_app_id(e["application_id"], brand)} for e in journeys
        ]
        for customer_id, journeys in DEMO_JOURNEYS.items()
    }


# Cross-reference: customer ID → seeded dossier app IDs (used to link seeded dossiers)
_SEEDED_DOSSIER_MAP: dict[str, list[dict]] = _build_seeded_dossier_map()
