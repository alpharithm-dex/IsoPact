import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import data from '../public/data/stage11-data.json'
import { App } from './App'

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('judge interface', () => {
  it('loads graph-first verified replay with backend chronicle', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => data }))
    render(<App />)
    expect(await screen.findByLabelText('Live Outcome Pact Graph')).toBeInTheDocument()
    expect(screen.getByText('What happened, and why')).toBeInTheDocument()
    expect(screen.getByText('Backend-derived')).toBeInTheDocument()
  })

  it('shows loading state without inferring settlement', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})))
    render(<App />)
    expect(screen.getByText('Reading authoritative Pact Graph…')).toBeInTheDocument()
    expect(screen.getByText('No settlement state is inferred while loading.')).toBeInTheDocument()
  })

  it('does not silently fall back after a live backend error', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => data }).mockResolvedValueOnce({ ok: false, status: 503 })
    vi.stubGlobal('fetch', fetchMock); render(<App />)
    await screen.findByLabelText('Live Outcome Pact Graph')
    fireEvent.click(screen.getAllByRole('button', { name: 'LIVE MODE' }).at(-1)!)
    expect(await screen.findByText('Live mode unavailable')).toBeInTheDocument()
    expect(screen.getByText(/never silently substitutes/)).toBeInTheDocument()
  })

  it('opens receipt proof and tamper result', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => data }))
    render(<App />); await screen.findByLabelText('Live Outcome Pact Graph')
    fireEvent.click(screen.getAllByRole('button', { name: 'SETTLEMENT RECEIPT' }).at(-1)!)
    expect(screen.getByRole('dialog')).toHaveTextContent('VERIFIED')
    fireEvent.click(screen.getByRole('button', { name: 'TAMPER TEST' }))
    await waitFor(() => expect(screen.getByRole('dialog')).toHaveTextContent('INVALID'))
    expect(screen.getByRole('dialog')).toHaveTextContent('SIGNATURE_INVALID')
  })
})
