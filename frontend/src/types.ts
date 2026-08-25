export type Tone = 'neutral' | 'active' | 'pending' | 'allowed' | 'blocked' | 'conflict' | 'verified' | 'settled'

export interface GraphNode { id: string; label: string; kind: string; x: number; y: number; state: string; tone: Tone; detail?: string }
export interface GraphEdge { id: string; from: string; to: string; label: string; tone: Tone; dashed?: boolean }
export interface EconomicLine { label: string; value: string; tone?: Tone; note?: string }
export interface ChronicleEntry {
  entry_id: string; logical_time?: string; actor?: string; category: string; summary: string;
  gateway_decision?: string; reason_code?: string; evidence_rank?: number; trace_id?: string;
  operation_identity?: string; evidence_id?: string; rule?: string; sequence?: number; claim_hash?: string;
  caused_by?: string[]; confirmed_by?: string[]; blocked_by?: string[]; reconciled_by?: string[]
}
export interface DemoStep {
  id: string; title: string; eyebrow: string; lifecycle: string; businessOutcome: string;
  receiptState: string; callout?: { actor: string; verdict: string; reason: string; detail: string; tone: Tone };
  nodes: GraphNode[]; edges: GraphEdge[]; economics: EconomicLine[]; chronicleThrough: number;
}
export interface Scenario {
  id: string; label: string; shortLabel: string; evidenceMode: 'LIVE' | 'VERIFIED REPLAY';
  pactId: string; caseLabel: string; orderId: string; scheduleDigest?: string;
  sourceArtifacts: string[]; steps: DemoStep[]; chronicle: ChronicleEntry[];
}
export interface ReceiptBundle {
  receipt: Record<string, unknown>; verification: Verification; tamperedVerification: Verification
}
export interface Verification {
  receipt_signature_valid: boolean; checkpoint_signature_valid: boolean; claim_chain_valid: boolean;
  terminal_hash_matches: boolean; overall_integrity_valid: boolean; reason_codes: string[]
}
export interface Stage11Data {
  schemaVersion: string; generatedAt: string; authoritativeSources: string[]; scenarios: Scenario[];
  receiptBundle: ReceiptBundle; observability: Record<string, unknown>; architecture: Record<string, string>
}
