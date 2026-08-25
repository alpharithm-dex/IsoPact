import { useEffect, useMemo, useReducer, useState } from 'react'
import { loadStage11Data } from './api'
import { assertAuthoritativeScenario, currentStep, initialReplay, replayReducer } from './model'
import type { ChronicleEntry, DemoStep, GraphEdge, GraphNode, ReceiptBundle, Scenario, Stage11Data, Tone } from './types'

const toneIcon: Record<Tone, string> = { neutral: '○', active: '▶', pending: '◷', allowed: '✓', blocked: '×', conflict: '!', verified: '◆', settled: '✓' }

function StatusBadge({ tone, children }: { tone: Tone; children: React.ReactNode }) {
  return <span className={`badge tone-${tone}`}><span aria-hidden="true">{toneIcon[tone]}</span>{children}</span>
}

function PactGraph({ step }: { step: DemoStep }) {
  const byId = useMemo(() => Object.fromEntries(step.nodes.map(n => [n.id, n])), [step.nodes])
  return <section className="graph-panel" aria-label="Live Outcome Pact Graph">
    <div className="section-heading"><div><span className="kicker">LIVE OUTCOME PACT GRAPH</span><h2>{step.title}</h2></div><StatusBadge tone={step.lifecycle === 'SETTLED' ? 'settled' : step.lifecycle === 'VIOLATED' ? 'conflict' : 'pending'}>{step.lifecycle}</StatusBadge></div>
    <div className="graph-stage">
      <svg className="graph-lines" viewBox="0 0 1000 620" role="img" aria-label="Causal connections between participating enterprise systems">
        <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8 Z" fill="currentColor" /></marker></defs>
        {step.edges.map(edge => <GraphLine key={edge.id} edge={edge} from={byId[edge.from]} to={byId[edge.to]} />)}
      </svg>
      {step.nodes.map(node => <GraphNodeView key={node.id} node={node} />)}
      <div className="graph-legend">{(['active','pending','allowed','blocked','verified','settled'] as Tone[]).map(t => <StatusBadge key={t} tone={t}>{t}</StatusBadge>)}</div>
    </div>
  </section>
}

function GraphLine({ edge, from, to }: { edge: GraphEdge; from: GraphNode; to: GraphNode }) {
  if (!from || !to) return null
  const x1 = from.x + 7, y1 = from.y + 5, x2 = to.x + 7, y2 = to.y + 5
  const mx = (x1 + x2) / 2
  return <g className={`edge tone-${edge.tone}`}>
    <path d={`M ${x1 * 10} ${y1 * 6.2} C ${mx * 10} ${y1 * 6.2}, ${mx * 10} ${y2 * 6.2}, ${x2 * 10} ${y2 * 6.2}`} markerEnd="url(#arrow)" strokeDasharray={edge.dashed ? '8 7' : undefined} />
    <text x={mx * 10} y={(y1 + y2) * 3.1 - 7}>{edge.label}</text>
  </g>
}

function GraphNodeView({ node }: { node: GraphNode }) {
  return <article className={`graph-node tone-${node.tone} kind-${node.kind}`} style={{ left: `${node.x}%`, top: `${node.y}%` }} aria-label={`${node.label}: ${node.state}`}>
    <div className="node-icon" aria-hidden="true">{toneIcon[node.tone]}</div><div><span className="node-kind">{node.kind}</span><strong>{node.label}</strong><small>{node.state}</small>{node.detail && <em>{node.detail}</em>}</div>
  </article>
}

