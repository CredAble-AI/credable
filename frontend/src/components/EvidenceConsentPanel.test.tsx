import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { evidenceConsentProvider } from '../hooks/useEvidenceConsentState'
import type { EvidenceConsentResponse, EvidenceConsentState } from '../types/evidenceConsent'
import EvidenceConsentPanel from './EvidenceConsentPanel'

vi.mock('../hooks/useEvidenceConsentState', () => ({
  evidenceConsentProvider: { get: vi.fn(), grant: vi.fn(), withdraw: vi.fn() },
}))

const consent = (status: EvidenceConsentState['status']): EvidenceConsentState => ({
  evidenceConsentId: 'evc_demo', selectionId: 'evs_demo', evidenceType: 'RECENT_REVENUE', sourceType: 'CUSTOMER_SUBMITTED',
  purposeCode: 'SUPPLEMENTAL_CREDIT_ASSESSMENT', purposeDescription: '기존 평가의 불확실성을 확인하기 위한 보완평가에 사용',
  dataCategories: ['MONTHLY_SALES', 'MONTHLY_DEPOSITS'], periodStart: '2026-03-01', periodEnd: '2026-08-31', required: true,
  status, grantedAt: status === 'PENDING' ? null : '2026-09-06T01:00:00+09:00', withdrawnAt: status === 'WITHDRAWN' ? '2026-09-06T02:00:00+09:00' : null, updatedAt: status === 'PENDING' ? null : '2026-09-06T02:00:00+09:00',
  scopeVersion: 'demo-recent-revenue-consent-v1', demoOnly: true,
})
const response = (status: EvidenceConsentState['status']): EvidenceConsentResponse => ({ sessionId: 'ses_demo', selectionId: 'evs_demo', consent: consent(status) })
const renderPanel = (onConsentChanged = vi.fn()) => render(<EvidenceConsentPanel sessionId="ses_demo" selectionId="evs_demo" evidenceType="RECENT_REVENUE" onConsentChanged={onConsentChanged} />)

describe('EvidenceConsentPanel', () => {
  beforeEach(() => {
    vi.mocked(evidenceConsentProvider.get).mockReset().mockResolvedValue(response('PENDING'))
    vi.mocked(evidenceConsentProvider.grant).mockReset().mockResolvedValue(response('GRANTED'))
    vi.mocked(evidenceConsentProvider.withdraw).mockReset().mockResolvedValue(response('WITHDRAWN'))
  })

  it('shows the server scope and grants consent for the current selection', async () => {
    const onConsentChanged = vi.fn()
    renderPanel(onConsentChanged)

    expect(await screen.findByText('기존 평가의 불확실성을 확인하기 위한 보완평가에 사용')).toBeInTheDocument()
    expect(screen.getByText('MONTHLY_SALES · MONTHLY_DEPOSITS')).toBeInTheDocument()
    expect(screen.getByText('2026-03-01 ~ 2026-08-31')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '이 범위에 동의' }))

    await waitFor(() => expect(evidenceConsentProvider.grant).toHaveBeenCalledWith('ses_demo', 'evs_demo', expect.any(AbortSignal)))
    expect(await screen.findByText('동의함')).toBeInTheDocument()
    expect(onConsentChanged).toHaveBeenCalledOnce()
  })

  it('withdraws an existing selection-scoped consent', async () => {
    vi.mocked(evidenceConsentProvider.get).mockResolvedValue(response('GRANTED'))
    const onConsentChanged = vi.fn()
    renderPanel(onConsentChanged)

    fireEvent.click(await screen.findByRole('button', { name: '이 동의 철회' }))

    await waitFor(() => expect(evidenceConsentProvider.withdraw).toHaveBeenCalledWith('ses_demo', 'evs_demo', expect.any(AbortSignal)))
    expect(await screen.findByText('동의 철회됨')).toBeInTheDocument()
    expect(onConsentChanged).toHaveBeenCalledOnce()
  })

  it('rejects a response for a different Evidence context', async () => {
    vi.mocked(evidenceConsentProvider.get).mockResolvedValue({ ...response('PENDING'), selectionId: 'evs_other' })
    renderPanel()

    expect(await screen.findByRole('alert')).toHaveTextContent('현재 선택한 증빙과 일치하는 동의 상태를 확인할 수 없습니다.')
  })
})
