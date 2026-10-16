from app.config import load_settings, validate_settings


def test_load_settings_smoke():
    settings = load_settings()
    assert settings is not None
    assert hasattr(settings, "content_understanding")
    assert hasattr(settings, "openai")
    assert hasattr(settings, "app")


def test_validate_settings_returns_list():
    settings = load_settings()
    errors = validate_settings(settings)
    assert isinstance(errors, list)


def test_openai_model_routing_defaults(monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_MODEL_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_REASONING_EFFORT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_CHAT_MODEL_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_NANO_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_NANO_MODEL_NAME", raising=False)
    monkeypatch.delenv("FRAUD_DETECTION_DEPLOYMENT", raising=False)

    settings = load_settings()

    assert settings.openai.deployment_name == "gpt-5.4-mini"
    assert settings.openai.model_name == "gpt-5.4-mini"
    assert settings.openai.api_version == "2025-04-01-preview"
    assert settings.openai.reasoning_effort == "low"
    assert settings.openai.get_deployment("chat") == ("gpt-5.4-mini", "gpt-5.4-mini")
    assert settings.openai.get_deployment("nano") == ("gpt-5.4-nano", "gpt-5.4-nano")
    assert settings.fraud_detection.deployment_name == "gpt-5.4-mini"


def test_content_understanding_model_alias_defaults(monkeypatch):
    monkeypatch.delenv("AZURE_CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT", raising=False)
    monkeypatch.delenv("AZURE_CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT", raising=False)

    settings = load_settings()

    assert settings.content_understanding.completion_deployment == "gpt-5.4-mini"
    assert settings.content_understanding.embedding_deployment == "text-embedding-3-large"


def test_markitdown_settings_from_env(monkeypatch):
    monkeypatch.setenv("MARKITDOWN_ENABLED", "true")
    monkeypatch.setenv("MARKITDOWN_MODE", "cu")
    monkeypatch.setenv("MARKITDOWN_USE_CONTENT_UNDERSTANDING", "true")
    monkeypatch.setenv("MARKITDOWN_PREFERRED_EXTENSIONS", "eml,msg,doc")

    settings = load_settings()

    assert settings.markitdown.enabled is True
    assert settings.markitdown.mode == "cu"
    assert settings.markitdown.use_content_understanding is True
    assert settings.markitdown.preferred_extensions == (".eml", ".msg", ".doc")
