from __future__ import annotations

import json
import os
import re
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any, Iterator


class _LinkAuditSpanProcessor:
    """Proof-only, fail-open record of SDK span links before backend translation."""

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        return None

    def on_end(self, span: Any) -> None:
        if span.name not in {"isopact.agent.invoke", "isopact.evidence.ingest"}:
            return
        try:
            context = span.context
            links = [
                {
                    "trace_id": f"{link.context.trace_id:032x}",
                    "span_id": f"{link.context.span_id:016x}",
                    "attributes": safe_attributes(dict(link.attributes or {})),
                }
                for link in span.links
            ]
            print(json.dumps({
                "severity": "INFO",
                "message": "opentelemetry span-link audit",
                "timestamp": datetime.now(UTC).isoformat(),
                "isopact.span.name": span.name,
                "isopact.span.trace_id": f"{context.trace_id:032x}",
                "isopact.span.span_id": f"{context.span_id:016x}",
                "isopact.span.parent_span_id": (
                    f"{span.parent.span_id:016x}" if span.parent else None
                ),
                "isopact.span.links": links,
                "isopact.pact_id": str((span.attributes or {}).get("isopact.pact_id", "")),
            }, sort_keys=True), flush=True)
        except Exception:
            return

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True

SPAN_NAMES = frozenset({
    "isopact.agent.invoke", "isopact.gateway.request", "isopact.gateway.authenticate",
    "isopact.gateway.authorize", "isopact.reservation.transaction", "isopact.external.refund",
    "isopact.external.replacement", "isopact.external.goodwill", "isopact.evidence.ingest",
    "isopact.evidence.reduce", "isopact.invariants.evaluate", "isopact.resolver.reason",
    "isopact.resolution.validate", "isopact.compensation.precondition",
    "isopact.compensation.execute", "isopact.claim.append", "isopact.kms.checkpoint.sign",
    "isopact.kms.receipt.sign", "isopact.settlement.evaluate",
    "isopact.receipt.verify",
})
FORBIDDEN = re.compile(r"authorization|bearer |jwt|webhook.?signature|private.?key|payment.?instrument|raw.?prompt|customer.?message", re.I)
METRIC_LABELS = frozenset({"decision_type", "reason_code", "agent_role", "tool_category", "pact_lifecycle", "rule_id", "evidence_rank", "compensation_result"})
UNBOUNDED = re.compile(r"^(pact_id|trace_id|span_id|operation_identity|receipt_id|customer_id|order_id|session_id|request_id|evidence_id)$", re.I)


def safe_attributes(values: dict[str, Any]) -> dict[str, str | int | float | bool]:
    result: dict[str, str | int | float | bool] = {}
    for key, value in values.items():
        if value is None or FORBIDDEN.search(key) or FORBIDDEN.search(str(value)):
            continue
        if isinstance(value, (str, int, float, bool)):
            result[key] = value if not isinstance(value, str) else value[:512]
    return result


def metric_attributes(values: dict[str, Any]) -> dict[str, str]:
    for key in values:
        if key not in METRIC_LABELS or UNBOUNDED.search(key):
            raise ValueError(f"unbounded or unsupported metric label: {key}")
    return {key: str(value)[:80] for key, value in values.items()}


