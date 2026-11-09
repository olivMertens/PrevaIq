from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api_server
from app.underwriting_policies import get_policy_file_for_persona

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


@pytest.mark.parametrize(
    "persona",
    ["habitation_claims", "property_casualty_claims", "underwriting", "automotive_claims"],
)
def test_policy_detail_uses_the_same_catalog_as_the_persona_list(monkeypatch, persona):
    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(prompts_root=str(PROMPTS))),
    )
    path = Path(get_policy_file_for_persona(str(PROMPTS), persona))
    expected = json.loads(path.read_text(encoding="utf-8"))["policies"][0]
    result = asyncio.run(api_server.get_policy_by_id(expected["id"], persona))
    assert result == expected


def test_policy_detail_respects_the_configured_catalog_root(monkeypatch, tmp_path):
    policy = {"id": "PC-LOCAL-001", "name": "Local policy contract", "criteria": []}
    path = Path(get_policy_file_for_persona(str(tmp_path), "habitation_claims"))
    path.write_text(json.dumps({"policies": [policy]}), encoding="utf-8")
    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(prompts_root=str(tmp_path))),
    )
    assert asyncio.run(api_server.get_policy_by_id(policy["id"], "habitation_claims")) == policy
    with pytest.raises(HTTPException) as error:
        asyncio.run(api_server.get_policy_by_id("PC-MISSING", "habitation_claims"))
    assert error.value.status_code == 404