function EconomicPanel({ step, scenario }: { step: DemoStep; scenario: Scenario }) {
  return <aside className="economics">
    <span className="kicker">OUTCOME / ECONOMIC POSITION</span>
    <h2>{scenario.shortLabel}</h2>
    <p className="promise">Resolve missing order through <strong>one primary resolution path.</strong></p>
    <div className="economic-lines">{step.economics.map(line => <div className="economic-line" key={line.label}><span>{line.label}{line.note && <small>{line.note}</small>}</span><strong className={line.tone ? `text-${line.tone}` : ''}>{line.value}</strong></div>)}</div>
    <div className={`outcome-card ${step.businessOutcome === 'SETTLED' ? 'settled' : ''}`}><span>BUSINESS OUTCOME</span><strong>{step.businessOutcome}</strong><small>{step.businessOutcome === 'NOT SETTLED' ? 'Agent completion does not discharge the obligation.' : 'Authoritative settlement conditions satisfied.'}</small></div>
    {step.callout && <div className={`block-callout tone-${step.callout.tone}`}><span>{step.callout.actor}</span><strong>{step.callout.verdict}</strong><code>{step.callout.reason}</code><p>{step.callout.detail}</p></div>}
  </aside>
}

function Chronicle({ entries }: { entries: ChronicleEntry[] }) {
  return <section className="chronicle"><div className="section-heading"><div><span className="kicker">CAUSAL CHRONICLE</span><h2>What happened, and why</h2></div><span className="source-pill">Backend-derived</span></div>
    <div className="timeline">{entries.map((entry, index) => <details key={entry.entry_id} className="timeline-entry"><summary><time>{entry.logical_time ? new Date(entry.logical_time).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : `Step ${index + 1}`}</time><span className="timeline-dot" /><span><strong>{entry.summary}</strong><small>{entry.actor || entry.category}{entry.gateway_decision ? ` · ${entry.gateway_decision}` : ''}{entry.evidence_rank ? ` · Rank ${entry.evidence_rank}` : ''}</small></span></summary><div className="causal-detail"><Detail label="Trace" value={entry.trace_id}/><Detail label="Operation" value={entry.operation_identity}/><Detail label="Reason" value={entry.reason_code}/><Detail label="Evidence" value={entry.evidence_id}/><Detail label="Rule" value={entry.rule}/><Detail label="StateClaim" value={entry.sequence ? `#${entry.sequence} · ${entry.claim_hash?.slice(0,16)}…` : undefined}/><Detail label="Caused by" value={entry.caused_by?.join(', ')}/><Detail label="Confirmed by" value={entry.confirmed_by?.join(', ')}/></div></details>)}</div>
  </section>
}

function Detail({ label, value }: { label: string; value?: string }) { return value ? <div><span>{label}</span><code>{value}</code></div> : null }

function ReceiptDrawer({ bundle, open, onClose }: { bundle: ReceiptBundle; open: boolean; onClose: () => void }) {
  const [tampered, setTampered] = useState(false)
  const verification = tampered ? bundle.tamperedVerification : bundle.verification
  const receipt = bundle.receipt as Record<string, any>
  if (!open) return null
  return <div className="drawer-scrim" role="presentation" onMouseDown={e => e.currentTarget === e.target && onClose()}><aside className="drawer" role="dialog" aria-modal="true" aria-labelledby="receipt-title"><button className="close" onClick={onClose} aria-label="Close receipt">×</button><span className="kicker">CRYPTOGRAPHIC OUTCOME PROOF</span><h2 id="receipt-title">Settlement Receipt</h2><div className="receipt-hero"><div className="seal">{verification.overall_integrity_valid ? '✓' : '×'}</div><div><span>INTEGRITY</span><strong>{verification.overall_integrity_valid ? 'VERIFIED' : 'INVALID'}</strong><small>{tampered ? 'Controlled modified receipt artifact' : 'Signed authoritative receipt'}</small></div></div>
    <div className="receipt-grid"><Detail label="Pact ID" value={String(receipt.pact_id || '')}/><Detail label="Outcome" value="Missing order resolved"/><Detail label="Primary resolution" value="Successful refund"/><Detail label="Refund" value="$200"/><Detail label="Goodwill" value="$50"/><Detail label="Final authorized compensation" value="$250"/><Detail label="Replacement" value="Blocked"/><Detail label="Duplicate refund" value="Blocked"/><Detail label="Authoritative evidence" value="stripe.refund.succeeded"/><Detail label="Policy" value={String(receipt.policy_version || '')}/><Detail label="Rule versions" value={(receipt.rule_versions || []).join(', ')}/><Detail label="Checkpoint" value={receipt.final_checkpoint?.checkpoint_id}/><Detail label="KMS key version" value={String(receipt.signing_key_version || '').split('/').at(-1)}/><Detail label="Terminal claim hash" value={receipt.final_checkpoint?.terminal_claim_hash}/></div>
    <div className="verification-checks"><Check label="Receipt signature" valid={verification.receipt_signature_valid}/><Check label="Checkpoint signature" valid={verification.checkpoint_signature_valid}/><Check label="Claim chain" valid={verification.claim_chain_valid}/><Check label="Terminal hash" valid={verification.terminal_hash_matches}/></div>
    {!verification.overall_integrity_valid && <div className="tamper-reason">Reason: {verification.reason_codes.join(', ') || 'signature / integrity mismatch'}</div>}
    <div className="drawer-actions"><button className="primary" onClick={() => setTampered(false)}>VERIFY INTEGRITY</button><button onClick={() => setTampered(true)}>TAMPER TEST</button></div></aside></div>
}

