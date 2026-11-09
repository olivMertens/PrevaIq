"""Ask IQ conversations are stored with their application, not on the container disk."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import api_server
from app.storage_providers.azure_blob import AzureBlobStorageProvider
from app.storage_providers.base import StorageBackend, StorageSettings
from app.storage_providers.local import LocalStorageProvider


def _conversation(conversation_id: str, app_id: str, updated_at: str, question: str) -> dict:
    return {
        "id": conversation_id,
        "application_id": app_id,
        "title": question[:50],
        "created_at": updated_at,
        "updated_at": updated_at,
        "persona": "habitation_claims",
        "messages": [
            {"role": "user", "content": question},
            {"role": "assistant", "content": "Réponse"},
        ],
    }


@pytest.fixture(params=["provider", "no-provider"])
def storage_root(request, tmp_path, monkeypatch):
    provider = None
    if request.param == "provider":
        provider = LocalStorageProvider(
            StorageSettings(backend=StorageBackend.LOCAL, local_root=str(tmp_path))
        )
    monkeypatch.setattr("app.storage._get_provider", lambda: provider)
    return str(tmp_path)


def test_conversations_round_trip_with_the_application(storage_root, tmp_path):
    first = _conversation("a1b2c3d4", "app-1", "2026-11-05T10:00:00Z", "Quelle franchise ?")
    second = _conversation("e5f6a7b8", "app-1", "2026-11-05T11:00:00Z", "x" * 120)
    api_server.save_conversation(storage_root, "app-1", first)
    api_server.save_conversation(storage_root, "app-1", second)

    stored = list(tmp_path.glob("**/app-1/files/.conversation-*.json"))
    assert len(stored) == 2
    assert api_server.load_conversation(storage_root, "app-1", "a1b2c3d4") == first

    summaries = api_server.list_conversations(storage_root, "app-1")
    assert [summary["id"] for summary in summaries] == ["e5f6a7b8", "a1b2c3d4"]
    assert summaries[0]["preview"] == "x" * 100 + "..."
    assert summaries[1] == {
        "id": "a1b2c3d4",
        "application_id": "app-1",
        "persona": "habitation_claims",
        "title": "Quelle franchise ?",
        "created_at": "2026-11-05T10:00:00Z",
        "updated_at": "2026-11-05T10:00:00Z",
        "message_count": 2,
        "preview": "Quelle franchise ?",
    }

    assert api_server.delete_stored_conversation(storage_root, "app-1", "a1b2c3d4")
    assert not api_server.delete_stored_conversation(storage_root, "app-1", "a1b2c3d4")
    assert api_server.load_conversation(storage_root, "app-1", "a1b2c3d4") is None


def test_listing_across_applications_is_limited_to_the_newest(storage_root):
    for index, app_id in enumerate(["app-1", "app-2", "app-3"]):
        api_server.save_conversation(
            storage_root,
            app_id,
            _conversation(f"conv{index}", app_id, f"2026-11-05T1{index}:00:00Z", "Statut ?"),
        )

    every = api_server.list_conversations(storage_root)
    assert {summary["application_id"] for summary in every} == {"app-1", "app-2", "app-3"}
    assert len(api_server.list_conversations(storage_root, None, 2)) == 2


@pytest.mark.parametrize("bad_id", ["../app-1", "a/b", "", "x" * 65])
def test_ids_used_in_storage_paths_are_validated(storage_root, bad_id):
    assert api_server.load_conversation(storage_root, bad_id, "a1b2c3d4") is None
    assert api_server.load_conversation(storage_root, "app-1", bad_id) is None
    assert api_server.list_conversations(storage_root, bad_id) == []
    assert not api_server.delete_stored_conversation(storage_root, "app-1", bad_id)
    with pytest.raises(ValueError):
        api_server.save_conversation(
            storage_root, "app-1", _conversation(bad_id, "app-1", "2026-11-05T10:00:00Z", "?")
        )


def test_blob_listing_keeps_only_matching_application_files():
    provider = object.__new__(AzureBlobStorageProvider)
    provider._brand_key = "prevaiq"
    modified = datetime(2026, 11, 5, 10, tzinfo=timezone.utc)
    names = [
        "brands/prevaiq/applications/app-1/files/.conversation-a1.json",
        "brands/prevaiq/applications/app-1/files/claim.pdf",
        "brands/prevaiq/applications/app-1/metadata.json",
        "brands/prevaiq/applications/app-2/files/.conversation-b2.json",
        "brands/prevaiq/applications/app-2/files/nested/.conversation-c3.json",
    ]
    requested: list[str] = []

    def list_blobs(name_starts_with):
        requested.append(name_starts_with)
        return [
            SimpleNamespace(name=name, last_modified=modified)
            for name in names
            if name.startswith(name_starts_with)
        ]

    provider._container_client = SimpleNamespace(list_blobs=list_blobs)

    assert provider.list_files(None, ".conversation-") == [
        ("app-1", ".conversation-a1.json", modified.timestamp()),
        ("app-2", ".conversation-b2.json", modified.timestamp()),
    ]
    assert provider.list_files("app-2", ".conversation-") == [
        ("app-2", ".conversation-b2.json", modified.timestamp()),
    ]
    assert requested[-1] == "brands/prevaiq/applications/app-2/files/.conversation-"


def test_conversation_is_stored_under_the_canonical_application_id(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from app.agents import api_integration

    settings = SimpleNamespace(
        app=SimpleNamespace(
            storage_root="unused", prompts_root=str(Path(__file__).resolve().parents[1] / "prompts")
        )
    )
    monkeypatch.setattr(api_server, "load_settings", lambda: settings)
    monkeypatch.setattr(
        api_server,
        "load_application",
        lambda *args: SimpleNamespace(id="e98d6523", persona="habitation_claims"),
    )
    saved = MagicMock()
    monkeypatch.setattr(api_server, "save_conversation", saved)
    monkeypatch.setattr(
        api_integration,
        "agent_chat",
        AsyncMock(return_value={"response": "OK", "agent": {"timings_ms": {}}}),
    )

    asyncio.run(
        api_server.create_or_continue_conversation(
            "SIN-2026-HAB-04837", api_server.ChatRequest(message="Statut ?")
        )
    )

    assert saved.call_args.args[1] == "e98d6523"
    assert saved.call_args.args[2]["application_id"] == "e98d6523"


@pytest.fixture
def history_client(storage_root, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(storage_root=storage_root)),
    )
    application = FastAPI()
    paths = {"/api/applications/{app_id}/conversations", "/api/conversations"}
    routes = [
        route
        for route in api_server.app.routes
        if getattr(route, "path", "") in paths and "GET" in getattr(route, "methods", set())
    ]
    assert len(routes) == 2, "Both real history routes must be registered"
    application.router.routes.extend(routes)
    return TestClient(application)


@pytest.mark.parametrize(
    "app_id",
    ["swiss-chocolate-storm", "swiss-watch-storm", "wine-cellar"],
)
def test_demo_case_without_saved_chats_has_a_successful_empty_history(history_client, app_id):
    response = history_client.get(f"/api/applications/{app_id}/conversations")
    assert response.status_code == 200
    assert response.json() == {"conversations": []}


def test_missing_local_fixture_route_is_not_missing_conversation_data(history_client):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    path = "/api/applications/swiss-chocolate-storm/conversations"
    incomplete_fixture = TestClient(FastAPI())
    assert incomplete_fixture.get(path).status_code == 404
    assert history_client.get(path).status_code == 200
    assert history_client.get("/api/conversations?limit=50").json() == {"conversations": []}


def test_history_http_routes_return_the_same_saved_conversation(history_client, storage_root):
    conversation = _conversation(
        "saved-chat",
        "swiss-chocolate-storm",
        "2026-11-09T08:00:00Z",
        "Quelle franchise ?",
    )
    api_server.save_conversation(storage_root, "swiss-chocolate-storm", conversation)
    current = history_client.get("/api/applications/swiss-chocolate-storm/conversations")
    every = history_client.get("/api/conversations?limit=50")
    assert current.status_code == every.status_code == 200
    assert current.json() == every.json()
    assert current.json()["conversations"][0]["id"] == "saved-chat"
    assert (
        api_server.load_conversation(storage_root, "swiss-chocolate-storm", "saved-chat")
        == conversation
    )


def test_history_storage_failure_is_not_reported_as_empty_success(history_client, monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("test storage unavailable")

    monkeypatch.setattr(api_server, "list_conversations", unavailable)
    for path in ("/api/applications/wine-cellar/conversations", "/api/conversations"):
        response = history_client.get(path)
        assert response.status_code == 500
        assert "conversations" not in response.json()