class Telemetry:
    """Optional SDK facade. Every exporter/configuration error degrades to no-op."""

    def __init__(self) -> None:
        self.enabled = os.getenv("ISOPACT_TELEMETRY_ENABLED", "true").lower() == "true"
        self.project = os.getenv("GOOGLE_CLOUD_PROJECT", os.getenv("ISOPACT_PROJECT", ""))
        self._tracer = self._meter = None
        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        if self.enabled:
            self._configure()

    def _configure(self) -> None:
        try:
            from opentelemetry import metrics, trace
            # Agent Runtime installs and exports through its own managed OTel
            # provider. Reuse that provider instead of requiring or replacing it
            # with IsoPact's Cloud Run sidecar exporter configuration.
            if os.getenv("GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", "").lower() == "true":
                self._tracer = trace.get_tracer("isopact", "10.0")
                self._meter = metrics.get_meter("isopact", "10.0")
                return
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
            resource = Resource.create({"service.name": os.getenv("K_SERVICE", "isopact"), "cloud.region": os.getenv("ISOPACT_REGION", "unknown")})
            tp = TracerProvider(resource=resource)
            tp.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(), schedule_delay_millis=5000))
            if os.getenv("ISOPACT_SPAN_LINK_AUDIT", "").lower() == "true":
                tp.add_span_processor(_LinkAuditSpanProcessor())
            trace.set_tracer_provider(tp)
            endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
            reader = PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=endpoint), export_interval_millis=15000)
            metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[reader]))
            self._tracer = trace.get_tracer("isopact", "10.0")
            self._meter = metrics.get_meter("isopact", "10.0")
        except Exception as exc:
            self.enabled = False
            self.log("WARNING", "telemetry initialization failed; enforcement remains active", error_type=type(exc).__name__)

    @contextmanager
    def span(self, name: str, *, links: tuple[Any, ...] = (), **attributes: Any) -> Iterator[Any]:
        if name not in SPAN_NAMES:
            raise ValueError(f"unstable span name: {name}")
        if self._tracer is None:
            yield None
            return
        try:
            scope = self._tracer.start_as_current_span(
                name,
                attributes=safe_attributes(attributes),
                links=links,
            )
        except Exception:
            yield None
            return
        # Never catch exceptions raised by business code across this yield. Doing
        # so would convert an enforcement result into a telemetry failure.
        with scope as span:
            yield span

    def inject(self, headers: dict[str, str]) -> None:
        try:
            from opentelemetry.propagate import inject
            inject(headers)
        except Exception:
            return

    @contextmanager
    def remote_context(self, carrier: dict[str, str]) -> Iterator[None]:
        """Attach valid inbound W3C context for the duration of a request."""
        token = None
        try:
            from opentelemetry.context import attach
            from opentelemetry.propagate import extract

            token = attach(extract(carrier))
        except Exception:
            token = None
        try:
            yield
        finally:
            if token is not None:
                try:
                    from opentelemetry.context import detach

                    detach(token)
                except Exception:
                    pass

    def causal_link(self, carrier: dict[str, str], **attributes: Any) -> Any | None:
        """Build a link to an upstream context without making it a parent."""
        try:
            from opentelemetry import trace
            from opentelemetry.propagate import extract

            context = extract(carrier)
            span_context = trace.get_current_span(context).get_span_context()
            if span_context.is_valid:
                return trace.Link(span_context, attributes=safe_attributes(attributes))
        except Exception:
            pass
        return None

    def add(self, name: str, value: int = 1, **labels: Any) -> None:
        attrs = metric_attributes(labels)
        try:
            if self._meter is not None:
                self._counters.setdefault(name, self._meter.create_counter(name)).add(value, attrs)
        except Exception:
            return

    def observe(self, name: str, value: float, **labels: Any) -> None:
        attrs = metric_attributes(labels)
        try:
            if self._meter is not None:
                self._histograms.setdefault(name, self._meter.create_histogram(name, unit="ms")).record(value, attrs)
        except Exception:
            return

    def context_ids(self) -> tuple[str | None, str | None]:
        try:
            from opentelemetry import trace
            ctx = trace.get_current_span().get_span_context()
            if ctx.is_valid:
                return f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}"
        except Exception:
            pass
        return None, None

    def log(self, severity: str, message: str, **fields: Any) -> None:
        trace_id, span_id = self.context_ids()
        payload: dict[str, Any] = {"severity": severity, "message": message, "timestamp": datetime.now(UTC).isoformat(), **safe_attributes(fields)}
        if trace_id and self.project:
            payload["logging.googleapis.com/trace"] = f"projects/{self.project}/traces/{trace_id}"
            payload["logging.googleapis.com/spanId"] = span_id
            payload["logging.googleapis.com/trace_sampled"] = True
        try:
            print(
                json.dumps(payload, sort_keys=True),
                file=sys.stderr if severity == "ERROR" else sys.stdout,
                flush=True,
            )
        except Exception:
            # A broken stdout/stderr sink is telemetry loss, never a business
            # authorization or settlement failure.
            return

    def flush(self, timeout_millis: int = 10000) -> None:
        """Best-effort export flush for finite jobs; never affects business semantics."""
        for provider in (getattr(self._tracer, "_tracer_provider", None), getattr(self._meter, "_meter_provider", None)):
            try:
                if provider is not None and hasattr(provider, "force_flush"):
                    provider.force_flush(timeout_millis=timeout_millis)
            except Exception:
                continue


telemetry = Telemetry()
