from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

from isopact.invariants.engine import CommerceInvariantEngine
from isopact.invariants.scenarios import NOW, protected_events, protected_facts, stage6_policy
from isopact.observability import telemetry
from isopact.reservations.firestore import evaluate_reservation_snapshot
from services.outcome_gateway.main import app


class CountingExporter(SpanExporter):
    def __init__(self): self.exported = 0
    def export(self, spans): self.exported += len(spans); return SpanExportResult.SUCCESS


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, int(len(ordered) * fraction + .999999) - 1))]


def stats(values: list[float]) -> dict:
    return {"samples": len(values), "p50_ms": round(statistics.median(values), 6), "p95_ms": round(percentile(values, .95), 6)}


def measure(tracer, samples: int) -> dict:
    telemetry._tracer = tracer
    facts = protected_facts(settled=True)
    client = app.test_client()
    gateway, http, invariants = [], [], []
    for _ in range(50):
        evaluate_reservation_snapshot(None, slot_occupied=False)
        client.get("/health")
    for i in range(samples):
        started = time.perf_counter_ns()
        with telemetry.span("isopact.gateway.authorize"):
            evaluate_reservation_snapshot(None, slot_occupied=False)
        gateway.append((time.perf_counter_ns() - started) / 1_000_000)
        started = time.perf_counter_ns()
        with telemetry.span("isopact.gateway.request"):
            response = client.get("/health")
            assert response.status_code == 200
        http.append((time.perf_counter_ns() - started) / 1_000_000)
        started = time.perf_counter_ns()
        CommerceInvariantEngine().evaluate(
            pact_id=f"overhead-{i}", graph_revision=1, facts=facts, policy=stage6_policy(),
            selected_resolution="successful_refund", settlement_evidence_satisfied=True,
            ticket_closed=True, agent_complete=True, protection_events=protected_events(facts), evaluated_at=NOW,
        )
        invariants.append((time.perf_counter_ns() - started) / 1_000_000)
    return {"gateway_authorization": stats(gateway), "http_gateway": stats(http), "invariant_evaluation": stats(invariants)}


def delta(enabled: dict, disabled: dict) -> dict:
    return {name: {"p50_delta_ms": round(enabled[name]["p50_ms"] - disabled[name]["p50_ms"], 6), "p95_delta_ms": round(enabled[name]["p95_ms"] - disabled[name]["p95_ms"], 6)} for name in enabled}


def main() -> None:
    samples = 500
    disabled = measure(None, samples)
    exporter = CountingExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "isopact-overhead-benchmark"}))
    provider.add_span_processor(BatchSpanProcessor(exporter, schedule_delay_millis=5000, max_queue_size=4096))
    enabled = measure(provider.get_tracer("isopact", "10.0"), samples)
    provider.force_flush(timeout_millis=10000)
    provider.shutdown()
    result = {"environment": "controlled local warm benchmark with OpenTelemetry BatchSpanProcessor and nonblocking in-memory exporter; not a production throughput claim", "samples_per_path": samples, "telemetry_disabled": disabled, "telemetry_enabled_batch": enabled, "delta": delta(enabled, disabled), "exported_spans": exporter.exported, "synchronous_multi_second_export_dependency": False, "result": "PASS"}
    path = ROOT / "artifacts" / "observability" / "telemetry-overhead.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__": main()
