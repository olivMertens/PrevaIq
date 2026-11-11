from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import processing
from app.orchestration import StageBudget


def _settings() -> SimpleNamespace:
    return SimpleNamespace(openai=SimpleNamespace())


def _usage(prompt: int, completion: int) -> dict:
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
    }


@pytest.fixture
def calls(monkeypatch):
    recorded: list[dict] = []
    answers: list[dict] = []

    def fake_chat_completion(settings, messages, **kwargs):
        recorded.append(kwargs)
        return answers.pop(0)

    monkeypatch.setattr(processing, "chat_completion", fake_chat_completion)
    return SimpleNamespace(recorded=recorded, answers=answers)


def _run() -> dict:
    return processing._run_single_prompt(
        _settings(),
        "damage_assessment",
        "visual_damage_analysis",
        "Assess the damage. {underwriting_policies}",
        "# Schadenmeldung",
        language="en",
    )


def test_empty_reasoning_answer_is_retried_once_without_reasoning(calls):
    calls.answers.extend(
        [
            {"content": "", "usage": _usage(9000, 4000)},
            {"content": '{"severity": "high"}', "usage": _usage(9000, 600)},
        ]
    )

    output = _run()

    assert output["parsed"] == {"severity": "high"}
    assert len(calls.recorded) == 2
    assert "reasoning_effort" not in calls.recorded[0]
    assert calls.recorded[1]["reasoning_effort"] == "none"
    assert calls.recorded[1]["response_format"] == "json_object"
    assert output["usage"] == _usage(18000, 4600)

    budget = StageBudget(stage="analysis", max_seconds=0)
    budget.charge(output["usage"])
    assert budget.tokens_used == 22600


def test_second_empty_answer_is_not_retried_again(calls):
    calls.answers.extend(
        [
            {"content": "", "usage": _usage(9000, 4000)},
            {"content": "", "usage": _usage(9000, 0)},
        ]
    )

    output = _run()

    assert len(calls.recorded) == 2
    assert output["parsed"]["_error"] == "Failed to parse JSON response."


def test_damage_analysis_cut_at_its_token_cap_is_repaired(calls):
    calls.answers.append(
        {
            "content": '{"damage_zones": [{"zone": "shop window"}], "summary": "Hail cracked',
            "usage": _usage(9000, 12000),
        }
    )

    output = _run()

    assert calls.recorded[0]["max_tokens"] == 12000
    assert "_error" not in output["parsed"]
    assert output["parsed"]["damage_zones"] == [{"zone": "shop window"}]
    assert output["parsed"]["_truncated"] is True


def test_non_empty_answer_makes_a_single_call(calls):
    calls.answers.append({"content": '{"severity": "low"}', "usage": _usage(9000, 300)})

    output = _run()

    assert output["parsed"] == {"severity": "low"}
    assert len(calls.recorded) == 1
    assert output["usage"] == _usage(9000, 300)
