"""Telemetry contract tests: Application Insights connection handling, span helpers and agent spans.

No network and no live LLM: spans go to an in-memory exporter and the Azure SDKs are stubbed.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from types import SimpleNamespace

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from app import telemetry
from app.agents.errors import AgentServiceError
from app.utils import setup_logging

IKEY = "12345678-aaaa-bbbb-cccc-1234567890ab"
CONNECTION_STRING = (
    f"InstrumentationKey={IKEY};"
    "IngestionEndpoint=https://francecentral-1.in.applicationinsights.azure.com/;"
    "LiveEndpoint=https://francecentral.livediagnostics.monitor.azure.com/;"
    "ApplicationId=99999999-0000-0000-0000-000000000000"
)
INGESTION_HOST = "francecentral-1.in.applicationinsights.azure.com"


@pytest.fixture()
def spans(monkeypatch):
    """Route every manual span to an in-memory exporter."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "get_tracer", lambda name="test": provider.get_tracer(name))
    return exporter


def _by_name(exporter: InMemorySpanExporter) -> dict:
    return {span.name: span for span in exporter.get_finished_spans()}


# ── Application Insights connection ─────────────────────────────────────────


def test_connection_description_masks_the_instrumentation_key():
    described = telemetry._describe_connection(telemetry._parse_connection_string(CONNECTION_STRING))
    assert described["ingestion_host"] == INGESTION_HOST
    assert described["instrumentation_key"] == "12345678..."
    assert "aaaa" not in str(described)


def test_configure_telemetry_stays_disabled_without_connection_string(monkeypatch, caplog):
    monkeypatch.setattr(telemetry, "_initialized", False)
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    with caplog.at_level(logging.INFO, logger="underwriting_assistant"):
        telemetry.configure_telemetry()
    assert "APPLICATIONINSIGHTS_CONNECTION_STRING is not set" in caplog.text
    assert telemetry._initialized is False


def test_configure_telemetry_rejects_a_connection_string_without_key(monkeypatch, caplog):
    def must_not_configure(**kwargs):
        raise AssertionError("configure_azure_monitor must not be reached")

    monkeypatch.setattr(telemetry, "_initialized", False)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", "IngestionEndpoint=https://x.example/")
    monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", must_not_configure)
    with caplog.at_level(logging.WARNING, logger="underwriting_assistant"):
        telemetry.configure_telemetry()
    assert "no InstrumentationKey" in caplog.text
    assert telemetry._initialized is False


def test_configure_telemetry_emits_a_connection_check_span_and_never_logs_the_key(
    monkeypatch, caplog, spans
):
    configured: dict = {}
    fake_openai_module = types.ModuleType("opentelemetry.instrumentation.openai_v2")
    fake_openai_module.OpenAIInstrumentor = lambda: SimpleNamespace(instrument=lambda: None)
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation.openai_v2", fake_openai_module)
    monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", configured.update)
    monkeypatch.setattr(telemetry, "_initialized", False)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", CONNECTION_STRING)
    monkeypatch.setenv("OTEL_SERVICE_NAME", "TestService")

    with caplog.at_level(logging.DEBUG, logger="underwriting_assistant"):
        telemetry.configure_telemetry()

    assert telemetry._initialized is True
    assert configured["connection_string"] == CONNECTION_STRING
    check = _by_name(spans)["app_insights.connection_check"]
    assert check.attributes["workbenchiq.telemetry.ingestion_host"] == INGESTION_HOST
    assert "Application Insights telemetry enabled: service=TestService" in caplog.text
    assert "connection check span emitted" in caplog.text
    assert IKEY not in caplog.text and IKEY not in str(dict(check.attributes))


