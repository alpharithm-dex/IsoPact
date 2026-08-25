# Data Model and Interfaces

## Conventions

- IDs are opaque strings with type prefixes; timestamps are UTC RFC 3339.
- Money is `{currency: ISO-4217, minor_units: integer}`; floating-point amounts are forbidden.
- All mutable aggregates carry `revision`, `created_at`, and `updated_at`.
- Enums are closed and unknown input fails validation.
- Stored events and decisions pin `schema_version` and `policy_version`.
- Canonical JSON uses sorted keys, UTF-8, normalized timestamps, and integers for monetary value.

The following TypeScript-like records define language-neutral contracts; implementation uses strict Pydantic models and matching TypeScript types.

```ts
type Money = { currency: "USD"; minor_units: number };
type PactState = "OPEN"|"PENDING"|"AT_RISK"|"VIOLATED"|"ESCALATED"|"SETTLED";
type Decision = "ALLOW"|"BLOCK"|"DEFER"|"REQUIRE_APPROVAL";

interface Pact {
  pact_id: string; schema_version: string; policy_version: string;
  outcome_type: string; subject: Record<string,string>;
  requested_outcome: string; allowed_resolution_paths: string[];
  exclusive_slots: Record<string,string[]>;
  required_evidence: Record<string,EvidenceRequirement[]>;
  financial_limits: Record<string,Money>;
  state: PactState; selected_resolution_path?: string;
  participant_ids: string[]; deadline_at?: string;
  revision: number; created_at: string; updated_at: string;
}

interface Participant {
  participant_id: string; pact_id: string;
  kind: "AGENT"|"HUMAN"|"SYSTEM";
  display_name: string; authenticated_principal: string;
  roles: string[]; allowed_tools: string[];
  authority_limits: Record<string,Money>;
}

interface StateClaim {
  claim_id: string; pact_id: string; sequence: number;
  participant_id: string; system: string; tool: string;
  purpose: string; request_hash: string; response_status: "ACCEPTED"|"PENDING"|"CONFIRMED"|"FAILED"|"REVERSED"|"UNKNOWN";
  operation_key?: string; external_reference?: string;
  evidence_ids: string[]; trace_id: string; occurred_at: string; recorded_at: string;
  previous_claim_hash: string; claim_hash: string;
}

interface EconomicEvent {
  event_id: string; pact_id: string; source_event_id: string;
  kind: "CAPTURE"|"REFUND"|"REPLACEMENT"|"GOODWILL_CREDIT"|"REVERSAL";
  phase: "PROJECTED"|"PENDING"|"SETTLED"|"FAILED"|"REVERSED"|"BLOCKED";
  amount: Money; subject_id: string; operation_key?: string;
  authorized_exception: boolean; evidence_ids: string[]; occurred_at: string;
}

interface Evidence {
  evidence_id: string; pact_id: string; source: string;
  source_event_id: string; type: string;
  rank: 1|2|3|4|5; // 1 is strongest
  authenticity: "VERIFIED"|"UNVERIFIED";
  subject: Record<string,string>; payload_hash: string;
  supports_claim_ids: string[]; occurred_at: string; ingested_at: string;
}

interface EvidenceRequirement {
  evidence_type: string; maximum_rank: 1|2; source_allowlist: string[];
  subject_constraints: Record<string,string>;
}

interface Invariant {
  invariant_id: string; version: string; description: string;
  severity: "INFO"|"WARNING"|"ERROR"|"CRITICAL";
  applicable_event_types: string[]; required_evidence?: EvidenceRequirement[];
  permitted_responses: Decision[];
}

interface InvariantEvaluation {
  evaluation_id: string; pact_id: string; invariant_id: string; invariant_version: string;
  input_revision: number; result: "PASS"|"FAIL"|"UNKNOWN";
  severity: string; explanation: string; evidence_ids: string[];
  recommended_responses: Decision[]; evaluated_at: string;
}

interface Conflict {
  conflict_id: string; pact_id: string; kind: string;
  status: "OPEN"|"PLANNED"|"RESOLVED"|"ESCALATED";
  claim_ids: string[]; economic_event_ids: string[];
  failed_evaluation_ids: string[]; detected_at: string; resolved_at?: string;
}

interface ResolutionPlan {
  plan_id: string; pact_id: string; conflict_id: string;
  proposed_by: string; model_contribution_id?: string;
  steps: ResolutionStep[]; policy_version: string;
  status: "PROPOSED"|"APPROVAL_REQUIRED"|"APPROVED"|"EXECUTING"|"COMPLETED"|"REJECTED"|"STALE";
  created_at: string;
}

interface ResolutionStep {
  ordinal: number; compensation_definition_id: string;
  forward_operation_key: string; parameters: Record<string,unknown>;
  required_approval_id?: string;
}

interface SettlementReceipt {
  receipt_id: string; pact_id: string; pact_revision: number;
  requested_outcome: string; selected_resolution_path: string;
  final_system_states: Record<string,string>; settled_events: string[];
  evidence_ids: string[]; approval_ids: string[]; participant_ids: string[];
  reconciliation_operation_keys: string[]; final_economic_position: EconomicPosition;
  graph_root_hash: string; signing_key_version: string; signature: string;
  settled_at: string;
}

interface OperationReservation {
  reservation_id: string; pact_id: string; operation_key: string;
  slot?: string; semantic_action: string; participant_id: string;
  state: "RESERVED"|"EXECUTING"|"UNCERTAIN"|"CONFIRMED"|"FAILED"|"RELEASED"|"REVERSED";
  request_hash: string; external_reference?: string;
  policy_version: string; lease_expires_at?: string;
  revision: number; created_at: string; updated_at: string;
}

interface CompensationDefinition {
  definition_id: string; version: string; forward_action: string;
  compensation_action: string|null;
  precondition_type: string|null;
  authority: "AUTOMATIC"|"APPROVAL_REQUIRED"|"HUMAN_REVIEW_ONLY";
  allowed_parameter_mapping: Record<string,string>;
  idempotency_scope: string; active: boolean;
}

interface EconomicPosition {
  original: Money; settled: Money; pending: Money; projected: Money;
  authorized_exception: Money; blocked: Money; recovered: Money; protected: Money;
}
```

