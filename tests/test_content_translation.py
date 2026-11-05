from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api_server
from app import content_translation
from app.content_translation import (
    detect_language,
    translate_case_content,
    translate_text_cached,
)
from app.processing import translate_analysis_payload
from app.storage import ApplicationMetadata

FRENCH = (
    "# Analyse photo : cave.png\n\n- **Nature du sinistre** : dégât des eaux dans la cave, "
    "avec des traces d'humidité sur les murs et une partie des bouteilles cassées par la chute."
)
ENGLISH = "The policyholder reports water damage in the cellar and the walls are wet with mould."
GERMAN = "Der Versicherte meldet einen Wasserschaden im Keller und die Wände sind nicht trocken."


def _settings() -> SimpleNamespace:
    return SimpleNamespace(openai=object(), app=SimpleNamespace(storage_root="root"))


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    monkeypatch.setattr(
        content_translation, "load_file", lambda root, app_id, name: files.get(name)
    )

    def save(root: str, app_id: str, name: str, content: bytes) -> str:
        files[name] = content
        return name

    monkeypatch.setattr(content_translation, "save_application_file", save)
    return files


def test_detect_language_recognizes_supported_languages() -> None:
    assert detect_language(FRENCH) == "fr"
    assert detect_language(ENGLISH) == "en"
    assert detect_language(GERMAN) == "de"
    assert detect_language("SIRET 123 456 789 00012 — 6 560,00 EUR") is None


def test_text_in_the_target_language_is_not_sent_to_the_model(
    monkeypatch: pytest.MonkeyPatch, storage: dict[str, bytes]
) -> None:
    def fail(*args, **kwargs):
        raise AssertionError("no model call expected")

    monkeypatch.setattr(content_translation, "chat_completion", fail)

    result = translate_text_cached(_settings(), "APP-1", ENGLISH, "en")

    assert result == {"text": ENGLISH, "source_language": "en", "translated": False}
    assert storage == {}


def test_translations_are_cached_by_content(
    monkeypatch: pytest.MonkeyPatch, storage: dict[str, bytes]
) -> None:
    calls: list[dict] = []

    def fake_completion(settings, messages, **kwargs):
        calls.append({"messages": messages, **kwargs})
        return {"content": "# Photo analysis: cave.png\n\n- **Nature of the loss**: water damage."}

    monkeypatch.setattr(content_translation, "chat_completion", fake_completion)

    first = translate_text_cached(_settings(), "APP-1", FRENCH, "en")
    second = translate_text_cached(_settings(), "APP-1", FRENCH, "en")

    assert first == second
    assert first["translated"] is True and first["source_language"] == "fr"
    assert first["text"].startswith("# Photo analysis")
    assert len(calls) == 1 and len(storage) == 1
    assert calls[0]["reasoning_effort"] == "none"
    assert "French to English" in calls[0]["messages"][0]["content"]

    translate_text_cached(_settings(), "APP-1", FRENCH + " Modifié.", "en")
    assert len(calls) == 2


def test_failed_translation_returns_the_original(
    monkeypatch: pytest.MonkeyPatch, storage: dict[str, bytes]
) -> None:
    monkeypatch.setattr(content_translation, "chat_completion", lambda *a, **k: {"content": ""})

    result = translate_text_cached(_settings(), "APP-1", FRENCH, "de")

    assert result["text"] == FRENCH
    assert result["translated"] is False
    assert result["error"] == "translation_failed"
    assert storage == {}


def test_case_content_translates_requested_pages_and_summaries(
    monkeypatch: pytest.MonkeyPatch, storage: dict[str, bytes]
) -> None:
    monkeypatch.setattr(
        content_translation,
        "chat_completion",
        lambda settings, messages, **kwargs: {"content": "EN " + messages[1]["content"]},
    )
    app_md = ApplicationMetadata(
        id="APP-1",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="completed",
        files=[],
        markdown_pages=[
            {"page_number": 1, "file": "cave.png", "markdown": FRENCH},
            {"page_number": 2, "file": "mail.pdf", "markdown": ENGLISH},
        ],
        batch_summaries=[{"batch_num": 1, "page_start": 1, "page_end": 2, "summary": FRENCH}],
    )

    result = translate_case_content(_settings(), app_md, "en-GB", [1, 2, 1, 99], [1])

    assert result["language"] == "en"
    assert [(page["page_number"], page["translated"]) for page in result["pages"]] == [
        (1, True),
        (2, False),
    ]
    assert result["batches"][0]["batch_num"] == 1
    assert result["batches"][0]["text"] == "EN " + FRENCH