function Check({ label, valid }: { label: string; valid: boolean }) { return <div><span>{label}</span><strong className={valid ? 'text-verified' : 'text-blocked'}>{valid ? 'VALID' : 'INVALID'}</strong></div> }

function ProofDrawer({ data, open, onClose }: { data: Stage11Data; open: boolean; onClose: () => void }) {
  if (!open) return null
  const obs = data.observability as Record<string, any>
  return <div className="drawer-scrim" onMouseDown={e => e.currentTarget === e.target && onClose()}><aside className="drawer proof-drawer" role="dialog" aria-modal="true"><button className="close" onClick={onClose}>×</button><span className="kicker">SYSTEM PROOF</span><h2>Operational evidence</h2><div className="proof-list"><Detail label="Live trace" value={obs.liveTraceId}/><Detail label="Agent resource" value={obs.agentResource}/><Detail label="Gateway latency p95" value={obs.gatewayLatency}/><Detail label="Firestore authorization" value={obs.firestoreLatency}/><Detail label="Evidence processing" value={obs.evidenceStatus}/><Detail label="Invariant engine" value={obs.invariantStatus}/><Detail label="KMS signing" value={obs.kmsStatus}/><Detail label="Receipt verification" value={obs.receiptStatus}/><Detail label="OpenTelemetry" value={obs.otelStatus}/><Detail label="Cloud Trace" value={obs.cloudTraceStatus}/></div><a className="dashboard-link" href={String(obs.dashboardUrl)} target="_blank" rel="noreferrer">Open Google Cloud dashboard ↗</a><div className="architecture"><span>REASONING PLANE · europe-west1</span><strong>Google Agent Runtime · Gemini</strong><i>↓ signed identity</i><span>SETTLEMENT PLANE · africa-south1</span><strong>Outcome Gateway · Firestore · Pub/Sub · KMS</strong></div></aside></div>
}

