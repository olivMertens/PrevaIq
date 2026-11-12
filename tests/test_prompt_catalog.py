from __future__ import annotations

import pytest

from app.personas import PersonaType
from app.prompts import analysis_steps, load_prompts


def test_catalog_metadata_and_persona_descriptions_are_not_steps() -> None:
    catalog = {
        "metadata": {"version": "1.2", "description": "Catalog of {brand}"},
        "summary": {
            "system": "You are an expert.",
            "facts": "List the facts.",
            "risk": {"prompt": "Rate the risk."},
            "conventions": {"units": "metric"},
        },
        "single": {"prompt": "One prompt."},
    }

    assert analysis_steps(catalog) == {
        "summary": {"facts": "List the facts.", "risk": "Rate the risk."},
        "single": {"single": "One prompt."},
    }


@pytest.mark.parametrize("persona", list(PersonaType), ids=lambda persona: persona.value)
def test_every_persona_runs_only_real_prompts(persona: PersonaType) -> None:
    steps = analysis_steps(load_prompts("prompts", persona))

    assert steps
    names = {section for section in steps} | {sub for subs in steps.values() for sub in subs}
    assert not names & {"metadata", "system", "version", "description"}
