import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import data from '../public/data/stage11-data.json'
import { App } from './App'

afterEach(() => { cleanup(); vi.restoreAllMocks() })
const load = () => { vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => data })); render(<App />) }

describe('productized enterprise interface', () => {
  it('opens on a work-focused case workspace rather than a graph', async () => {
    load()
    expect(await screen.findByText('Missing order')).toBeInTheDocument()
    expect(screen.getByText('CURRENT RESOLUTION')).toBeInTheDocument()
    expect(screen.getByText('Waiting on Stripe')).toBeInTheDocument()
    expect(screen.queryByLabelText('Case Map')).not.toBeInTheDocument()
    expect(screen.queryByText(/Step 7 of 10/)).not.toBeInTheDocument()
  })

  it('explains the pending customer outcome without introducing settlement logic', async () => {
    load(); await screen.findByRole('heading', { name: 'Authorized response' })
    expect(screen.getAllByText('Waiting for confirmation').length).toBeGreaterThan(0)
    expect(screen.getByText('Support issued a refund and Retention granted $50 goodwill. IsoPact stopped a replacement and a duplicate refund. The case will resolve when Stripe confirms the refund.')).toBeInTheDocument()
    expect(screen.getByText('Processing at Stripe')).toBeInTheDocument()
    expect(screen.getByText('Another primary resolution is already underway')).toBeInTheDocument()
  })

  it('keeps the graph as a secondary Case Map view', async () => {
    load(); await screen.findByRole('heading', { name: 'Authorized response' })
    fireEvent.click(screen.getByRole('tab', { name: 'Case Map' }))
    expect(await screen.findByLabelText('Case Map')).toBeInTheDocument()
    expect(screen.getByText('How this outcome was reached')).toBeInTheDocument()
    expect(screen.getByText('Accepted, not yet confirmed')).toBeInTheDocument()
  })

  it('provides a case queue while distinguishing UI fixtures from canonical data', async () => {
    load(); await screen.findByRole('heading', { name: 'Authorized response' })
    fireEvent.click(screen.getAllByRole('button', { name: 'Cases' }).at(-1)!)
    expect(await screen.findByText('Customer outcome queue')).toBeInTheDocument()
    expect(screen.getByText('ORD-8519')).toBeInTheDocument()
    expect(screen.getByText('LIVE CASE')).toBeInTheDocument()
    expect(screen.getAllByText('VERIFIED FIXTURE').length).toBeGreaterThan(0)
    expect(screen.getByText(/canonical evidence for ORD-8472/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /ORD-8472/ }))
    expect(await screen.findByRole('heading', { name: 'Authorized response' })).toBeInTheDocument()
  })

  it('keeps synthetic workspaces visibly non-authoritative', async () => {
    load(); await screen.findByRole('heading', { name: 'Authorized response' })
    fireEvent.click(screen.getByRole('button', { name: /Northstar Commerce/ }))
    fireEvent.click(screen.getByRole('menuitem', { name: /Acme Retail/ }))
    expect(await screen.findByText('SYNTHETIC WORKSPACE')).toBeInTheDocument()
    expect(screen.getByText(/No tenant isolation, customer records/)).toBeInTheDocument()
    expect(screen.queryByText('ORD-8472')).not.toBeInTheDocument()
  })

  it('supports queue search and explicit integration states', async () => {
    load(); await screen.findByRole('heading', { name: 'Authorized response' })
    fireEvent.click(screen.getAllByRole('button', { name: 'Cases' }).at(-1)!)
    fireEvent.change(screen.getByPlaceholderText('Case, customer, or issue'), { target: { value: '8519' } })
    expect(screen.getByText('ORD-8519')).toBeInTheDocument()
    expect(screen.queryByText('ORD-8433')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Integrations/ }))
    expect(await screen.findByRole('heading', { name: 'Enterprise systems' })).toBeInTheDocument()
    expect(screen.getByText(/Connected adapter/)).toBeInTheDocument()
    expect(screen.getAllByText(/Demo adapter/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Not connected/)).toBeInTheDocument()
  })

  it('keeps technical evidence and receipt proof accessible', async () => {
    load(); await screen.findByRole('heading', { name: 'Authorized response' })
    fireEvent.click(screen.getByRole('tab', { name: 'Evidence' }))
    expect(await screen.findByText('What supports this case state')).toBeInTheDocument()
    expect(screen.getAllByText('View details').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: 'Verification' }))
    expect(await screen.findByRole('dialog')).toHaveTextContent('Cryptographic outcome proof')
    expect(screen.getByRole('dialog')).toHaveTextContent('VERIFIED')
  })

  it('exposes agents, policies, and system proof as enterprise surfaces', async () => {
    load(); await screen.findByRole('heading', { name: 'Authorized response' })
    fireEvent.click(screen.getByRole('button', { name: /Agents/ }))
    expect(await screen.findByText('Enterprise fleet')).toBeInTheDocument()
    expect(screen.getAllByText(/Managed identity/).length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('button', { name: /Policies/ }))
    expect(await screen.findByText('Trusted resolution policy')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /System/ }))
    expect(await screen.findByText('Operational infrastructure')).toBeInTheDocument()
    expect(screen.getByText('Google Agent Runtime')).toBeInTheDocument()
  })

  it('moves scenarios and replay controls into Demo Lab', async () => {
    load(); await screen.findByRole('heading', { name: 'Authorized response' })
    fireEvent.click(screen.getByRole('button', { name: /Demo Lab/ }))
    expect(await screen.findByText('Scenario comparison')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Without IsoPact' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Without IsoPact' }))
    expect(screen.getByText('Step 1 of 2')).toBeInTheDocument()
    expect(screen.getByLabelText('Case Map')).toBeInTheDocument()
  })

  it('does not silently fall back after a live data error', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => data }).mockResolvedValueOnce({ ok: false, status: 503 })
    vi.stubGlobal('fetch', fetchMock); render(<App />); await screen.findByRole('heading', { name: 'Authorized response' })
    fireEvent.click(screen.getByRole('button', { name: /Demo Lab/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Live' }))
    expect(await screen.findByText('Live view is unavailable')).toBeInTheDocument()
    expect(screen.getByText(/never silently substitutes/)).toBeInTheDocument()
  })
})
