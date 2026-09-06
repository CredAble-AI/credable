import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { policyBoundaryProvider } from '../hooks/useAssessmentState'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { evidenceSelectionProvider } from '../hooks/useEvidenceSelectionState'
import type { CustomerSession } from '../types/customerSession'
import type { EvidenceSelectionResponse } from '../types/evidenceSelection'
import type { PolicyBoundaryCheckResponse } from '../types/policyBoundary'
import EvidenceSelectionPage from './EvidenceSelectionPage'

vi.mock('../hooks/useAssessmentState', () => ({ policyBoundaryProvider: { get: vi.fn() } }))
vi.mock('../hooks/useEvidenceSelectionState', () => ({ evidenceSelectionProvider: { get: vi.fn(), selectNext: vi.fn() } }))
vi.mock('../hooks/useCustomerSession', () => ({ useCustomerSession: vi.fn() }))

const session: CustomerSession = {
  sessionId: 'ses_demo', selectedProfileType: 'small-business', demoOnly: true,
  demoProfile: { demoProfileId: 'small-business', businessBorrowerType: 'SOLE_PROPRIETOR', displayName: '개인사업자', description: '개업 초기 소상공인을 예시로 한 개인사업자 합성 Demo 사례' },
  consents: { required: { customerIdentity: false, accountSummary: false, creditInformation: false }, optional: { submittedDocuments: false, otherInstitutions: false, partnerData: false } },
  createdAt: '2026-09-06T00:00:00+09:00', updatedAt: '2026-09-06T00:00:00+09:00',
}
const boundary = (status: 'STABLE' | 'AMBIGUOUS'): PolicyBoundaryCheckResponse => ({
  sessionId: session.sessionId,
  boundaryCheck: {
    boundaryCheckId: 'pbc_demo', assessmentId: 'asm_demo', checkedAt: '2026-09-06T01:01:00+09:00', inputSnapshotId: 'dss_demo', calibrationVersion: 'demo-calibration-v1', policyVersion: 'demo-policy-v1', demoOnly: true,
    decision: { status, possibleRoutes: status === 'AMBIGUOUS' ? ['DEMO_PATH_1', 'DEMO_PATH_2'] : ['DEMO_PATH_1'], crossedBoundaryCodes: status === 'AMBIGUOUS' ? ['DEMO_BOUNDARY_1_2'] : [], stopReason: status === 'STABLE' ? 'PATH_STABLE' : null, underwriterRequired: false },
  },
})
const selected: EvidenceSelectionResponse = {
  sessionId: session.sessionId,
  selection: {
    selectionId: 'evs_demo', boundaryCheckId: 'pbc_demo', resolutionId: null, rejectedQualityCheckId: null, iteration: 1, status: 'SELECTED', evaluatedCandidateCount: 2, stopReason: null, underwriterRequired: false, selectedAt: '2026-09-06T01:02:00+09:00', calibrationVersion: 'demo-calibration-v1', boundaryPolicyVersion: 'demo-policy-v1', selectionPolicyVersion: 'demo-selection-v1', demoOnly: true,
    selectedEvidence: { evidenceType: 'CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY', displayName: '최근 매출·입금 요약', description: '최근 매출 발생과 실제 입금 흐름을 확인할 수 있는 고객 제출 자료', sourceType: 'CUSTOMER_SUBMITTED', collectionMode: 'DEMO_FILE_UPLOAD', availability: 'CONSENT_REQUIRED', rationaleCodes: ['DEMO_RESOLVE_BOUNDARY_1_2', 'DEMO_MINIMUM_SINGLE_REQUEST'], consentScope: { scopeVersion: 'demo-recent-revenue-consent-v1', purposeCode: 'SUPPLEMENTAL_CREDIT_ASSESSMENT', purposeDescription: '기존 평가의 불확실성을 확인하기 위한 보완평가에 사용', dataCategories: ['MONTHLY_SALES'], periodStart: '2026-03-01', periodEnd: '2026-08-31', required: true }, demoOnly: true },
  },
}
const renderPage = (entry = '/evidence') => render(<MemoryRouter initialEntries={[entry]}><Routes><Route path="/evidence" element={<EvidenceSelectionPage />} /><Route path="/assessment" element={<h1>기준평가 화면</h1>} /></Routes></MemoryRouter>)

describe('EvidenceSelectionPage', () => {
  beforeEach(() => {
    vi.mocked(useCustomerSession).mockReset().mockReturnValue({ session, loading: false })
    vi.mocked(policyBoundaryProvider.get).mockReset().mockResolvedValue(boundary('AMBIGUOUS'))
    vi.mocked(evidenceSelectionProvider.get).mockReset()
    vi.mocked(evidenceSelectionProvider.selectNext).mockReset()
  })

  it('recovers an empty selection without automatically posting', async () => {
    vi.mocked(evidenceSelectionProvider.get).mockResolvedValue({ sessionId: session.sessionId, selection: null })
    renderPage()

    expect(await screen.findByRole('button', { name: '필요한 자료 확인' })).toBeInTheDocument()
    expect(evidenceSelectionProvider.get).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal))
    expect(evidenceSelectionProvider.selectNext).not.toHaveBeenCalled()
  })

  it('shows only the single Evidence selected by the server', async () => {
    vi.mocked(evidenceSelectionProvider.get).mockResolvedValue({ sessionId: session.sessionId, selection: null })
    vi.mocked(evidenceSelectionProvider.selectNext).mockResolvedValue(selected)
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '필요한 자료 확인' }))

    expect(await screen.findByRole('heading', { name: '최근 매출·입금 요약' })).toBeInTheDocument()
    expect(screen.getByText('동의 확인 필요')).toBeInTheDocument()
    expect(screen.getByText('2건')).toBeInTheDocument()
    expect(screen.getByText('DEMO_MINIMUM_SINGLE_REQUEST')).toBeInTheDocument()
    expect(screen.getByText('불필요한 추가 요청을 막기 위해 한 건만 선택했습니다.')).toBeInTheDocument()
    expect(screen.queryByText(/최적 Evidence|utility/i)).not.toBeInTheDocument()
    expect(evidenceSelectionProvider.selectNext).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal))
  })

  it('returns to the assessment when the latest boundary is not ambiguous', async () => {
    vi.mocked(policyBoundaryProvider.get).mockResolvedValue(boundary('STABLE'))
    renderPage()

    expect(await screen.findByRole('heading', { name: '기준평가 화면' })).toBeInTheDocument()
    await waitFor(() => expect(evidenceSelectionProvider.get).not.toHaveBeenCalled())
  })

  it('requests the next server-selected Evidence when entered from a resolution action', async () => {
    const repeated = { ...selected, selection: selected.selection && { ...selected.selection, selectionId: 'evs_second', resolutionId: 'res_demo', iteration: 2 } }
    vi.mocked(evidenceSelectionProvider.selectNext).mockResolvedValue(repeated)
    vi.mocked(evidenceSelectionProvider.get).mockResolvedValue(repeated)

    renderPage('/evidence?selectNext=1')

    expect(await screen.findByText('evs_second')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(evidenceSelectionProvider.selectNext).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal))
  })
})