def test_large_analyses_are_translated_in_parallel_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import json

    calls: list[dict] = []

    def fake_completion(settings, messages, **kwargs):
        chunk = json.loads(messages[1]["content"])
        calls.append({"keys": sorted(chunk), **kwargs})
        return {"content": json.dumps({key: f"EN:{value}" for key, value in chunk.items()})}

    monkeypatch.setattr("app.processing.chat_completion", fake_completion)
    monkeypatch.setattr("app.processing._TRANSLATION_CHUNK_CHARS", 40)
    payload = {
        "llm_outputs": {
            name: {"parsed": {"summary": f"Résumé {name} du dossier sinistre habitation."}}
            for name in ("a", "b", "c")
        }
    }

    translated = translate_analysis_payload(
        _settings(), payload, source_language="fr", target_language="en"
    )

    summaries = [translated["llm_outputs"][name]["parsed"]["summary"] for name in ("a", "b", "c")]
    assert all(summary.startswith("EN:Résumé") for summary in summaries)
    assert sorted(key for call in calls for key in call["keys"]) == ["0", "1", "2"]
    assert len(calls) == 3
    assert {call["reasoning_effort"] for call in calls} == {"none"}


def _case() -> ApplicationMetadata:
    return ApplicationMetadata(
        id="app-1",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="completed",
        files=[],
        analysis_locale="fr",
        context_labels=[{"key": "guarantee", "label": "Garantie dégâts des eaux"}],
        llm_outputs={"summary": {"parsed": {"summary": "Le dossier nécessite une revue."}}},
        markdown_pages=[
            {"page_number": 1, "file": "cave.png", "markdown": FRENCH},
            {"page_number": 2, "file": "mail.pdf", "markdown": ENGLISH},
        ],
    )


def test_case_api_does_not_wait_for_an_analysis_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scheduled: list[tuple[str, str]] = []
    monkeypatch.setattr(api_server, "load_settings", _settings)
    monkeypatch.setattr(api_server, "load_application", lambda root, app_id: _case())
    monkeypatch.setattr("app.processing.load_localized_analysis_cache", lambda *args: None)
    monkeypatch.setattr(
        api_server,
        "_schedule_analysis_translation",
        lambda app_id, language: scheduled.append((app_id, language)),
    )

    def no_translation(*args, **kwargs):
        raise AssertionError("the request must not translate synchronously")

    monkeypatch.setattr("app.processing.translate_analysis_payload", no_translation)

    response = TestClient(api_server.app).get("/api/applications/app-1?language=en")

    assert response.status_code == 200
    payload = response.json()
    assert payload["analysis_language"] == "fr"
    assert payload["analysis_translation_pending"] == "en"
    assert payload["llm_outputs"]["summary"]["parsed"]["summary"].startswith("Le dossier")
    assert scheduled == [("app-1", "en")]
    assert [page["language"] for page in payload["markdown_pages"]] == ["fr", "en"]

    same_language = TestClient(api_server.app).get("/api/applications/app-1?language=fr").json()
    assert same_language["analysis_language"] == "fr"
    assert "analysis_translation_pending" not in same_language


def test_case_api_stops_waiting_after_a_failed_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_server, "load_settings", _settings)
    monkeypatch.setattr(api_server, "load_application", lambda root, app_id: _case())
    monkeypatch.setattr("app.processing.load_localized_analysis_cache", lambda *args: None)
    monkeypatch.setattr(api_server, "_analysis_translation_failed_recently", lambda *args: True)
    monkeypatch.setattr(
        api_server,
        "_schedule_analysis_translation",
        lambda *args: (_ for _ in ()).throw(AssertionError("no retry during the cooldown")),
    )

    payload = TestClient(api_server.app).get("/api/applications/app-1?language=de").json()

    assert payload["analysis_language"] == "fr"
    assert payload["analysis_translation_failed"] == "de"
    assert "analysis_translation_pending" not in payload
