from __future__ import annotations

import json

import pytest
from opentelemetry.propagate import inject
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from isopact.observability.chronicle import build_case_chronicle
from isopact.observability.telemetry import SPAN_NAMES, Telemetry, metric_attributes, safe_attributes


def test_span_taxonomy_and_secret_filtering():
    assert "isopact.gateway.authorize" in SPAN_NAMES
    result = safe_attributes({"isopact.pact_id": "PACT-1", "authorization_header": "Bearer secret", "note": "ok"})
    assert result == {"isopact.pact_id": "PACT-1", "note": "ok"}
    assert "Bearer" not in json.dumps(result)


def test_metric_cardinality_contract():
    assert metric_attributes({"decision_type": "ALLOW", "agent_role": "SUPPORT"})
    with pytest.raises(ValueError):
        metric_attributes({"pact_id": "PACT-1"})


def test_business_exception_is_never_converted_by_telemetry():
    instance = Telemetry.__new__(Telemetry)
    instance._tracer = None
    with pytest.raises(PermissionError, match="denied"):
        with instance.span("isopact.gateway.authenticate"):
            raise PermissionError("denied")


def test_logging_sink_failure_is_fail_open(monkeypatch):
    instance = Telemetry.__new__(Telemetry)
    instance.project = "test-project"
    instance.context_ids = lambda: (None, None)

    def broken_print(*args, **kwargs):
        raise BrokenPipeError("logging sink unavailable")

    monkeypatch.setattr("builtins.print", broken_print)
    instance.log("INFO", "business path remains available")


def test_w3c_remote_context_is_preserved_and_async_context_is_linked():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    tracer = provider.get_tracer("test")
    instance = Telemetry.__new__(Telemetry)
    instance._tracer = tracer

    carrier: dict[str, str] = {}
    with tracer.start_as_current_span("runtime.tool") as upstream:
        upstream_context = upstream.get_span_context()
        inject(carrier)

    with instance.remote_context(carrier):
        with instance.span("isopact.gateway.request"):
            pass

    link = instance.causal_link(carrier, **{"isopact.source_event_id": "evt-1"})
    assert link is not None
    with instance.span("isopact.evidence.ingest", links=(link,)):
        pass

    spans = {span.name: span for span in exporter.get_finished_spans()}
    assert spans["isopact.gateway.request"].context.trace_id == upstream_context.trace_id
    assert spans["isopact.gateway.request"].parent.span_id == upstream_context.span_id
    assert spans["isopact.evidence.ingest"].parent is None
    assert spans["isopact.evidence.ingest"].links[0].context.span_id == upstream_context.span_id


def test_normalized_mixed_case_http_trace_header_is_preserved():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    instance = Telemetry.__new__(Telemetry)
    instance._tracer = provider.get_tracer("test-mixed-case")
    carrier = {
        key.lower(): value
        for key, value in {
            "Traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
        }.items()
    }
    with instance.remote_context(carrier):
        with instance.span("isopact.gateway.request"):
            pass
    span = exporter.get_finished_spans()[0]
    assert f"{span.context.trace_id:032x}" == "0af7651916cd43dd8448eb211c80319c"
    assert f"{span.parent.span_id:016x}" == "b7ad6b7169203331"


def test_chronicle_is_ordered_and_causal_without_mutating_source():
    claims = [
        {"claim_id": "c2", "pact_id": "p", "occurred_at": "2026-01-02T00:00:00Z", "sequence_number": 2, "evidence_rank": 1, "references": ["event_1"], "claim_hash": "b"},
        {"claim_id": "c1", "pact_id": "p", "occurred_at": "2026-01-01T00:00:00Z", "sequence_number": 1, "evidence_rank": 4, "references": ["intent_1"], "normalized_payload": {"authorization_result": "ALLOW", "reason_code": "AUTHORITY_RESERVED"}, "claim_hash": "a"},
    ]
    result = build_case_chronicle({"pact_id": "p", "graph_state": "SETTLED"}, {"claims": claims})
    assert [entry["entry_id"] for entry in result["entries"]] == ["c1", "c2"]
    assert result["entries"][1]["confirmed_by"] == ["event_1"]
    assert result["current_lifecycle"] == "SETTLED"
    assert claims[0]["claim_id"] == "c2"
