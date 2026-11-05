"""Context labels and tasks follow the claim's jurisdiction (France vs Switzerland)."""

from __future__ import annotations

from types import SimpleNamespace

from app.processing import generate_context_labels, generate_context_tasks

_SWISS_FIELDS = {
    "llm_extracted:NatureSinistre": {"value": "Hagel / Sturm (Elementarschaden)"},
    "llm_extracted:DescriptionSinistre": {
        "value": "Hagelzug, zerbrochenes Schaufenster, Wassereintritt im Atelier"
    },
    "cu_extracted:AdresseAssure": {"value": "Kakaogasse 7, 8400 Winterthur"},
    "llm_extracted:MontantEstime": {"value": "CHF 1'697'400.00"},
}
_FRENCH_FIELDS = {
    "llm_extracted:NatureSinistre": {"value": "Tempête"},
    "cu_extracted:AdresseAssure": {"value": "42 rue des Vignobles, 33000 Bordeaux"},
    "llm_extracted:MontantEstime": {"value": "6,560.00 EUR"},
}
_VERIFIED_EVENT = {
    "overall_assessment": {"risk_score": 0.1, "overall_fraud_risk": "low"},
    "web_intelligence": {
        "event_verified": True,
        "findings": [{"summary": "Hagelzug bestätigt"}],
        "source_urls": ["https://example.test/news"],
    },
}


def _claim(fields, files=(), fraud=None):
    return SimpleNamespace(
        persona="habitation_claims",
        extracted_fields=fields,
        llm_outputs={},
        fraud_analysis=fraud,
        files=[SimpleNamespace(filename=name) for name in files],
        status="completed",
        sentiment_analysis=None,
    )


def test_swiss_labels_use_chf_and_the_elementar_regime():
    labels = {
        label["key"]: label
        for label in generate_context_labels(_claim(_SWISS_FIELDS, fraud=_VERIFIED_EVENT))
    }

    assert {"garantie_tempete", "bris_glace", "regime_elementar", "sinistre_majeur"} <= set(labels)
    assert "CHF" in labels["sinistre_majeur"]["tooltip"]
    assert "€" not in labels["sinistre_majeur"]["tooltip"]
    assert labels["evenement_confirme"]["source_url"] == "https://example.test/news"
    assert not {"regime_catnat", "convention_irsi", "catnat_confirmee"} & set(labels)


def test_swiss_tasks_follow_the_avb_and_chf():
    tasks = {
        task["key"]: task
        for task in generate_context_tasks(
            _claim(
                _SWISS_FIELDS,
                files=["schadenmeldung-geschaeftsversicherung.pdf", "IMG_20260828_104112.jpg"],
            )
        )
    }

    assert tasks["verify_tempete_coverage"]["task"].endswith("AVB (CH)")
    assert "CHF" in tasks["mandate_expert"]["task"]
    assert "€" not in tasks["mandate_expert"]["task"]
    missing = tasks["collect_missing_docs"]["task"]
    assert (
        "Devis ou facture" in missing and "Déclaration" not in missing and "Photos" not in missing
    )
    assert "verify_catnat" not in tasks


def test_french_claims_keep_euro_and_cat_nat():
    labels = {
        label["key"]: label
        for label in generate_context_labels(_claim(_FRENCH_FIELDS, fraud=_VERIFIED_EVENT))
    }
    tasks = {task["key"]: task for task in generate_context_tasks(_claim(_FRENCH_FIELDS))}

    assert "€" in labels["sinistre_majeur"]["tooltip"]
    assert "catnat_confirmee" in labels and "evenement_confirme" not in labels
    assert tasks["verify_tempete_coverage"]["task"] == "Vérifier couverture tempête — CG Habitation"
    assert "€" in tasks["mandate_expert"]["task"]


def _liability_label(description: str) -> bool:
    fields = {
        "llm_extracted:NatureSinistre": {"value": "Grêle / tempête"},
        "llm_extracted:DescriptionSinistre": {"value": description},
    }
    return "rc_habitation" in {label["key"] for label in generate_context_labels(_claim(fields))}


def test_liability_label_needs_the_rc_word_not_a_substring():
    assert not _liability_label("Court-circuit sur la machine, marchandises perdues")
    assert _liability_label("Mise en cause de la RC de l'occupant")
    assert _liability_label("Recours en responsabilité civile")
