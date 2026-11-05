from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

import api_server
from app.languages import UnsupportedLanguageError, require_language
from app.processing import (
    cached_localized_analysis_payload,
    localized_analysis_payload,
    translate_analysis_payload,
)
from app.storage import (
    ApplicationMetadata,
    StoredFile,
    analysis_source_revision,
    load_localized_analysis_cache,
    save_application_metadata,
    save_localized_analysis_cache,
)


def _metadata() -> ApplicationMetadata:
    return ApplicationMetadata(
        id="app-1",
        created_at="2026-01-01T00:00:00Z",
        external_reference="REF-123",
        status="completed",
        files=[StoredFile(filename="source.pdf", path="source.pdf", url="/source.pdf")],
        analysis_locale="fr",
        document_markdown="Texte OCR original",
        llm_outputs={
            "summary": {
                "parsed": {
                    "summary": "Le dossier nécessite une revue manuelle.",
                    "status": "review_needed",
                    "policy_id": "CG-AUTO-42",
                    "citations": [{"article": "Article L113-2", "quote": "Texte source"}],
                },
                "raw": '{"summary":"Le dossier nécessite une revue manuelle."}',
            }
        },
    )


def test_external_language_validation_is_explicit() -> None:
    assert require_language("de-DE") == "de"
    with pytest.raises(UnsupportedLanguageError):
        require_language("es")


def test_process_endpoint_propagates_normalized_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _metadata()
    metadata.processing_status = None
    captured: list[tuple[str, str | None, str | None]] = []

    async def fake_background(app_id: str, mode: str | None, language: str | None) -> None:
        captured.append((app_id, mode, language))

    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(storage_root="unused")),
    )
    monkeypatch.setattr(api_server, "load_application", lambda *args: metadata)
    monkeypatch.setattr(api_server, "save_application_metadata", lambda *args: None)
    monkeypatch.setattr(api_server, "run_extract_and_analyze_background", fake_background)

    async def exercise() -> dict:
        response = await api_server.process_application(metadata.id, "standard", "de-DE")
        await asyncio.sleep(0)
        return response

    response = asyncio.run(exercise())

    assert captured == [(metadata.id, "standard", "de")]
    assert response["message"].startswith("Die Verarbeitung")


def test_extraction_handoff_preserves_language(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = _metadata()
    metadata.processing_status = None
    captured: list[str | None] = []

    async def fake_extraction(app_id: str, language: str | None = None) -> None:
        return None

    async def fake_analysis(
        app_id: str,
        sections=None,
        processing_mode: str | None = None,
        language: str | None = None,
    ) -> None:
        captured.append(language)

    monkeypatch.setattr(api_server, "run_extraction_background", fake_extraction)
    monkeypatch.setattr(api_server, "run_analysis_background", fake_analysis)
    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(storage_root="unused")),
    )
    monkeypatch.setattr(api_server, "load_application", lambda *args: metadata)
    monkeypatch.setattr(api_server, "save_application_metadata", lambda *args: None)

    asyncio.run(api_server.run_extract_and_analyze_background(metadata.id, language="de"))

    assert captured == ["de"]


def test_risk_background_uses_requested_language(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = _metadata()
    captured: list[str] = []

    def fake_risk_analysis(settings, app_md, language: str) -> None:
        captured.append(language)

    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(storage_root="unused")),
    )
    monkeypatch.setattr(api_server, "load_application", lambda *args: metadata)
    monkeypatch.setattr("app.processing.run_risk_analysis", fake_risk_analysis)

    asyncio.run(api_server._risk_analysis_background(metadata.id, "de-DE"))

    assert captured == ["de"]


def test_translation_preserves_shape_and_source_values(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_completion(*args, **kwargs):
        return {"content": '{"0":"The application requires manual review."}'}

    monkeypatch.setattr("app.processing.chat_completion", fake_completion)
    original = _metadata().llm_outputs
    translated = translate_analysis_payload(
        SimpleNamespace(openai=object()),
        {"llm_outputs": original},
        source_language="fr",
        target_language="en",
    )

    parsed = translated["llm_outputs"]["summary"]["parsed"]
    assert parsed["summary"] == "The application requires manual review."
    assert parsed["status"] == "review_needed"
    assert parsed["policy_id"] == "CG-AUTO-42"
    assert parsed["citations"] == [{"article": "Article L113-2", "quote": "Texte source"}]
    assert translated["llm_outputs"]["summary"]["raw"] == original["summary"]["raw"]
    assert original["summary"]["parsed"]["summary"].startswith("Le dossier")


def test_translation_keeps_web_iq_queries_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict] = []

    def fake_completion(_settings, messages, **_kwargs):
        sent.append(json.loads(messages[1]["content"]))
        return {"content": '{"0":"The storm is not confirmed."}'}

    monkeypatch.setattr("app.processing.chat_completion", fake_completion)
    query = "météo Bordeaux 27 mars 2026 pluie vent orage"
    payload = {
        "fraud_analysis": {
            "web_intelligence": {
                "overall_assessment": "La tempête n'est pas confirmée.",
                "search_queries": [query],
            }
        }
    }

    translated = translate_analysis_payload(
        SimpleNamespace(openai=object()), payload, source_language="fr", target_language="en"
    )

    web = translated["fraud_analysis"]["web_intelligence"]
    assert web["overall_assessment"] == "The storm is not confirmed."
    assert web["search_queries"] == [query]
    assert sent == [{"0": "La tempête n'est pas confirmée."}]


