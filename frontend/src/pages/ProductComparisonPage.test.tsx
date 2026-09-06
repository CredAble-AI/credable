import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { mockAssessmentProvider } from '../mocks/assessmentProvider'
import { mockProductProvider } from '../mocks/productProvider'
import type { AssessmentResponse } from '../types/assessment'
import type { CustomerSession } from '../types/customerSession'
import type { ProductComparisonResult } from '../types/product'
import ProductComparisonPage from './ProductComparisonPage'

vi.mock('../hooks/useCustomerSession', () => ({ useCustomerSession: vi.fn() }))
vi.mock('../mocks/assessmentProvider', () => ({ mockAssessmentProvider: { get: vi.fn(), run: vi.fn() } }))
vi.mock('../mocks/productProvider', () => ({ mockProductProvider: { get: vi.fn(), refresh: vi.fn() } }))

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
    required: { customerIdentity: true, accountSummary: true, creditInformation: true },
    optional: { submittedDocuments: false, otherInstitutions: false, partnerData: false },
  },
  demoOnly: true,
  createdAt: '2026-09-06T00:00:00+09:00',
  updatedAt: '2026-09-06T00:00:00+09:00',
}

const assessment: AssessmentResponse = {
  sessionId: session.sessionId,
  assessment: {
    assessmentId: 'asm_demo', status: 'COMPLETED', calculatedAt: '2026-09-06T01:00:00+09:00', inputSnapshotId: 'dss_demo', modelVersion: 'demo-v1', reasonCode: null, uncertainty: null, demoOnly: true,
  },
}

const unavailable: ProductComparisonResult = {
  sessionId: session.sessionId, products: [], status: 'CATALOG_UNAVAILABLE', sortableFields: [], nullPlacement: 'LAST', initialOrder: 'CATALOG_SOURCE', canViewProducts: false, cannotProceedReason: 'PRODUCT_CATALOG_NOT_LOADED', resultAt: '2026-09-06T02:00:00+09:00', catalogSnapshotId: null, demoOnly: true,
}

const available: ProductComparisonResult = {
  ...unavailable,
  status: 'PUBLIC_ONLY',
  canViewProducts: true,
  cannotProceedReason: null,
  catalogSnapshotId: 'pcs_demo',
  products: [{
    applicationLinkAvailable: false,
    applicationUrl: null,
    product: {
      productId: 'prd_demo', productName: 'CredAble 운영자금', eligibilitySummary: '등록 사업자 대상',
      publicConditions: { maxAmount: { amount: '50000000', currency: 'KRW' }, annualRateRange: { minPercent: '4.50', maxPercent: '7.00' }, termRangeMonths: { minMonths: 12, maxMonths: 60 }, repaymentMethods: ['원리금균등'] },
      personalizedConditions: null, conditionStatus: 'PUBLIC_ONLY', conditionReasonCode: null,
      officialSource: { sourceName: 'CredAble Demo Bank', sourceUrl: null, effectiveDate: '2026-09-06' }, productVersion: 'demo-v1', applicationUrl: null, applicationReference: null, finalApprovalRequired: true, demoOnly: true,
    },
  }],
}

const renderPage = () => render(<MemoryRouter initialEntries={['/products']}><Routes><Route path="/products" element={<ProductComparisonPage />} /><Route path="/assessment" element={<h1>기준평가 화면</h1>} /></Routes></MemoryRouter>)

describe('ProductComparisonPage', () => {
  beforeEach(() => {
    vi.mocked(useCustomerSession).mockReset().mockReturnValue({ session, loading: false })
    vi.mocked(mockAssessmentProvider.get).mockReset().mockResolvedValue(assessment)
    vi.mocked(mockProductProvider.get).mockReset().mockResolvedValue(unavailable)
    vi.mocked(mockProductProvider.refresh).mockReset().mockResolvedValue(available)
  })

  it('recovers product state with GET without automatically refreshing the catalog', async () => {
    renderPage()

    expect(await screen.findByRole('button', { name: '상품 조건 불러오기' })).toBeInTheDocument()
    expect(mockProductProvider.get).toHaveBeenCalledTimes(1)
    expect(mockProductProvider.refresh).not.toHaveBeenCalled()
  })

  it('runs the full provider refresh only after the customer requests product conditions', async () => {
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '상품 조건 불러오기' }))

    await waitFor(() => expect(mockProductProvider.refresh).toHaveBeenCalledTimes(1))
    expect(await screen.findByText('1개 상품 조건을 확인했습니다.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'CredAble 운영자금' })).toBeInTheDocument()
  })

  it('keeps the previous product result visible when a refresh fails', async () => {
    vi.mocked(mockProductProvider.get).mockResolvedValue(available)
    vi.mocked(mockProductProvider.refresh).mockRejectedValue({ code: 'PRODUCT_QUERY_FAILED', message: '상품 조건 조회에 실패했습니다.', retryable: true })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '전체 조건 다시 확인' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('상품 조건 조회에 실패했습니다.')
    expect(screen.getByRole('heading', { name: 'CredAble 운영자금' })).toBeInTheDocument()
  })
})
