# ADR-028: OpenTelemetry telemetry pipeline

Accepted. Cloud Run emits OTLP to a Google-built Collector sidecar, which batches to the Google Cloud Telemetry API. SDK and exporter initialization failures become no-ops. No synchronous exporter is admitted to consequential-write paths.
