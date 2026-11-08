from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from proof.messaging.models import OutboxEvent
from proof.reconciliation.models import ReconciliationFinding

REGISTRY = CollectorRegistry()
REQUESTS = Counter("proof_http_requests", "Requests by route template and status.",
                   ["route", "method", "status"], registry=REGISTRY)
LATENCY = Histogram("proof_http_request_duration_seconds", "API request duration.",
                    ["route"], registry=REGISTRY)
ERRORS = Counter("proof_domain_errors", "Rejected domain commands.", ["code"], registry=REGISTRY)


def configure_tracing(service: str) -> TracerProvider | None:
    endpoint = os.getenv("PROOF_OTLP_TRACES_ENDPOINT")
    if not endpoint:
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    trace.set_tracer_provider(provider)
    return provider


def scrape(session: Session) -> bytes:
    pending, dead = session.execute(select(
        func.count().filter(OutboxEvent.published_at.is_(None), OutboxEvent.dead_lettered_at.is_(None)),
        func.count().filter(OutboxEvent.dead_lettered_at.is_not(None)),
    )).one()
    findings = session.scalar(select(func.count()).select_from(ReconciliationFinding).where(
        ReconciliationFinding.status == "open",
    ))
    snapshot = CollectorRegistry()
    Gauge("proof_outbox_pending", "Unpublished events eligible for retry.", registry=snapshot).set(pending)
    Gauge("proof_outbox_dead_letters", "Events awaiting operator replay.", registry=snapshot).set(dead)
    Gauge("proof_reconciliation_open", "Open findings.", registry=snapshot).set(findings or 0)
    return generate_latest(REGISTRY) + generate_latest(snapshot)
