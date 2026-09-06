import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { dataConnectionProvider } from '../hooks/useDataConnectionState'
import type { ApiError } from '../types/api'
import type { DataSourceListResponse, DataSourceState } from '../types/dataConnection'
import type { CustomerSession } from '../types/customerSession'
import DataConnectionPage from './DataConnectionPage'

vi.mock('../hooks/useDataConnectionState', () => ({
  dataConnectionProvider: {
    list: vi.fn(),
    refresh: vi.fn(),
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
  },
  consents: {
    required: { customerIdentity: false, accountSummary: false, creditInformation: false },
    optional: { submittedDocuments: false, otherInstitutions: false, partnerData: false },
  },
  demoOnly: true,
  createdAt: '2026-09-06T00:00:00+09:00',
  updatedAt: '2026-09-06T00:00:00+09:00',
}

const source = (overrides: Partial<DataSourceState> = {}): DataSourceState => ({
  sourceType: 'BANK_INTERNAL',
  displayName: '은행 내부 데이터',
  retrievalStatus: 'NOT_REQUESTED',
  verificationStatus: 'NOT_STARTED',
  observedAt: null,
  retrievedAt: null,
  dataVersion: null,
  reasonCode: null,
  demoOnly: true,
  ...overrides,
})
const response = (dataSources: DataSourceState[]): DataSourceListResponse => ({
  sessionId: session.sessionId,
  dataSources,
  demoOnly: true,
})
const renderPage = () => render(
  <MemoryRouter initialEntries={['/data-connection']}>
    <Routes>
      <Route path="/data-connection" element={<DataConnectionPage />} />
      <Route path="/assessment" element={<h1>기준평가 화면</h1>} />
    </Routes>
  </MemoryRouter>,
)

describe('DataConnectionPage', () => {
  beforeEach(() => {
    vi.mocked(useCustomerSession).mockReset().mockReturnValue({ session, loading: false })
    vi.mocked(dataConnectionProvider.list).mockReset()
    vi.mocked(dataConnectionProvider.refresh).mockReset()
  })

  it('shows only the two baseline sources before additional evidence is requested', async () => {
    vi.mocked(dataConnectionProvider.list).mockResolvedValue(response([
      source(),
      source({ sourceType: 'CREDIT_INFORMATION', displayName: '신용정보', retrievalStatus: 'CONSENT_REQUIRED', reasonCode: 'CONSENT_REQUIRED' }),
      source({ sourceType: 'CUSTOMER_SUBMITTED', displayName: '고객 제출 데이터', retrievalStatus: 'NO_DATA', retrievedAt: '2026-09-06T00:00:00Z', reasonCode: 'DEMO_DATA_NOT_CONFIGURED' }),
      source({ sourceType: 'EXTERNAL_CONNECTED', displayName: '외부 연결 데이터', retrievalStatus: 'FAILED', retrievedAt: '2026-09-06T00:00:00Z', reasonCode: 'DATA_SOURCE_ADAPTER_ERROR' }),
    ]))
    renderPage()

    await screen.findByRole('heading', { level: 3, name: '은행 내부 데이터' })
    expect(screen.getAllByRole('heading', { level: 3 }).map((heading) => heading.textContent)).toEqual([
      '은행 내부 데이터', '신용정보',
    ])
    expect(screen.getByText('연결 상태 · 동의 필요')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 3, name: '고객 제출 데이터' })).not.toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 3, name: '외부 연결 데이터' })).not.toBeInTheDocument()
    expect(screen.queryByText('시연 기술 정보 보기')).not.toBeInTheDocument()
    expect(screen.queryByText('은행 보유 · 필수')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /다시 조회/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '기준평가 데이터 불러오기' })).toBeInTheDocument()
  })

  it('keeps refresh results visible before moving to the assessment', async () => {
    vi.mocked(dataConnectionProvider.list).mockResolvedValue(response([
      source(),
      source({ sourceType: 'CREDIT_INFORMATION', displayName: '신용정보' }),
    ]))
    const verified = { retrievalStatus: 'RETRIEVED', verificationStatus: 'VERIFIED', observedAt: '2026-08-31T23:59:59+09:00', retrievedAt: '2026-09-06T00:00:00Z' } as const
    vi.mocked(dataConnectionProvider.refresh).mockResolvedValue(response([
      source({ ...verified, dataVersion: 'synthetic-bank-data-v1' }),
      source({ ...verified, sourceType: 'CREDIT_INFORMATION', displayName: '신용정보', dataVersion: 'synthetic-credit-information-v1' }),
    ]))
    renderPage()

    expect(await screen.findAllByText('연결 상태 · 조회 전')).toHaveLength(2)
    fireEvent.click(screen.getByRole('button', { name: '기준평가 데이터 불러오기' }))

    await waitFor(() => expect(dataConnectionProvider.refresh).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal)))
    expect(await screen.findByText('기준평가에 필요한 두 출처의 조회와 검증이 완료됐습니다.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: '기준평가에 사용할 데이터 출처를 확인합니다' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '기존 평가 결과 확인' }))
    expect(await screen.findByRole('heading', { level: 1, name: '기준평가 화면' })).toBeInTheDocument()
  })

  it('shows a retry action for retryable list errors', async () => {
    vi.mocked(dataConnectionProvider.list).mockRejectedValue({
      code: 'DATA_SOURCE_REQUEST_FAILED',
      message: '데이터 출처를 불러오지 못했습니다.',
      requestId: 'req_demo',
      retryable: true,
    } satisfies ApiError)
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('데이터 출처를 불러오지 못했습니다.')
    expect(screen.getByText(/Request ID: req_demo/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '다시 확인' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '기준평가 데이터 불러오기' })).not.toBeInTheDocument()
  })
})
