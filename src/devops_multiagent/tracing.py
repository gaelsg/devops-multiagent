from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def configure_tracing(service_name: str) -> None:
    """Configura un TracerProvider global apuntando a Jaeger (OTLP/gRPC).

    Opcional: si OTEL_EXPORTER_OTLP_ENDPOINT no esta seteado, no hace nada
    -- correr sin tracing configurado sigue siendo un modo valido (ej.
    desarrollo local sin el LXC de observability levantado).
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True)))
    trace.set_tracer_provider(provider)