export function App() {
  const preview = useMemo(() => new URLSearchParams(window.location.search), [])
  const [mode, setMode] = useState<'LIVE' | 'VERIFIED REPLAY'>('VERIFIED REPLAY')
  const [data, setData] = useState<Stage11Data | null>(null)
  const [error, setError] = useState('')
  const [scenarioId, setScenarioId] = useState(preview.get('scenario') || 'protected')
  const [replay, dispatch] = useReducer(replayReducer, { ...initialReplay, index: Math.max(0, Number(preview.get('step') || 0)) })
  const [receiptOpen, setReceiptOpen] = useState(preview.get('receipt') === 'open')
  const [proofOpen, setProofOpen] = useState(false)

  useEffect(() => { const controller = new AbortController(); setData(null); setError(''); loadStage11Data(mode, controller.signal).then(next => { next.scenarios.forEach(assertAuthoritativeScenario); setData(next) }).catch(e => { if (e.name !== 'AbortError') setError(e.message) }); return () => controller.abort() }, [mode])
  const scenario = data?.scenarios.find(item => item.id === scenarioId) || data?.scenarios[0]
  const step = scenario ? currentStep(scenario, replay) : null
  useEffect(() => { if (!replay.playing || !scenario) return; const timer = setTimeout(() => dispatch({ type: 'TICK', max: scenario.steps.length - 1 }), 1500 / replay.speed); return () => clearTimeout(timer) }, [replay, scenario])

  if (error) return <main className="state-page"><span className="brand-mark">I</span><h1>Live mode unavailable</h1><p>{error}</p><p>IsoPact never silently substitutes recorded evidence for a live backend.</p><button className="primary" onClick={() => setMode('VERIFIED REPLAY')}>OPEN VERIFIED REPLAY</button></main>
  if (!data || !scenario || !step) return <main className="state-page"><div className="loader"/><h1>Reading authoritative Pact Graph…</h1><p>No settlement state is inferred while loading.</p></main>
  const visibleEntries = scenario.chronicle.slice(0, step.chronicleThrough)
  return <div className="app-shell">
    <header><div className="brand"><span className="brand-mark">I</span><div><strong>IsoPact</strong><small>A closed ticket is not a settled outcome.</small></div></div><div className="case-title"><span>CASE</span><strong>{scenario.caseLabel}</strong><small>{scenario.pactId}</small></div><div className="header-status"><div><span>PACT STATE</span><strong>{step.lifecycle}</strong></div><span className={`live-indicator ${mode === 'LIVE' ? 'live' : ''}`}>{mode}</span><button onClick={() => setReceiptOpen(true)}><span>RECEIPT</span><strong>{step.receiptState}</strong></button></div></header>
    <nav className="scenario-tabs" aria-label="Demo scenarios">{data.scenarios.map(item => <button key={item.id} className={item.id === scenario.id ? 'active' : ''} onClick={() => { setScenarioId(item.id); dispatch({ type: 'RESET' }) }}><span>{item.label}</span><small>{item.evidenceMode}</small></button>)}</nav>
    <section className="control-strip"><div className="mode-toggle" aria-label="Evidence mode"><button className={mode === 'LIVE' ? 'active' : ''} onClick={() => setMode('LIVE')}>LIVE MODE</button><button className={mode === 'VERIFIED REPLAY' ? 'active' : ''} onClick={() => setMode('VERIFIED REPLAY')}>VERIFIED REPLAY</button></div><div className="same-schedule"><strong>Same request · Same systems · Same objectives · Same schedule</strong><span>Different settlement control</span></div><div className="replay-controls"><button onClick={() => dispatch({type:'RESET'})} aria-label="Reset replay">↺</button><button onClick={() => dispatch({type: replay.playing ? 'PAUSE' : 'PLAY'})} aria-label={replay.playing ? 'Pause replay' : 'Play replay'}>{replay.playing ? 'Ⅱ' : '▶'}</button><button onClick={() => dispatch({type:'STEP',max:scenario.steps.length-1})} aria-label="Step replay">▶|</button><button onClick={() => dispatch({type:'SPEED',speed:replay.speed === 1 ? 2 : 1})}>{replay.speed}×</button><span>{String(replay.index + 1).padStart(2,'0')} / {String(scenario.steps.length).padStart(2,'0')}</span></div></section>
    <main className="workspace"><PactGraph step={step}/><EconomicPanel step={step} scenario={scenario}/><Chronicle entries={visibleEntries}/></main>
    <footer><span>Outcome settlement infrastructure for multi-agent enterprises.</span><div><button onClick={() => setProofOpen(true)}>SYSTEM PROOF</button><button onClick={() => setReceiptOpen(true)}>SETTLEMENT RECEIPT</button></div></footer>
    <ReceiptDrawer bundle={data.receiptBundle} open={receiptOpen} onClose={() => setReceiptOpen(false)}/><ProofDrawer data={data} open={proofOpen} onClose={() => setProofOpen(false)}/>
  </div>
}