def test_prose_citing_a_url_is_translated_but_bare_urls_are_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[dict] = []

    def fake_completion(_settings, messages, **_kwargs):
        chunk = json.loads(messages[1]["content"])
        sent.append(chunk)
        return {"content": json.dumps({key: f"EN {text}" for key, text in chunk.items()})}

    monkeypatch.setattr("app.processing.chat_completion", fake_completion)
    detail = "La vérification web contredit la tempête. Source : https://x.test/a"
    payload = {
        "fraud_analysis": {
            "overall_assessment": {
                "attention_items": [{"label": "Tempête non confirmée", "detail": detail}],
                "source_urls": ["https://x.test/a"],
                "contact": "gestion@prevaiq.example",
            }
        }
    }

    translated = translate_analysis_payload(
        SimpleNamespace(openai=object()), payload, source_language="fr", target_language="en"
    )

    assessment = translated["fraud_analysis"]["overall_assessment"]
    assert sent == [{"0": "Tempête non confirmée", "1": detail}]
    assert assessment["attention_items"][0]["detail"] == f"EN {detail}"
    assert assessment["source_urls"] == ["https://x.test/a"]
    assert assessment["contact"] == "gestion@prevaiq.example"


def test_legacy_analysis_without_locale_is_treated_as_french(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _metadata()
    metadata.analysis_locale = None
    settings = SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="unused"))
    received_source = None

    def fake_translate(settings, payload, *, source_language, target_language):
        nonlocal received_source
        received_source = source_language
        return payload

    monkeypatch.setattr("app.processing.translate_analysis_payload", fake_translate)
    monkeypatch.setattr("app.processing.load_application", lambda *args: metadata)
    monkeypatch.setattr("app.processing.load_localized_analysis_cache", lambda *args: None)
    monkeypatch.setattr("app.processing.save_localized_analysis_cache", lambda *args: "cache")

    localized_analysis_payload(settings, metadata, "en")

    assert received_source == "fr"


def test_localized_cache_is_revision_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    metadata = _metadata()
    settings = SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="unused"))
    calls = 0

    def fake_translate(settings, payload, *, source_language, target_language):
        nonlocal calls
        calls += 1
        return {**payload, "translated": target_language}

    monkeypatch.setattr("app.processing.translate_analysis_payload", fake_translate)
    monkeypatch.setattr("app.processing.load_application", lambda *args: metadata)
    monkeypatch.setattr("app.processing.load_localized_analysis_cache", lambda *args: None)
    monkeypatch.setattr("app.processing.save_localized_analysis_cache", lambda *args: "cache")

    first = localized_analysis_payload(settings, metadata, "de")
    second = localized_analysis_payload(settings, metadata, "de")
    assert first == second
    assert calls == 1

    metadata.llm_outputs["summary"]["parsed"]["summary"] = "Analyse canonique modifiée."
    third = localized_analysis_payload(settings, metadata, "de")
    assert third["translated"] == "de"
    assert calls == 2


def test_localized_cache_does_not_overwrite_newer_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _metadata()
    latest = deepcopy(original)
    latest.status = "reviewed"
    latest.llm_outputs["summary"]["parsed"]["summary"] = "Une analyse plus récente."
    saved: list[tuple[str, str]] = []
    settings = SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="unused"))

    monkeypatch.setattr(
        "app.processing.translate_analysis_payload",
        lambda *args, **kwargs: {"llm_outputs": {"translated": "en"}},
    )
    monkeypatch.setattr("app.processing.load_localized_analysis_cache", lambda *args: None)
    monkeypatch.setattr("app.processing.load_application", lambda *args: latest)
    monkeypatch.setattr(
        "app.processing.save_localized_analysis_cache",
        lambda root, app_id, revision, language, payload: saved.append((revision, language)),
    )

    localized_analysis_payload(settings, original, "en")

    assert saved == []
    assert latest.status == "reviewed"
    assert latest.llm_outputs["summary"]["parsed"]["summary"] == "Une analyse plus récente."


def test_localized_cache_uses_distinct_revision_locale_objects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _metadata()
    saved: list[tuple[str, str, str]] = []
    settings = SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="unused"))

    monkeypatch.setattr(
        "app.processing.translate_analysis_payload",
        lambda *args, target_language, **kwargs: {"translated": target_language},
    )
    monkeypatch.setattr("app.processing.load_localized_analysis_cache", lambda *args: None)
    monkeypatch.setattr("app.processing.load_application", lambda *args: deepcopy(metadata))
    monkeypatch.setattr(
        "app.processing.save_localized_analysis_cache",
        lambda root, app_id, revision, language, payload: saved.append(
            (app_id, revision, language)
        ),
    )

    localized_analysis_payload(settings, metadata, "en")
    localized_analysis_payload(settings, metadata, "de")

    assert len(saved) == 2
    assert saved[0][:2] == saved[1][:2]
    assert {saved[0][2], saved[1][2]} == {"en", "de"}


