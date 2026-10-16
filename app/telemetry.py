"""WorkbenchIQ Telemetry — OpenTelemetry + Azure Monitor for agent tracing.

Configures the Azure Monitor OpenTelemetry distro to export traces
(including GenAI semantic convention spans) to Application Insights.
Agent spans appear in the Foundry project's Tracing view.

Key Foundry requirements:
- opentelemetry-instrumentation-openai-v2 auto-instruments all OpenAI SDK calls
  with GenAI semantic convention spans (gen_ai.operation.name, gen_ai.request.model,
  gen_ai.usage.input_tokens, etc.)
- OTEL_SERVICE_NAME identifies the service in Foundry Tracing UI (cloud_roleName)
- OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=true captures prompt/response content

Per-claim correlation:
- A FastAPI middleware (install_claim_correlation_middleware) extracts the claim_id
  from the URL path and sets it as OTel baggage + current-span attribute.
- A BaggageSpanProcessor then copies the baggage entry onto every child span (incl.
  auto-instrumented OpenAI spans), so cost/latency can be aggregated per dossier in KQL.

Manual spans and logs:
- start_span / record_span_error / add_span_event wrap the agent, workflow-step and
  Foundry agent calls; exceptions leaving a span set its ERROR status.
- configure_telemetry emits an ``app_insights.connection_check`` span at startup so the
  connection can be verified in the ``dependencies`` table. Set LOG_LEVEL=DEBUG for details.
"""

from __future__ import annotations

import os
import re
import time
from contextlib import contextmanager
from typing import Any, Iterator, Mapping
from urllib.parse import urlparse

from .utils import setup_logging

# Not logging.getLogger(__name__): the root logger sits at WARNING under gunicorn, so
# INFO/DEBUG records of that logger would be dropped.
logger = setup_logging()

_initialized = False

# Path regex captures claim_id from routes like /claims/{claim_id}/... or
# /claims/habitation/{claim_id}/... — anything between "/claims/" (optionally
# followed by a known prefix) and the next "/" or end of path.
_CLAIM_ID_RE = re.compile(
    r"/claims/(?:habitation/|auto/)?(?P<cid>[A-Za-z0-9_-]+)(?:/|$)"
)

_BAGGAGE_KEYS_TO_PROMOTE = ("claim.id", "brand")


def _parse_connection_string(conn_str: str) -> dict[str, str]:
    """Split ``Key=Value;Key=Value`` into a dict with lower-cased keys."""
    parts: dict[str, str] = {}
    for item in conn_str.split(";"):
        key, separator, value = item.partition("=")
        if separator and key.strip():
            parts[key.strip().lower()] = value.strip()
    return parts


def _describe_connection(parts: Mapping[str, str]) -> dict[str, str]:
    """Log-safe view of a parsed connection string: the instrumentation key is masked."""
    ikey = parts.get("instrumentationkey", "")
    ingestion = parts.get("ingestionendpoint", "")
    return {
        "instrumentation_key": f"{ikey[:8]}..." if len(ikey) > 8 else "***",
        "ingestion_host": urlparse(ingestion).netloc or "default",
        "application_id": parts.get("applicationid", ""),
    }