def test_configure_telemetry_logs_a_failed_configuration_and_stays_disabled(monkeypatch, caplog):
    def broken(**kwargs):
        raise RuntimeError("exporter unavailable")

    monkeypatch.setattr("azure.monitor.opentelemetry.configure_azure_monitor", broken)
    monkeypatch.setattr(telemetry, "_initialized", False)
    monkeypatch.setenv("APPLICATIONINSIGHTS_CONNECTION_STRING", CONNECTION_STRING)
    monkeypatch.setenv("OTEL_SERVICE_NAME", "TestService")
    with caplog.at_level(logging.WARNING, logger="underwriting_assistant"):
        telemetry.configure_telemetry()
    assert "Failed to configure Azure Monitor telemetry" in caplog.text
    assert telemetry._initialized is False


def test_setup_logging_honours_log_level(monkeypatch):
    logger = logging.getLogger("underwriting_assistant")
    saved_handlers, saved_level = list(logger.handlers), logger.level
    try:
        logger.handlers.clear()
        monkeypatch.setenv("LOG_LEVEL", "debug")
        assert setup_logging().level == logging.DEBUG

        logger.handlers.clear()
        monkeypatch.setenv("LOG_LEVEL", "not-a-level")
        assert setup_logging().level == logging.INFO
    finally:
        logger.handlers[:] = saved_handlers
        logger.setLevel(saved_level)


# ── Span helpers ────────────────────────────────────────────────────────────


def test_start_span_records_the_exception_and_sets_error_status(spans):
    with pytest.raises(ValueError):
        with telemetry.start_span("agent.run", {"kept": "yes", "dropped": None}):
            raise ValueError("boom")

    [finished] = spans.get_finished_spans()
    assert finished.status.status_code is StatusCode.ERROR
    assert [event.name for event in finished.events] == ["exception"]
    assert dict(finished.attributes) == {"kept": "yes"}


def test_record_span_error_flags_a_handled_failure(spans):
    with telemetry.start_span("step", kind="client") as span:
        telemetry.record_span_error(span, "timed out after 150s", error_type="timeout")

    [finished] = spans.get_finished_spans()
    assert finished.kind is SpanKind.CLIENT
    assert finished.status.status_code is StatusCode.ERROR
    assert finished.attributes["error.type"] == "timeout"


def test_spans_degrade_to_a_noop_without_a_tracer(monkeypatch):
    monkeypatch.setattr(telemetry, "get_tracer", lambda name="test": None)
    with telemetry.start_span("step", {"k": "v"}) as span:
        span.set_attribute("k", "v")
        telemetry.record_span_error(span, "boom")  # must not raise


def test_add_span_event_attaches_to_the_current_span_only(spans):
    telemetry.add_span_event("ignored")  # no active span: must be a no-op
    with telemetry.start_span("step"):
        telemetry.add_span_event("refusal_retry", {"agent": "ExtractAgent", "skipped": None})

    [finished] = spans.get_finished_spans()
    [event] = finished.events
    assert event.name == "refusal_retry"
    assert dict(event.attributes) == {"agent": "ExtractAgent"}


# ── Agent spans ─────────────────────────────────────────────────────────────


def test_workflow_step_span_flags_timeouts_and_failures(monkeypatch, spans):
    from app.agents import workflows as wf

    async def fake_run(agent, prompt, *, agent_name, max_retries=1):
        if agent_name == "Slow":
            await asyncio.sleep(1)
        if agent_name == "Broken":
            raise RuntimeError("provider down")
        return "analysis"

    monkeypatch.setattr(wf, "_run_agent_with_refusal_retry", fake_run)
    monkeypatch.setattr(wf, "AGENT_TIMEOUT_SECONDS", 0.01)

    async def run():
        return [await wf._run_step(None, "prompt", agent_name=name) for name in ("Fast", "Slow", "Broken")]

    fast, slow, broken = asyncio.run(run())

    assert fast == "analysis"
    assert "délai dépassé" in slow and "indisponible" in broken
    recorded = _by_name(spans)
    assert recorded["workflow.step Fast"].status.status_code is StatusCode.UNSET
    assert recorded["workflow.step Fast"].attributes["workbenchiq.response_chars"] == len("analysis")
    assert recorded["workflow.step Slow"].status.status_code is StatusCode.ERROR
    assert recorded["workflow.step Slow"].attributes["error.type"] == "timeout"
    assert recorded["workflow.step Broken"].status.status_code is StatusCode.ERROR
    assert recorded["workflow.step Broken"].attributes["error.type"] == "RuntimeError"


