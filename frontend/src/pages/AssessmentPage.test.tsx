import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { assessmentProvider, policyBoundaryProvider } from '../hooks/useAssessmentState'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { evidenceSelectionProvider } from '../hooks/useEvidenceSelectionState'
import type { AssessmentResponse } from '../types/assessment'
import type { CustomerSession } from '../types/customerSession'
import type { EvidenceSelectionResponse } from '../types/evidenceSelection'
import type { PolicyBoundaryCheckResponse } from '../types/policyBoundary'
import AssessmentPage from './AssessmentPage'

vi.mock('../hooks/useAssessmentState', () => ({
  assessmentProvider: { get: vi.fn(), run: vi.fn() },
  policyBoundaryProvider: { get: vi.fn(), check: vi.fn() },
}))
vi.mock('../hooks/useCustomerSession', () => ({ useCustomerSession: vi.fn() }))
vi.mock('../hooks/useEvidenceSelectionState', () => ({ evidenceSelectionProvider: { get: vi.fn(), selectNext: vi.fn() } }))

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

const notRun: AssessmentResponse = {
  sessionId: session.sessionId,
  assessment: {
    assessmentId: null,
    status: 'NOT_RUN',
    calculatedAt: null,
    inputSnapshotId: null,
    modelVersion: null,
    reasonCode: null,
    uncertainty: null,
    demoOnly: true,
  },
}

const completed: AssessmentResponse = {
  sessionId: session.sessionId,
  assessment: {
    assessmentId: 'asm_demo',
    status: 'COMPLETED',
    calculatedAt: '2026-09-06T01:00:00+09:00',
    inputSnapshotId: 'dss_demo',
    modelVersion: 'demo-assessment-v1',
    reasonCode: null,
    uncertainty: {
      pointEstimate: null,
      lowerBound: null,
      upperBound: null,
      gradeSet: ['DEMO_GRADE_B', 'DEMO_GRADE_C'],
      calibrationMode: 'RULE_TABLE',
      calibrationVersion: 'demo-calibration-v1',
      demoOnly: true,
    },
    demoOnly: true,
  },
}

const ambiguous: PolicyBoundaryCheckResponse = {
  sessionId: session.sessionId,
  boundaryCheck: {
    boundaryCheckId: 'pbc_demo',
    assessmentId: 'asm_demo',
    checkedAt: '2026-09-06T01:01:00+09:00',
    decision: {
      status: 'AMBIGUOUS',
      possibleRoutes: ['DEMO_PATH_1', 'DEMO_PATH_2'],
      crossedBoundaryCodes: ['DEMO_BOUNDARY_1_2'],
      stopReason: null,
      underwriterRequired: false,
    },
    inputSnapshotId: 'dss_demo',
    calibrationVersion: 'demo-calibration-v1',
    policyVersion: 'demo-policy-v1',
    demoOnly: true,
  },
}

const stable: PolicyBoundaryCheckResponse = {
  ...ambiguous,
  boundaryCheck: {
    ...ambiguous.boundaryCheck!,
    decision: {
      status: 'STABLE',
      possibleRoutes: ['DEMO_PATH_1'],
      crossedBoundaryCodes: [],
      stopReason: 'PATH_STABLE',
      underwriterRequired: false,
    },
  },
}

const evidenceSelection: EvidenceSelectionResponse = {
  sessionId: session.sessionId,
  selection: {
    selectionId: 'evs_demo', boundaryCheckId: 'pbc_demo', resolutionId: null, rejectedQualityCheckId: null, iteration: 1, maxEvidenceRequests: 2, status: 'SELECTED', evaluatedCandidateCount: 2, stopReason: null, underwriterRequired: false,
    selectedAt: '2026-09-06T01:02:00+09:00', calibrationVersion: 'demo-calibration-v1', boundaryPolicyVersion: 'demo-policy-v1', selectionPolicyVersion: 'demo-selection-v1', sourceCreditAssessmentId: 'asm_demo', informationGapCodes: ['DEMO_RECENT_PERFORMANCE_NOT_REFLECTED'], baselineFeatureSnapshotId: 'dss_demo', baselineInformationCoverageCodes: [], demoOnly: true,
    selectedEvidence: { evidenceType: 'CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY', displayName: '최근 매출·입금 요약', description: '최근 매출 발생과 실제 입금 흐름을 확인할 수 있는 고객 제출 자료', sourceType: 'CUSTOMER_SUBMITTED', collectionMode: 'DEMO_FILE_UPLOAD', availability: 'CONSENT_REQUIRED', rationaleCodes: ['DEMO_RESOLVE_BOUNDARY_1_2'], consentScope: null, demoOnly: true },
  },
}

const renderPage = () => render(
  <MemoryRouter initialEntries={['/assessment']}>
    <Routes><Route path="/assessment" element={<AssessmentPage />} /><Route path="/evidence" element={<h1>Evidence 선택 화면</h1>} /><Route path="/products" element={<h1>상품 비교 화면</h1>} /></Routes>
  </MemoryRouter>,
)

