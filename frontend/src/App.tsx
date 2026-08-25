import { useEffect, useMemo, useReducer, useState } from 'react'
import { loadStage11Data } from './api'
import { assertAuthoritativeScenario, currentStep, initialReplay, replayReducer } from './model'
import type { ChronicleEntry, DemoStep, GraphEdge, GraphNode, ReceiptBundle, Scenario, Stage11Data, Tone } from './types'
import './brand.css'

const toneIcon: Record<Tone, string> = { neutral: '○', active: '▶', pending: '◷', allowed: '✓', blocked: '×', conflict: '!', verified: '◆', settled: '✓' }

function BrandIcon({ brand }: { brand: 'jira' | 'slack' | 'salesforce' | 'stripe' }) {
  if (brand === 'jira') return <svg viewBox="0 0 24 24" role="img" aria-label="Jira"><path fill="#2684ff" d="M11.571 11.513H0a5.218 5.218 0 0 0 5.232 5.215h2.13v2.057A5.215 5.215 0 0 0 12.575 24V12.518a1.005 1.005 0 0 0-1.005-1.005zm5.723-5.756H5.736a5.215 5.215 0 0 0 5.215 5.214h2.129v2.058a5.218 5.218 0 0 0 5.215 5.214V6.758a1.001 1.001 0 0 0-1.001-1.001zM23.013 0H11.455a5.215 5.215 0 0 0 5.215 5.215h2.129v2.057A5.215 5.215 0 0 0 24 12.483V1.005A1.001 1.001 0 0 0 23.013 0Z"/></svg>
  if (brand === 'stripe') return <svg viewBox="0 0 24 24" role="img" aria-label="Stripe"><path fill="#635bff" d="M13.98 10.21c0-.78.64-1.08 1.68-1.08 1.5 0 3.39.45 4.89 1.25V5.75a13 13 0 0 0-4.89-.9c-4 0-6.66 2.09-6.66 5.58 0 5.44 7.49 4.57 7.49 6.92 0 .91-.79 1.2-1.9 1.2-1.65 0-3.75-.68-5.42-1.6v4.69c1.85.8 3.72 1.13 5.42 1.13 4.1 0 6.92-2.03 6.92-5.56-.02-5.87-7.53-4.83-7.53-7zM3 3.96l4.84-1.04v19.52L3 23.48z"/></svg>
  if (brand === 'salesforce') return <svg viewBox="0 0 64 64" role="img" aria-label="Salesforce"><path fill="#00a1e0" d="M26.62 14.49c2.07-2.14 4.95-3.5 8.13-3.5 4.24 0 7.91 2.36 9.88 5.86a13.6 13.6 0 0 1 5.6-1.18c7.63 0 13.8 6.23 13.8 13.91S57.82 43.5 50.2 43.5c-.93 0-1.83-.09-2.71-.27a10.1 10.1 0 0 1-8.82 5.17c-1.58 0-3.08-.37-4.41-1a11.5 11.5 0 0 1-10.59 7.02 11.5 11.5 0 0 1-10.8-7.54c-.71.15-1.44.22-2.19.22C4.78 47.1 0 42.27 0 36.29a10.82 10.82 0 0 1 5.34-9.36 12.2 12.2 0 0 1-1.03-4.95c-.03-6.82 5.56-12.39 12.41-12.39 3.98 0 7.56 1.92 9.9 4.9"/></svg>
  return <svg viewBox="0 0 64 64" role="img" aria-label="Slack"><path fill="#e01e5a" d="M17.78 40.31c0-3.73 2.82-6.73 6.32-6.73s6.32 3 6.32 6.73v16.57c0 3.73-2.82 6.73-6.32 6.73s-6.32-3-6.32-6.73z"/><path fill="#ecb22d" d="M40.31 46.22c-3.73 0-6.73-2.82-6.73-6.32s3-6.32 6.73-6.32h16.57c3.73 0 6.73 2.82 6.73 6.32s-3 6.32-6.73 6.32z"/><path fill="#2fb67c" d="M33.58 7.12c0-3.73 2.82-6.73 6.32-6.73s6.32 3 6.32 6.73v16.57c0 3.73-2.82 6.73-6.32 6.73s-6.32-3-6.32-6.73z"/><path fill="#36c5f1" d="M7.12 30.42c-3.73 0-6.73-2.82-6.73-6.32s3-6.32 6.73-6.32h16.57c3.73 0 6.73 2.82 6.73 6.32s-3 6.32-6.73 6.32z"/><path fill="#ecb22d" d="M33.58 57.67a6.31 6.31 0 0 0 6.32 6.32c3.5 0 6.32-2.82 6.32-6.32v-6.32H39.9a6.31 6.31 0 0 0-6.32 6.32z"/><path fill="#2fb67c" d="M57.67 30.42h-6.32V24.1c0-3.5 2.82-6.32 6.32-6.32s6.32 2.82 6.32 6.32-2.82 6.32-6.32 6.32z"/><path fill="#e01e5a" d="M6.71 33.58h6.32v6.32c0 3.5-2.82 6.32-6.32 6.32S.39 43.4.39 39.9s2.82-6.32 6.32-6.32z"/><path fill="#36c5f1" d="M30.42 6.71v6.32H24.1c-3.5 0-6.32-2.82-6.32-6.32S20.6.39 24.1.39s6.32 2.82 6.32 6.32z"/></svg>
}

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
  const brand = node.id === 'jira' ? 'jira' : node.id === 'stripe' ? 'stripe' : node.id === 'crm' ? 'salesforce' : null
  return <article className={`graph-node tone-${node.tone} kind-${node.kind}`} style={{ left: `${node.x}%`, top: `${node.y}%` }} aria-label={`${node.label}: ${node.state}`}>
    <div className={`node-icon${brand ? ' brand-node-icon' : ''}`} aria-hidden="true">{brand ? <BrandIcon brand={brand}/> : toneIcon[node.tone]}</div><div><span className="node-kind">{node.kind}</span><strong>{node.label}</strong><small>{node.state}</small>{node.detail && <em>{node.detail}</em>}</div>
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
  return <div className="drawer-scrim" onMouseDown={e => e.currentTarget === e.target && onClose()}><aside className="drawer proof-drawer" role="dialog" aria-modal="true"><button className="close" onClick={onClose}>×</button><span className="kicker">SYSTEM PROOF</span><h2>Operational evidence</h2><div className="proof-list"><Detail label="Live trace" value={obs.liveTraceId}/><Detail label="Agent resource" value={obs.agentResource}/><Detail label="Gateway latency p95" value={obs.gatewayLatency}/><Detail label="Firestore authorization" value={obs.firestoreLatency}/><Detail label="Evidence processing" value={obs.evidenceStatus}/><Detail label="Invariant engine" value={obs.invariantStatus}/><Detail label="KMS signing" value={obs.kmsStatus}/><Detail label="Receipt verification" value={obs.receiptStatus}/><Detail label="OpenTelemetry" value={obs.otelStatus}/><Detail label="Cloud Trace" value={obs.cloudTraceStatus}/></div><a className="dashboard-link" href={String(obs.dashboardUrl)} target="_blank" rel="noreferrer">Open Google Cloud dashboard ↗</a><div className="architecture"><span>REASONING PLANE · europe-west1</span><strong>Google Agent Runtime · Gemini</strong><i>↓ signed identity</i><span>SETTLEMENT PLANE · africa-south1</span><strong>Outcome Gateway · Firestore · Pub/Sub · KMS</strong><span>ILLUSTRATIVE ENTERPRISE SYSTEMS</span><div className="platform-marks"><span><BrandIcon brand="jira"/>Jira</span><span><BrandIcon brand="slack"/>Slack</span><span><BrandIcon brand="salesforce"/>Salesforce</span></div><small>Examples only · no live integration or endorsement claimed. Third-party marks belong to their owners.</small></div></aside></div>
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
