# ADR-029: Trace context and links

Accepted. Remote tools inject W3C Trace Context when ADK exposes an active context. The Gateway starts/extracts a trace through standard instrumentation. Async work must use extracted context or a span link to the originating context; it must not fabricate parentage. Stable IsoPact causal IDs provide cross-trace correlation and remain distinct from trace IDs.
