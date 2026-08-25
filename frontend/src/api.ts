import type { Stage11Data } from './types'

export async function loadStage11Data(mode: 'LIVE' | 'VERIFIED REPLAY', signal?: AbortSignal): Promise<Stage11Data> {
  const url = mode === 'LIVE' ? '/v1/demo/stage11' : '/data/stage11-data.json'
  const response = await fetch(url, { signal, headers: { Accept: 'application/json' } })
  if (!response.ok) throw new Error(`${mode === 'LIVE' ? 'Live settlement plane' : 'Verified replay'} unavailable (${response.status})`)
  return response.json()
}

export async function verifyReceipt(tampered = false): Promise<Record<string, unknown>> {
  const response = await fetch('/v1/demo/stage11/receipts/verify', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ proof: tampered ? 'TAMPERED_ARTIFACT' : 'LIVE' })
  })
  if (!response.ok) throw new Error(`Verifier unavailable (${response.status})`)
  return response.json()
}