def test_agent_workflow_failure_sets_error_attributes_on_its_span(monkeypatch, spans):
    from app.agents import api_integration, workflows

    async def failing(settings, app_id, persona, language="fr"):
        raise RuntimeError("provider down")

    monkeypatch.setattr(workflows, "create_express_workflow", failing)
    with pytest.raises(AgentServiceError) as raised:
        asyncio.run(api_integration.agent_workflow(object(), "APP-1", "express"))

    [span] = spans.get_finished_spans()
    assert span.name == f"Workflow:{workflows.WORKFLOWS['express']['name']}"
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"] == raised.value.code
    assert span.attributes["workbenchiq.request_id"] == raised.value.request_id


def test_agent_chat_direct_tool_route_gets_a_child_tool_span(monkeypatch, spans):
    from app.agents import api_integration, tools

    monkeypatch.setattr(tools, "get_application_summary", lambda application_id: "Résumé du dossier")
    monkeypatch.setattr(tools, "query_fabric_data", lambda question, persona="": "42 sinistres")

    result = asyncio.run(
        api_integration.agent_chat(object(), "APP-1", "Combien de sinistres ?", agent_type="data")
    )

    assert result["response"] == "42 sinistres"
    recorded = _by_name(spans)
    chat, tool = recorded["FabricDataAgent"], recorded["execute_tool query_fabric_data"]
    assert tool.parent.span_id == chat.context.span_id
    assert tool.attributes["gen_ai.tool.name"] == "query_fabric_data"
    assert chat.attributes["gen_ai.agent.name"] == "FabricDataAgent"


def test_agent_chat_logs_completion_with_token_usage(monkeypatch, spans, caplog):
    from app.agents import agents, api_integration, tools

    class FakeAgent:
        async def run(self, message):
            usage = {"input_token_count": 10, "output_token_count": 5}
            return SimpleNamespace(text="Réponse", messages=[], usage_details=usage)

    async def fake_analysis_agent(settings):
        return FakeAgent()

    monkeypatch.setattr(agents, "create_analysis_agent", fake_analysis_agent)
    monkeypatch.setattr(tools, "get_application_summary", lambda application_id: "Résumé du dossier")

    with caplog.at_level(logging.INFO, logger="underwriting_assistant"):
        result = asyncio.run(
            api_integration.agent_chat(object(), "APP-1", "Analyse ce dossier", agent_type="analysis")
        )

    assert result["response"] == "Réponse"
    assert "agent_chat done: agent=AnalysisAgent" in caplog.text
    assert "tokens_in=10 tokens_out=5" in caplog.text
    # Token counts stay on the framework's own spans: repeating gen_ai.usage.* here would double count.
    span = _by_name(spans)["AnalysisAgent"]
    assert not any(key.startswith("gen_ai.usage") for key in span.attributes)
    timings = result["agent"]["timings_ms"]
    assert timings["total_ms"] >= timings["setup_ms"]
    assert timings["setup_ms"] >= timings["imports_ms"] >= 0
    assert timings["context_ms"] >= 0
    assert timings["run_ms"] >= 0
    assert "chat.load_context" in _by_name(spans)


def test_agent_chat_failure_sets_the_error_code_on_the_span(monkeypatch, spans):
    from app.agents import agents, api_integration, tools

    class BrokenAgent:
        async def run(self, message):
            raise RuntimeError("provider down")

    async def fake_analysis_agent(settings):
        return BrokenAgent()

    monkeypatch.setattr(agents, "create_analysis_agent", fake_analysis_agent)
    monkeypatch.setattr(tools, "get_application_summary", lambda application_id: "Résumé du dossier")

    with pytest.raises(AgentServiceError) as raised:
        asyncio.run(api_integration.agent_chat(object(), "APP-1", "Analyse ce dossier", agent_type="analysis"))

    span = _by_name(spans)["AnalysisAgent"]
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"] == raised.value.code
    assert span.attributes["workbenchiq.request_id"] == raised.value.request_id


