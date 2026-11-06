"""The glossary menu follows the UI language: terms are translated once, never abbreviations."""

from __future__ import annotations

import json
import threading
from types import SimpleNamespace

import pytest

from app import glossary_translation as translation


def _glossary(language="fr"):
    persona = {
        "name": "Sinistres Habitation",
        "description": "Terminologie assurance habitation",
        "categories": [
            {
                "id": "garanties",
                "name": "Garanties et Couvertures",
                "terms": [
                    {
                        "abbreviation": "DDE",
                        "meaning": "Dégâts des eaux",
                        "context": "Sinistre causé par l'eau (fuite, infiltration, débordement)",
                    },
                    {"abbreviation": "BG", "meaning": "Bris de Glace"},
                ],
            },
            {
                "id": "indemnisation",
                "name": "Indemnisation",
                "terms": [
                    {
                        "abbreviation": "FRC",
                        "meaning": "Franchise Contractuelle",
                        "context": "Montant restant à charge de l'assuré par sinistre",
                    }
                ],
            },
        ],
    }
    if language:
        persona["language"] = language
    return {"version": "1.0", "personas": {"habitation_claims": persona}}


@pytest.fixture()
def settings(tmp_path):
    (tmp_path / "glossary.json").write_text(json.dumps(_glossary()), encoding="utf-8")
    translation._cache.clear()
    return SimpleNamespace(app=SimpleNamespace(prompts_root=str(tmp_path)), openai=None)


class FakeModel:
    def __init__(self):
        self.calls = []
        self.lock = threading.Lock()

    def __call__(self, texts, source, target):
        with self.lock:
            self.calls.append((list(texts), source, target))
        return [f"[{target}] {text}" for text in texts]


def _terms(glossary):
    return {
        term["abbreviation"]: (category["name"], term["meaning"], term.get("context"))
        for category in glossary["categories"]
        for term in category["terms"]
    }


def test_a_glossary_already_in_the_reader_language_is_not_translated(settings):
    model = FakeModel()

    glossary = translation.localized_glossary(settings, "habitation_claims", "fr", model)

    assert model.calls == []
    assert (glossary["language"], glossary["source_language"], glossary["translated"]) == (
        "fr",
        "fr",
        False,
    )
    assert _terms(glossary)["DDE"][1] == "Dégâts des eaux"


def test_categories_meanings_and_contexts_are_translated_but_not_abbreviations(settings):
    model = FakeModel()

    glossary = translation.localized_glossary(settings, "habitation_claims", "en", model)

    assert (glossary["language"], glossary["source_language"], glossary["translated"]) == (
        "en",
        "fr",
        True,
    )
    assert _terms(glossary) == {
        "DDE": (
            "[en] Garanties et Couvertures",
            "[en] Dégâts des eaux",
            "[en] Sinistre causé par l'eau (fuite, infiltration, débordement)",
        ),
        "BG": ("[en] Garanties et Couvertures", "[en] Bris de Glace", None),
        "FRC": (
            "[en] Indemnisation",
            "[en] Franchise Contractuelle",
            "[en] Montant restant à charge de l'assuré par sinistre",
        ),
    }
    assert [(source, target) for _, source, target in model.calls] == [("fr", "en")]
    # The source glossary is untouched.
    original = translation.localized_glossary(settings, "habitation_claims", "fr", model)
    assert _terms(original)["BG"][1] == "Bris de Glace"


def test_a_glossary_is_translated_once_and_again_when_a_term_changes(settings, tmp_path):
    model = FakeModel()
    translation.localized_glossary(settings, "habitation_claims", "en", model)
    translation.localized_glossary(settings, "habitation_claims", "en", model)
    assert len(model.calls) == 1

    translation.localized_glossary(settings, "habitation_claims", "de", model)
    assert len(model.calls) == 2

    edited = _glossary()
    edited["personas"]["habitation_claims"]["categories"][1]["terms"][0]["meaning"] = "Franchise"
    (tmp_path / "glossary.json").write_text(json.dumps(edited), encoding="utf-8")
    glossary = translation.localized_glossary(settings, "habitation_claims", "en", model)
    assert len(model.calls) == 3
    assert _terms(glossary)["FRC"][1] == "[en] Franchise"


def test_the_original_terms_are_shown_when_the_translation_fails(settings):
    def down(texts, source, target):
        raise RuntimeError("model unavailable")

    glossary = translation.localized_glossary(settings, "habitation_claims", "en", down)

    assert (glossary["language"], glossary["translated"]) == ("fr", False)
    assert _terms(glossary)["DDE"][1] == "Dégâts des eaux"
    model = FakeModel()
    translation.localized_glossary(settings, "habitation_claims", "en", model)
    assert len(model.calls) == 1  # a failure is not cached


def test_an_undeclared_language_is_detected_from_the_terms(tmp_path):
    (tmp_path / "glossary.json").write_text(json.dumps(_glossary(language=None)), encoding="utf-8")
    glossary = translation.get_glossary_for_persona(str(tmp_path), "habitation_claims")
    assert glossary["language"] is None
    assert translation.glossary_language(glossary) == "fr"


def test_every_shipped_glossary_declares_the_language_of_its_terms():
    shipped = json.loads(open("prompts/glossary.json", encoding="utf-8").read())["personas"]
    declared = {persona: glossary.get("language") for persona, glossary in shipped.items()}
    assert declared == {
        "underwriting": "en",
        "life_health_claims": "en",
        "mortgage": "fr",
        "automotive_claims": "en",
        "habitation_claims": "fr",
    }
    for persona in ("mortgage", "habitation_claims"):
        detected = translation.glossary_language({**shipped[persona], "language": None})
        assert detected == "fr", persona


def test_translations_stay_aligned_across_parallel_batches(settings, tmp_path):
    many = _glossary()
    many["personas"]["habitation_claims"]["categories"][0]["terms"] = [
        {"abbreviation": f"T{index}", "meaning": f"Terme numéro {index}"} for index in range(95)
    ]
    (tmp_path / "glossary.json").write_text(json.dumps(many), encoding="utf-8")
    model = FakeModel()

    glossary = translation.localized_glossary(settings, "habitation_claims", "en", model)

    assert len(model.calls) == 3  # 98 texts in batches of 40
    terms = _terms(glossary)
    assert all(terms[f"T{index}"][1] == f"[en] Terme numéro {index}" for index in range(95))


def test_the_model_must_return_one_translation_per_entry(monkeypatch):
    sent = {}

    def answer(content):
        def chat_completion(openai, messages, **kwargs):
            sent.update(messages=messages, kwargs=kwargs)
            return {"content": content}

        return chat_completion

    settings = SimpleNamespace(openai="openai-settings")
    texts = ["Dégâts des eaux", "Bris de Glace"]

    monkeypatch.setattr(
        translation,
        "chat_completion",
        answer(json.dumps({"translations": ["Water damage", "Glass breakage"]})),
    )
    assert translation.translate_entries(settings, texts, "fr", "en") == [
        "Water damage",
        "Glass breakage",
    ]
    assert sent["kwargs"]["response_format"] == "json_object"
    assert "from French to English" in sent["messages"][0]["content"]
    assert json.loads(sent["messages"][1]["content"]) == texts

    monkeypatch.setattr(
        translation, "chat_completion", answer(json.dumps({"translations": ["Water damage"]}))
    )
    with pytest.raises(RuntimeError):
        translation.translate_entries(settings, texts, "fr", "en")
