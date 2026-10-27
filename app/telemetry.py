import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlite3 import SQLite3Instrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor


def setup_tracing(app=None):
    """Initialize OpenTelemetry tracing."""
    service_name = os.getenv("OTEL_SERVICE_NAME", "dashboard")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    
    # Create resource with service name
    resource = Resource.create({SERVICE_NAME: service_name})
    
    # Create tracer provider
    provider = TracerProvider(resource=resource)
    
    # Add OTLP exporter
    otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
    
    # Set global tracer provider
    trace.set_tracer_provider(provider)
    
    # Auto-instrument libraries
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()
    SQLite3Instrumentor().instrument()
    
    if app:
        FastAPIInstrumentor.instrument_app(app)
    
    return trace.get_tracer(__name__)


def get_tracer(name: str):
    """Get a tracer instance."""
    return trace.get_tracer(name)