# ── Foundry agent calls (web intelligence, Fabric) ──────────────────────────


def _fraud_settings():
    return SimpleNamespace(web_intelligence_agent_name="WebIntel", foundry_project_endpoint="https://foundry.example")


def test_web_intelligence_span_is_entered_and_carries_the_result(monkeypatch, spans):
    from app.agents import tools

    response = SimpleNamespace(output_text='{"event_verified": true, "findings": [{"title": "Arrêté"}]}', output=[])
    project = SimpleNamespace(
        get_openai_client=lambda: SimpleNamespace(responses=SimpleNamespace(create=lambda **kwargs: response))
    )
    monkeypatch.setattr("azure.ai.projects.AIProjectClient", lambda **kwargs: project)
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: object())

    result = tools._run_web_intelligence(
        _fraud_settings(), claim_date="01/06/2026", claim_location="12 rue des Lilas, Nîmes",
        claim_nature="Inondation", claim_type="habitation", declared_amount="5000",
    )

    assert result["event_verified"] is True
    [span] = spans.get_finished_spans()
    assert span.name == "web_intelligence.query" and span.kind is SpanKind.CLIENT
    assert span.attributes["workbenchiq.findings_count"] == 1
    assert span.attributes["workbenchiq.citations_count"] == 0
    assert span.attributes["gen_ai.agent.name"] == "WebIntel"
    assert not any("location" in key for key in span.attributes)
    assert "Nîmes" not in str(dict(span.attributes))


def test_web_intelligence_failure_is_recorded_on_the_span(monkeypatch, spans):
    from app.agents import tools

    def unavailable(**kwargs):
        raise RuntimeError("foundry down")

    monkeypatch.setattr("azure.ai.projects.AIProjectClient", unavailable)
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: object())

    result = tools._run_web_intelligence(
        _fraud_settings(), claim_date="", claim_location="", claim_nature="", claim_type="auto",
        declared_amount="",
    )

    assert result == {"error": "foundry down"}
    [span] = spans.get_finished_spans()
    assert span.status.status_code is StatusCode.ERROR
    assert span.attributes["error.type"] == "RuntimeError"


def test_fabric_query_span_and_cleanup_failure_is_logged(monkeypatch, spans, caplog):
    from app.agents import tools

    def delete_version(**kwargs):
        raise RuntimeError("delete forbidden")

    project = SimpleNamespace(
        connections=SimpleNamespace(get=lambda name: SimpleNamespace(id=f"/connections/{name}")),
        agents=SimpleNamespace(
            create_version=lambda **kwargs: SimpleNamespace(name=kwargs["agent_name"], version="7"),
            delete_version=delete_version,
        ),
        get_openai_client=lambda: SimpleNamespace(
            responses=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(output_text="42 sinistres"))
        ),
    )
    monkeypatch.setattr("azure.ai.projects.AIProjectClient", lambda **kwargs: project)
    monkeypatch.setattr("azure.identity.DefaultAzureCredential", lambda: object())
    monkeypatch.setattr(
        "app.config.load_settings",
        lambda: SimpleNamespace(foundry=SimpleNamespace(project_endpoint="https://foundry.example/api/projects/p")),
    )
    monkeypatch.setenv("FABRIC_CONNECTION_NAME", "fabric-conn")

    with caplog.at_level(logging.WARNING, logger="underwriting_assistant"):
        answer = tools.query_fabric_data("Combien de sinistres ?", persona="habitation_claims")

    assert answer == "42 sinistres"
    [span] = spans.get_finished_spans()
    assert span.name == "fabric_data_agent.query" and span.kind is SpanKind.CLIENT
    assert span.status.status_code is StatusCode.UNSET
    assert span.attributes["gen_ai.agent.version"] == "7"
    assert span.attributes["workbenchiq.fabric.connection"] == "fabric-conn"
    assert "could not delete temporary agent" in caplog.text