describe('AssessmentPage', () => {
  beforeEach(() => {
    vi.mocked(useCustomerSession).mockReset().mockReturnValue({ session, loading: false })
    vi.mocked(assessmentProvider.get).mockReset()
    vi.mocked(assessmentProvider.run).mockReset()
    vi.mocked(policyBoundaryProvider.get).mockReset()
    vi.mocked(policyBoundaryProvider.check).mockReset()
    vi.mocked(evidenceSelectionProvider.get).mockReset().mockResolvedValue({ sessionId: session.sessionId, selection: null })
    vi.mocked(evidenceSelectionProvider.selectNext).mockReset().mockResolvedValue(evidenceSelection)
  })

  it('recovers NOT_RUN without automatically executing the assessment', async () => {
    vi.mocked(assessmentProvider.get).mockResolvedValue(notRun)
    renderPage()

    expect(await screen.findByRole('heading', { name: '기존 평가 확인 준비' })).toBeInTheDocument()
    expect(screen.queryByText('시연 기술 정보 보기')).not.toBeInTheDocument()
    expect(assessmentProvider.get).toHaveBeenCalledTimes(1)
    expect(assessmentProvider.run).not.toHaveBeenCalled()
    expect(policyBoundaryProvider.get).not.toHaveBeenCalled()
    expect(policyBoundaryProvider.check).not.toHaveBeenCalled()
    expect(evidenceSelectionProvider.get).not.toHaveBeenCalled()
    expect(screen.getByRole('button', { name: '기존 평가 결과 불러오기' })).toBeInTheDocument()
  })

  it('runs a completed assessment and then checks the server policy boundary', async () => {
    vi.mocked(assessmentProvider.get).mockResolvedValue(notRun)
    vi.mocked(assessmentProvider.run).mockResolvedValue(completed)
    vi.mocked(policyBoundaryProvider.check).mockResolvedValue(ambiguous)
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '기존 평가 결과 불러오기' }))

    await waitFor(() => expect(policyBoundaryProvider.check).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal)))
    await waitFor(() => expect(evidenceSelectionProvider.selectNext).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '현재 확인 가능한 결과' })).toBeInTheDocument()
    expect(screen.getByText('평가 구간 B')).toBeInTheDocument()
    expect(screen.getByText('평가 구간 C')).toBeInTheDocument()
    expect(screen.queryByText('모델 추정값')).not.toBeInTheDocument()
    expect(screen.queryByText('추정 범위')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '추가 자료 확인 필요' })).toBeInTheDocument()
    expect(screen.queryByText('심사역 재확인 패널')).not.toBeInTheDocument()
    expect(screen.getByText('기존 평가 기준시점 이후의 최근 매출·입금 흐름이 반영되지 않았습니다.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '최근 매출·입금 요약' })).toBeInTheDocument()
    expect(screen.getByText('정책 경계')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '요청 자료 제출하기' })).toHaveAttribute('href', '/evidence')
    expect(screen.queryByRole('link', { name: '필요한 자료 확인' })).not.toBeInTheDocument()
  })

  it('blocks boundary checking when the server cannot complete the assessment', async () => {
    vi.mocked(assessmentProvider.get).mockResolvedValue(notRun)
    vi.mocked(assessmentProvider.run).mockResolvedValue({
      sessionId: session.sessionId,
      assessment: {
        assessmentId: 'asm_insufficient',
        status: 'INSUFFICIENT_DATA',
        calculatedAt: '2026-09-06T01:00:00+09:00',
        inputSnapshotId: 'dss_demo',
        modelVersion: null,
        reasonCode: 'DEMO_VERIFIED_DATA_INSUFFICIENT',
        uncertainty: null,
        demoOnly: true,
      },
    })
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '기존 평가 결과 불러오기' }))

    expect(await screen.findByRole('heading', { name: '현재 데이터로 확인 불가' })).toBeInTheDocument()
    expect(screen.getByText('이 상태는 신용이 낮거나 대출 자격이 없다는 의미가 아닙니다.')).toBeInTheDocument()
    expect(evidenceSelectionProvider.get).not.toHaveBeenCalled()
    expect(policyBoundaryProvider.get).not.toHaveBeenCalled()
    expect(policyBoundaryProvider.check).not.toHaveBeenCalled()
  })

  it('recovers a completed assessment with GET and requires an explicit boundary check', async () => {
    vi.mocked(assessmentProvider.get).mockResolvedValue(completed)
    vi.mocked(policyBoundaryProvider.get).mockResolvedValue({ sessionId: session.sessionId, boundaryCheck: null })
    vi.mocked(policyBoundaryProvider.check).mockResolvedValue(ambiguous)
    renderPage()

    expect(await screen.findByRole('button', { name: '정책 경계 확인' })).toBeInTheDocument()
    expect(policyBoundaryProvider.get).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal))
    expect(policyBoundaryProvider.check).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '정책 경계 확인' }))
    await waitFor(() => expect(policyBoundaryProvider.check).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(evidenceSelectionProvider.selectNext).toHaveBeenCalledTimes(1))
  })

  it('links a stable server boundary directly to product conditions', async () => {
    vi.mocked(assessmentProvider.get).mockResolvedValue(completed)
    vi.mocked(policyBoundaryProvider.get).mockResolvedValue(stable)
    renderPage()

    expect(await screen.findByRole('heading', { name: '추가 자료 없이 확인 완료' })).toBeInTheDocument()
    expect(screen.getByText('추가 자료 없이 자사 상품 조건을 확인할 수 있습니다.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '자사 상품 조건 확인' })).toHaveAttribute('href', '/products')
    expect(evidenceSelectionProvider.get).not.toHaveBeenCalled()
  })
})
