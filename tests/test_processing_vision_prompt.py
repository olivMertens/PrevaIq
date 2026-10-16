from types import SimpleNamespace
from unittest.mock import patch

from app.processing import _gpt_vision_describe_image


def test_gpt_vision_prompt_uses_driver_perspective_for_left_right():
    settings = SimpleNamespace(openai=SimpleNamespace())

    with patch("app.processing.chat_completion", return_value={"content": "OK"}) as mock_chat:
        _gpt_vision_describe_image(settings, b"fake-image-bytes", "photo.jpg")

    messages = mock_chat.call_args.args[1]
    system_prompt = messages[0]["content"]

    assert "du point de vue du conducteur assis dans le véhicule" in system_prompt
    assert "PAS du point de vue du photographe" in system_prompt