## Keys, idempotency, and concurrency

`operation_key = SHA-256(canonical_json({pact_id, resolution_path, event_type, subject, normalized_value_or_resource}))`.

Request IDs, agent/session/trace IDs, and policy version are deliberately excluded: retries from different transports and authorization-policy updates retain the same economic identity. The reservation separately pins the policy version that authorized each attempt. A new policy version therefore cannot bypass a live, unknown, or confirmed economic reservation. The exclusive slot key is `pacts/{pact_id}/slots/{slot_name}`; refund and replacement both compete for `primary_compensation`.

The repository operation `reserve(pact_id, operation_key, slots[], expected_pact_revision)` runs as one Firestore transaction. It returns the existing reservation for an identical operation, rejects a conflicting live slot holder, or creates the reservation and slot records atomically. It never holds a transaction open during an external call.

## Persistence layout

```text
pacts/{pact_id}
  participants/{participant_id}
  claims/{claim_id}
  economic_events/{event_id}
  evidence/{evidence_id}
  invariants/{invariant_id_version}
  evaluations/{evaluation_id}
  conflicts/{conflict_id}
  reservations/{operation_key}
  slots/{slot_name}
  plans/{plan_id}
  approvals/{approval_id}
  receipts/{receipt_id}
  inbox_events/{source_source_event_id}
```

The pact document is the transaction anchor and carries aggregate revision/state. High-volume append-only data remains in subcollections. Event ingestion first creates the deterministic inbox key; existing keys make duplicate delivery a no-op. Reducers use event time plus explicit lifecycle precedence, not arrival order alone.

## Repository ports

```python
class PactRepository(Protocol):
    def get_snapshot(self, pact_id: str) -> PactSnapshot: ...
    def reserve_operation(self, command: ReserveOperation) -> ReservationResult: ...
    def transition_reservation(self, command: TransitionReservation) -> OperationReservation: ...
    def append_evidence_once(self, evidence: Evidence) -> AppendResult: ...
    def append_claim(self, claim: StateClaim) -> StateClaim: ...
    def persist_evaluation(self, evaluation: InvariantEvaluation) -> None: ...
    def commit_settlement(self, expected_revision: int, receipt: SettlementReceipt) -> None: ...
```

Both in-memory and Firestore implementations must satisfy the same contract test suite.
