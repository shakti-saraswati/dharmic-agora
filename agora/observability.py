"""
SAB Observability (OpenTelemetry)

Enabled via environment variables:
- SAB_OTEL_ENABLED=true
- SAB_OTEL_SERVICE_NAME=sab-api
- SAB_OTEL_EXPORTER=console|otlp
- SAB_OTEL_OTLP_ENDPOINT=https://... (only if exporter=otlp)
"""

from __future__ import annotations

import os
from typing import Optional


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def configure_observability() -> bool:
    if not _bool_env("SAB_OTEL_ENABLED", False):
        return False

    service_name = os.environ.get("SAB_OTEL_SERVICE_NAME", "sab-api")
    exporter = os.environ.get("SAB_OTEL_EXPORTER", "console").lower()

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except Exception:
        return False

    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    if exporter == "otlp":
        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            endpoint = os.environ.get("SAB_OTEL_OTLP_ENDPOINT")
            span_exporter = OTLPSpanExporter(endpoint=endpoint) if endpoint else OTLPSpanExporter()
            provider.add_span_processor(BatchSpanProcessor(span_exporter))
        except Exception:
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    return True


def instrument_app(app) -> bool:
    if not _bool_env("SAB_OTEL_ENABLED", False):
        return False
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
    except Exception:
        return False

    LoggingInstrumentor().instrument(set_logging_format=True)
    FastAPIInstrumentor.instrument_app(app)
    return True
