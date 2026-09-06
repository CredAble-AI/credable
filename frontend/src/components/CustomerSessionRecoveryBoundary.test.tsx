import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { sessionProvider, useCustomerSession } from '../hooks/useCustomerSession'
import type { CustomerSession } from '../types/customerSession'
import CustomerSessionRecoveryBoundary from './CustomerSessionRecoveryBoundary'

const session: CustomerSession = {
  sessionId: 'ses_recovered',
  selectedProfileType: 'small-business',
  demoProfile: { demoProfileId: 'small-business', businessBorrowerType: 'SOLE_PROPRIETOR', displayName: '개인사업자', description: '합성 Demo 사례' },
  consents: { required: { customerIdentity: false, accountSummary: false, creditInformation: false }, optional: { submittedDocuments: false, otherInstitutions: false, partnerData: false } },
  demoOnly: true,
  createdAt: '2026-09-06T00:00:00+09:00',
  updatedAt: '2026-09-06T00:00:00+09:00',
}

function SessionProbe() {
  const result = useCustomerSession()
  if (result.loading) return <p>세션 확인 중</p>
  return <h1>{result.session?.sessionId}</h1>
}

describe('CustomerSessionRecoveryBoundary', () => {
  afterEach(() => vi.restoreAllMocks())

  it('keeps the route and retries a recoverable session load', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    vi.spyOn(sessionProvider, 'get')
      .mockRejectedValueOnce({ code: 'SESSION_SERVICE_UNAVAILABLE', message: '세션 서비스를 사용할 수 없습니다.', requestId: 'req_retry', retryable: true })
      .mockResolvedValueOnce(session)

    render(<MemoryRouter initialEntries={['/protected']}><Routes><Route element={<CustomerSessionRecoveryBoundary />}><Route path="/protected" element={<SessionProbe />} /></Route><Route path="/start" element={<h1>새 평가</h1>} /></Routes></MemoryRouter>)

    expect(await screen.findByRole('heading', { name: '진행 중인 세션을 불러오지 못했습니다' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('req_retry')
    expect(screen.getByRole('link', { name: '새 평가 시작' })).toHaveAttribute('href', '/start')

    fireEvent.click(screen.getByRole('button', { name: '다시 시도' }))

    await waitFor(() => expect(screen.getByRole('heading', { name: 'ses_recovered' })).toBeInTheDocument())
    expect(sessionProvider.get).toHaveBeenCalledTimes(2)
  })
})
