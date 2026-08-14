"""Cloud Trace export for ADK's native OpenTelemetry spans.

ADK instruments every turn out of the box (invocation, agent, model call, tool
call spans, with token usage even through LiteLLM). This wires those spans to
Cloud Trace via ADK's own ADC-authorized OTLP exporter, adds spans for our
plain-requests speech hops, and correlates structured logs with traces.

Best-effort by design: any failure here degrades to "no tracing", never to a
broken app. Set DISABLE_TRACING=1 to opt out entirely.
"""
import logging
import os


def setup() -> None:
    if os.environ.get("DISABLE_TRACING") == "1":
        return
    try:
        import google.auth
        from google.adk.telemetry.google_cloud import get_gcp_exporters, get_gcp_resource
        from google.adk.telemetry.setup import maybe_set_otel_providers

        credentials, project = google.auth.default()  # the identity the service runs as
        if not project:
            return
        maybe_set_otel_providers(  # install as the app's OpenTelemetry provider
            otel_hooks_to_setup=[
                get_gcp_exporters(  # exports spans to Cloud Trace
                    enable_cloud_tracing=True, google_auth=(credentials, project)
                )
            ],
            otel_resource=get_gcp_resource(project),
        )
    except Exception as e:  # noqa: BLE001
        logging.warning("tracing disabled: %s", e)
        return

    try:
        # Spans for the outbound speech-service calls (plain requests, which ADK
        # doesn't instrument) so transcribe/speak show up in the turn waterfall.
        from opentelemetry.instrumentation.requests import RequestsInstrumentor

        RequestsInstrumentor().instrument()
    except Exception:  # noqa: BLE001
        pass

    if os.environ.get("K_SERVICE"):  # Cloud Run only; keep local logs plain
        try:
            import google.cloud.logging

            google.cloud.logging.Client().setup_logging()
        except Exception:  # noqa: BLE001
            pass