def test_localized_cache_is_persisted_separately_from_metadata(tmp_path) -> None:
    payload = {"llm_outputs": {"summary": {"parsed": {"summary": "Localized"}}}}

    save_localized_analysis_cache(str(tmp_path), "app-1", "revision-1", "de", payload)

    assert load_localized_analysis_cache(str(tmp_path), "app-1", "revision-1", "de") == payload
    assert not (tmp_path / "app-1" / "metadata.json").exists()


def test_save_invalidates_stale_translation_cache(tmp_path) -> None:
    metadata = _metadata()
    metadata.localized_analyses = {
        "de": {"source_revision": "stale", "payload": {"llm_outputs": {}}}
    }
    app_dir = tmp_path / metadata.id
    app_dir.mkdir()

    save_application_metadata(str(tmp_path), metadata)

    assert metadata.localized_analyses == {}
    assert metadata.analysis_source_revision


def _english_case() -> ApplicationMetadata:
    metadata = _metadata()
    metadata.analysis_locale = "en"
    metadata.llm_outputs = {"summary": {"parsed": {"summary": "Manual review required."}}}
    metadata.context_labels = [{"key": "event_confirmed", "label": "✓ Événement confirmé"}]
    metadata.context_tasks = [{"key": "siu", "task": "Transmettre au SIU", "priority": "high"}]
    return metadata


def _record_translations(monkeypatch: pytest.MonkeyPatch, metadata: ApplicationMetadata) -> list:
    calls: list[tuple[str, str, list[str]]] = []

    def fake_translate(settings, payload, *, source_language, target_language):
        calls.append((source_language, target_language, sorted(payload)))
        return {key: f"{source_language}->{target_language}" for key in payload}

    monkeypatch.setattr("app.processing.translate_analysis_payload", fake_translate)
    monkeypatch.setattr("app.processing.load_application", lambda *args: metadata)
    monkeypatch.setattr("app.processing.load_localized_analysis_cache", lambda *args: None)
    monkeypatch.setattr("app.processing.save_localized_analysis_cache", lambda *args: "cache")
    return calls


def test_french_context_items_are_translated_for_an_english_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _english_case()
    settings = SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="unused"))
    calls = _record_translations(monkeypatch, metadata)

    assert cached_localized_analysis_payload(settings, metadata, "en") is None
    localized = localized_analysis_payload(settings, metadata, "en")

    assert calls == [("fr", "en", ["context_labels", "context_tasks"])]
    assert localized["context_tasks"] == "fr->en"
    assert localized["llm_outputs"] == metadata.llm_outputs


def test_french_context_items_need_no_translation_in_french(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _english_case()
    metadata.analysis_locale = "fr"
    settings = SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="unused"))
    calls = _record_translations(monkeypatch, metadata)

    localized = cached_localized_analysis_payload(settings, metadata, "fr")

    assert calls == []
    assert localized["context_labels"] == metadata.context_labels


def test_fraud_analysis_is_translated_from_its_own_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _english_case()
    metadata.context_labels = []
    metadata.context_tasks = []
    metadata.fraud_analysis = {"language": "de", "overall_assessment": {"summary": "Hoch."}}
    settings = SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="unused"))
    calls = _record_translations(monkeypatch, metadata)

    localized = localized_analysis_payload(settings, metadata, "en")

    assert calls == [("de", "en", ["fraud_analysis"])]
    assert localized["fraud_analysis"] == "de->en"


def test_fraud_analysis_without_language_follows_the_case_analysis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _english_case()
    metadata.context_labels = []
    metadata.context_tasks = []
    metadata.fraud_analysis = {"overall_assessment": {"summary": "High."}}
    settings = SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="unused"))
    calls = _record_translations(monkeypatch, metadata)

    assert cached_localized_analysis_payload(settings, metadata, "en") is not None
    localized_analysis_payload(settings, metadata, "de")

    assert calls == [("en", "de", ["fraud_analysis", "llm_outputs"])]


def test_localization_contract_bump_invalidates_cached_translations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    metadata = _metadata()
    settings = SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="unused"))
    cached = {"llm_outputs": {"summary": "cached"}}
    metadata.localized_analyses = {
        "en": {"source_revision": analysis_source_revision(metadata), "payload": cached}
    }
    monkeypatch.setattr("app.processing.load_localized_analysis_cache", lambda *args: None)

    assert cached_localized_analysis_payload(settings, metadata, "en") == cached
    monkeypatch.setattr("app.storage._LOCALIZATION_CONTRACT_VERSION", 999)
    assert cached_localized_analysis_payload(settings, metadata, "en") is None