def configure_telemetry() -> None:
    """Initialize Azure Monitor OpenTelemetry exporter + OpenAI SDK auto-instrumentation.

    Reads APPLICATIONINSIGHTS_CONNECTION_STRING from env.
    Sets OTEL_SERVICE_NAME if not already set.
    No-op if the env var is missing or malformed, or if already initialized.
    The instrumentation key is never logged in full.
    """
    global _initialized
    if _initialized:
        logger.debug("Telemetry already configured - skipping")
        return

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_str:
        logger.info("Application Insights disabled: APPLICATIONINSIGHTS_CONNECTION_STRING is not set")
        return

    parts = _parse_connection_string(conn_str)
    if not parts.get("instrumentationkey"):
        logger.warning(
            "Application Insights disabled: APPLICATIONINSIGHTS_CONNECTION_STRING has no "
            "InstrumentationKey (keys found: %s)",
            sorted(parts) or "none",
        )
        return
    connection = _describe_connection(parts)
    logger.debug("Application Insights connection string parsed: %s", connection)

    # Set service name for Foundry Tracing UI (shows as cloud_roleName)
    if not os.getenv("OTEL_SERVICE_NAME"):
        from app.brands import get_current_brand_profile

        os.environ["OTEL_SERVICE_NAME"] = get_current_brand_profile().app_name
        logger.debug("OTEL_SERVICE_NAME not set - defaulting to the brand app name")
    logger.debug(
        "Telemetry settings: service=%s capture_message_content=%s",
        os.environ["OTEL_SERVICE_NAME"],
        os.getenv("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false"),
    )

    try:
        from azure.monitor.opentelemetry import configure_azure_monitor

        started = time.perf_counter()
        configure_azure_monitor(
            connection_string=conn_str,
            enable_live_metrics=False,
            instrumentation_options={
                "azure_sdk": {"enabled": True},
                "fastapi": {"enabled": True},
                "requests": {"enabled": True},
            },
        )
        logger.debug(
            "configure_azure_monitor completed in %d ms (azure_sdk, fastapi, requests instrumented)",
            (time.perf_counter() - started) * 1000,
        )

        # Auto-instrument OpenAI SDK — creates GenAI semantic convention spans
        # for every chat.completions.create() call (model, tokens, latency)
        try:
            from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

            OpenAIInstrumentor().instrument()
            logger.info("OpenAI SDK auto-instrumented with GenAI semantic conventions")
        except ImportError:
            logger.warning("opentelemetry-instrumentation-openai-v2 not installed — "
                           "OpenAI calls will not have GenAI spans in Foundry")

        # Promote baggage entries (claim.id, brand) onto every emitted span,
        # so OpenAI/auto-instrumented spans can be grouped per dossier in KQL.
        _register_baggage_span_processor()

        _initialized = True
    except Exception:
        logger.warning("Failed to configure Azure Monitor telemetry", exc_info=True)
        return

    logger.info(
        "Application Insights telemetry enabled: service=%s ingestion=%s ikey=%s",
        os.environ.get("OTEL_SERVICE_NAME", "unknown"),
        connection["ingestion_host"],
        connection["instrumentation_key"],
    )
    _emit_connection_check_span(connection)


def _emit_connection_check_span(connection: Mapping[str, str]) -> None:
    """Emit one startup span so the connection can be verified end to end.

    The span is exported by the batch processor within seconds; it showing up in the
    ``dependencies`` table proves the key, endpoint and network path all work.
    """
    with start_span(
        "app_insights.connection_check",
        {"workbenchiq.telemetry.ingestion_host": connection["ingestion_host"]},
        tracer_name="workbenchiq.telemetry",
    ) as span:
        recording = bool(span.is_recording())
        trace_id = span.get_span_context().trace_id if recording else 0
    if recording:
        logger.info(
            "Application Insights connection check span emitted: trace_id=%032x "
            "(look for 'app_insights.connection_check' in the dependencies table)",
            trace_id,
        )
    else:
        logger.warning("Application Insights connection check span was not recorded (no active tracing)")


def _register_baggage_span_processor() -> None:
    """Attach a SpanProcessor that copies selected baggage entries to span attributes.

    OTel baggage is propagated across the call stack but does NOT automatically
    appear on spans. This processor reads baggage at span-start and writes the
    keys listed in _BAGGAGE_KEYS_TO_PROMOTE as span attributes, so they show up
    in App Insights customDimensions and can be used in KQL group-by clauses.
    """
    try:
        from opentelemetry import baggage, trace
        from opentelemetry.sdk.trace import SpanProcessor

        class _BaggageSpanProcessor(SpanProcessor):
            def on_start(self, span, parent_context=None):  # type: ignore[override]
                try:
                    ctx = parent_context
                    for key in _BAGGAGE_KEYS_TO_PROMOTE:
                        val = baggage.get_baggage(key, context=ctx)
                        if val is not None:
                            span.set_attribute(key, str(val))
                except Exception:
                    pass

            def on_end(self, span):  # type: ignore[override]
                pass

            def shutdown(self):  # type: ignore[override]
                pass

            def force_flush(self, timeout_millis: int = 30000) -> bool:  # type: ignore[override]
                return True

        provider = trace.get_tracer_provider()
        if hasattr(provider, "add_span_processor"):
            provider.add_span_processor(_BaggageSpanProcessor())
            logger.info("Baggage span processor registered (keys=%s)", _BAGGAGE_KEYS_TO_PROMOTE)
    except Exception:
        logger.warning("Failed to register baggage span processor", exc_info=True)


