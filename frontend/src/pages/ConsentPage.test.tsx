import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { consentProvider } from '../hooks/useConsentState'
import { useCustomerSession } from '../hooks/useCustomerSession'
import type { ApiError } from '../types/api'
import type { ConsentListResponse, ConsentState } from '../types/consent'
import type { CustomerSession } from '../types/customerSession'
import ConsentPage from './ConsentPage'

vi.mock('../hooks/useConsentState', () => ({
  consentProvider: {
    list: vi.fn(),
    grant: vi.fn(),
    withdraw: vi.fn(),
  },
}))

vi.mock('../hooks/useCustomerSession', () => ({ useCustomerSession: vi.fn() }))

const session: CustomerSession = {
  sessionId: 'ses_demo',
  selectedProfileType: 'small-business',
  demoProfile: {
    demoProfileId: 'small-business',
    businessBorrowerType: 'SOLE_PROPRIETOR',
    displayName: '개인사업자',
    description: '개업 초기 소상공인을 예시로 한 개인사업자 합성 Demo 사례',
    scenarioLabel: '정책 경계에 걸린 사례',
    scenarioSummary: '기존 평가 구간이 두 정책 경로에 걸쳐 있어 최소 증빙 한 건을 요청하는 흐름을 확인합니다.',
  },
  consents: {
    required: { customerIdentity: false, accountSummary: false, creditInformation: false },
    optional: { submittedDocuments: false, otherInstitutions: false, partnerData: false },
  },
  demoOnly: true,
  createdAt: '2026-09-06T00:00:00+09:00',
  updatedAt: '2026-09-06T00:00:00+09:00',
}

const consent = (overrides: Partial<ConsentState> = {}): ConsentState => ({
  sourceType: 'BANK_INTERNAL',
  displayName: '은행 내부 데이터',
  description: '도입 은행이 보유한 고객·계좌·대출 관련 데이터',
  required: null,
  status: 'PENDING',
  grantedAt: null,
  withdrawnAt: null,
  updatedAt: null,
  scopeVersion: 'demo-consent-scopes-v2',
  demoOnly: true,
  ...overrides,
})

const response = (consents: ConsentState[]): ConsentListResponse => ({
  sessionId: session.sessionId,
  consents,
  scopeVersion: 'demo-consent-scopes-v2',
  demoOnly: true,
})

const renderPage = () => render(
  <MemoryRouter initialEntries={['/consent']}>
    <Routes>
      <Route path="/consent" element={<ConsentPage />} />
      <Route path="/data-connection" element={<h1>데이터 연결 화면</h1>} />
    </Routes>
  </MemoryRouter>,
)

describe('ConsentPage', () => {
  beforeEach(() => {
    vi.mocked(useCustomerSession).mockReset().mockReturnValue({ session, loading: false })
    vi.mocked(consentProvider.list).mockReset()
    vi.mocked(consentProvider.grant).mockReset()
    vi.mocked(consentProvider.withdraw).mockReset()
  })

  it('shows only the sources needed for the existing assessment', async () => {
    vi.mocked(consentProvider.list).mockResolvedValue(response([
      consent({ required: true }),
      consent({ sourceType: 'CUSTOMER_SUBMITTED', displayName: '고객 제출 데이터', description: '고객이 직접 제출하는 소득·사업·재무 관련 데이터', required: false }),
    ]))
    renderPage()

    expect(screen.getByRole('navigation', { name: '진행 단계' })).toHaveTextContent('시작동의데이터 연결기존 평가상품 비교')
    expect(await screen.findByRole('checkbox', { name: /은행 내부 데이터/ })).toBeInTheDocument()
    expect(screen.getByText('도입 은행이 보유한 고객·계좌·대출 관련 데이터')).toBeInTheDocument()
    expect(screen.getByText('동의 범위 확인 완료')).toBeInTheDocument()
    expect(screen.getByText('필수')).toBeInTheDocument()
    expect(screen.queryByRole('checkbox', { name: /고객 제출 데이터/ })).not.toBeInTheDocument()
    expect(screen.getAllByText('미동의')[0]?.closest('.consent-item__status')).toHaveClass('consent-item__status--pending')
    expect(screen.getByText(/계속하려면 필수 항목에 동의해주세요/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '데이터 연결로 이동' })).toBeDisabled()
  })

  it('updates the checkbox only after the grant response succeeds', async () => {
    const pending = consent({ required: true })
    const granted = consent({ required: true, status: 'GRANTED', grantedAt: '2026-09-06T00:00:00Z', updatedAt: '2026-09-06T00:00:00Z' })
    vi.mocked(consentProvider.list).mockResolvedValue(response([pending]))
    vi.mocked(consentProvider.grant).mockResolvedValue(granted)
    renderPage()

    const checkbox = await screen.findByRole('checkbox', { name: /은행 내부 데이터/ })
    expect(screen.getByRole('button', { name: '데이터 연결로 이동' })).toBeDisabled()
    fireEvent.click(checkbox)

    await waitFor(() => expect(consentProvider.grant).toHaveBeenCalledWith('ses_demo', 'BANK_INTERNAL', expect.any(AbortSignal)))
    await waitFor(() => expect(checkbox).toBeChecked())
    expect(screen.getByText('동의함').closest('.consent-item__status')).toHaveClass('consent-item__status--granted')
    expect(screen.getByText('은행 내부 데이터 동의를 반영했습니다.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '데이터 연결로 이동' })).toBeEnabled()
  })

  it('does not block progression when an optional consent update fails', async () => {
    vi.mocked(consentProvider.list).mockResolvedValue(response([consent({ required: false })]))
    vi.mocked(consentProvider.grant).mockRejectedValue({
      code: 'CONSENT_REQUEST_FAILED',
      message: '선택 동의를 반영하지 못했습니다.',
      retryable: true,
    } satisfies ApiError)
    renderPage()

    const checkbox = await screen.findByRole('checkbox', { name: /은행 내부 데이터/ })
    fireEvent.click(checkbox)

    expect(await screen.findByRole('alert')).toHaveTextContent('선택 동의를 반영하지 못했습니다.')
    expect(checkbox).not.toBeChecked()
    expect(screen.getByRole('button', { name: '데이터 연결로 이동' })).toBeEnabled()
  })

  it('shows a retry action when the consent list cannot be loaded', async () => {
    const apiError = { code: 'CONSENT_REQUEST_FAILED', message: '동의 상태를 불러오지 못했습니다.', requestId: 'req_demo', retryable: true } satisfies ApiError
    vi.mocked(consentProvider.list).mockRejectedValue(apiError)
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('동의 상태를 불러오지 못했습니다.')
    expect(screen.getByText('요청 ID req_demo')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '다시 시도' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '데이터 연결로 이동' })).toBeDisabled()
  })
})
