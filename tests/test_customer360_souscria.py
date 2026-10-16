"""Tests for Souscr'IA acquisition enrichment of the Customer 360 view.

Pure-function tests (no live Souscr'IA server): they prove that
``apply_souscria_acquisition`` enriches the view when given a context dict and is
a graceful no-op when the connector is off (``None``) or unavailable.
"""

from __future__ import annotations

from app.customer360 import (
    Customer360View,
    CustomerJourneyEvent,
    CustomerProfile,
    apply_souscria_acquisition,
)


def _view() -> Customer360View:
    profile = CustomerProfile(
        id="PRV-006",
        name="DUPONT Jean",
        date_of_birth="1979-04-12",
        email="jean.dupont@email.fr",
        phone="",
        address="",
        customer_since="2022-09-05",
        risk_tier="medium",
        souscria_ref="SOC-001",
    )
    existing = CustomerJourneyEvent(
        date="2023-01-01T00:00:00Z",
        persona="underwriting",
        application_id="app-1",
        event_type="application_submitted",
        title="Dossier",
        summary="",
        status="completed",
    )
    return Customer360View(profile=profile, journey_events=[existing])


def _raw_context() -> dict:
    return {
        "available": True,
        "client_id": "SOC-001",
        "contracts": [{"id": "AUTO-1", "product": "auto", "annual_premium": 744}],
        "advisor": {"first_name": "Catherine", "last_name": "Moreau", "agency": "Lyon Centre"},
        "next_best_actions": [{"id": "NBA-1", "label": "Renouveler MRH"}],
        "interactions": [
            {
                "type": "souscription",
                "channel": "agence",
                "date": "2026-04-15T14:22:00Z",
                "summary": "Renouvellement MRH",
                "outcome": "souscrit",
            }
        ],
        "errors": [],
        "source": "souscria-mcp",
    }


def test_apply_souscria_acquisition_enriches_view():
    view = _view()
    apply_souscria_acquisition(view, _raw_context())

    assert view.souscria_acquisition is not None
    assert view.souscria_acquisition.available is True
    assert view.souscria_acquisition.client_id == "SOC-001"
    assert view.souscria_acquisition.contracts[0]["product"] == "auto"
    assert view.souscria_acquisition.advisor["last_name"] == "Moreau"
    assert view.souscria_acquisition.next_best_actions[0]["label"] == "Renouveler MRH"

    # Business interaction injected as a journey event and sorted most-recent first.
    assert len(view.journey_events) == 2
    top = view.journey_events[0]
    assert top.persona == "souscria_acquisition"
    assert top.title == "Souscription"
    assert top.status == "approved"
    assert top.application_id == ""  # not a workbench dossier → non-clickable
    assert top.key_metrics["Source"] == "Souscr'IA"


def test_apply_souscria_acquisition_noop_when_not_configured():
    view = _view()
    before = list(view.journey_events)

    apply_souscria_acquisition(view, None)  # connector off

    assert view.souscria_acquisition is None
    assert view.journey_events == before


def test_apply_souscria_acquisition_noop_when_unavailable():
    view = _view()
    apply_souscria_acquisition(view, {"available": False, "client_id": "SOC-001"})

    assert view.souscria_acquisition is None
    assert len(view.journey_events) == 1