def install_claim_correlation_middleware(app) -> None:
    """Register a FastAPI middleware that sets claim.id + brand in OTel baggage.

    Extracts claim_id from URL path (e.g. /claims/{cid}/...) and the brand
    from the X-Brand request header (falls back to BRAND env var). Both are
    stored as baggage so they propagate to all downstream spans, and as
    attributes on the active server span so they're queryable directly.

    No-op if OpenTelemetry is not installed or telemetry was not configured.
    """
    try:
        from opentelemetry import baggage, context as otel_context, trace
    except ImportError:
        return

    @app.middleware("http")
    async def _claim_correlation_middleware(request, call_next):
        token = None
        try:
            ctx = otel_context.get_current()
            claim_id = None
            match = _CLAIM_ID_RE.search(request.url.path or "")
            if match:
                cid = match.group("cid")
                # Skip non-identifier segments to avoid polluting baggage with
                # collection routes like /claims/pending or /claims/policies.
                if cid not in {"pending", "policies", "submit"}:
                    claim_id = cid
                    ctx = baggage.set_baggage("claim.id", cid, context=ctx)
                    span = trace.get_current_span()
                    if span and span.is_recording():
                        span.set_attribute("claim.id", cid)

            brand = request.headers.get("x-brand") or os.getenv("BRAND")
            if brand:
                ctx = baggage.set_baggage("brand", brand, context=ctx)
                span = trace.get_current_span()
                if span and span.is_recording():
                    span.set_attribute("brand", brand)
            if claim_id or brand:
                logger.debug(
                    "OTel correlation: path=%s claim.id=%s brand=%s", request.url.path, claim_id, brand
                )

            token = otel_context.attach(ctx)
            return await call_next(request)
        finally:
            if token is not None:
                otel_context.detach(token)


def get_tracer(name: str = "workbenchiq"):
    """Return an OpenTelemetry tracer for manual span creation.

    Returns None if OTel is not installed; before configure_telemetry() the API's
    proxy tracer is a no-op.
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return None


class _NoopSpan:
    """Stand-in span so call sites need no None checks when OpenTelemetry is missing."""

    def __getattr__(self, _name: str):
        return lambda *args, **kwargs: None


_NOOP_SPAN = _NoopSpan()


@contextmanager
def start_span(
    name: str,
    attributes: Mapping[str, Any] | None = None,
    *,
    tracer_name: str = "workbenchiq.agents",
    kind: str = "internal",
) -> Iterator[Any]:
    """Open a span that is current for the duration of the ``with`` block.

    An exception leaving the block is recorded on the span and sets its ERROR status.
    ``None`` attribute values are dropped; ``kind`` is ``internal`` or ``client``.
    """
    tracer = get_tracer(tracer_name)
    if tracer is None:
        yield _NOOP_SPAN
        return

    from opentelemetry import trace

    with tracer.start_as_current_span(
        name,
        kind=getattr(trace.SpanKind, kind.upper()),
        attributes={key: value for key, value in (attributes or {}).items() if value is not None},
    ) as span:
        yield span


def record_span_error(span: Any, error: BaseException | str, *, error_type: str | None = None) -> None:
    """Flag ``span`` as failed for an error the caller handles itself (nothing is raised)."""
    if span is _NOOP_SPAN:
        return
    from opentelemetry.trace import Status, StatusCode

    if isinstance(error, BaseException):
        span.record_exception(error)
        description = f"{type(error).__name__}: {error}"
        error_type = error_type or type(error).__name__
    else:
        description = error
        error_type = error_type or "error"
    span.set_attribute("error.type", error_type)
    span.set_status(Status(StatusCode.ERROR, description[:200]))


def add_span_event(name: str, attributes: Mapping[str, Any] | None = None) -> None:
    """Attach an event to the current span (no-op when no recording span is active)."""
    try:
        from opentelemetry import trace
    except ImportError:
        return
    span = trace.get_current_span()
    if span.is_recording():
        span.add_event(
            name, attributes={key: value for key, value in (attributes or {}).items() if value is not None}
        )
