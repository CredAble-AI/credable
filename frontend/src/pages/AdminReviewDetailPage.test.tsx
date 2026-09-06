import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminReviewProvider } from '../hooks/useAdminReviewState'
import type { AdminReviewCaseContext, AdminReviewQueueItem } from '../types/adminReview'
import AdminReviewDetailPage from './AdminReviewDetailPage'

vi.mock('../hooks/useAdminReviewState', () => ({ adminReviewProvider: { get: vi.fn(), claim: vi.fn(), complete: vi.fn() } }))
vi.mock('../components/AssessmentExplanationPanel', () => ({ default: () => <div>AI 설명 패널</div> }))

const pending: AdminReviewQueueItem = { reviewId: 'uwr_assessment', sessionId: 'ses_sole', triggerType: 'CUSTOMER_ASSESSMENT_REVIEW', triggerId: 'arr_demo', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCodes: ['CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'], requestedAt: '2026-09-06T02:00:00Z', dataVersion: 'demo-v1', policyVersion: 'assessment-review-request-policy-v1', status: 'PENDING', demoOnly: true }
const inReview: AdminReviewQueueItem = { ...pending, status: 'IN_REVIEW', startedAt: '2026-09-06T02:10:00Z' }
const decisionNote = '서버 기록과 제출 정보가 일치해 기존 평가를 유지합니다.'
const completed: AdminReviewQueueItem = { ...inReview, status: 'COMPLETED', resultCode: 'ASSESSMENT_CONFIRMED', decisionNote, completedAt: '2026-09-06T02:20:00Z' }
const context: AdminReviewCaseContext = {
  assessment: { assessmentId: 'asm_demo', status: 'COMPLETED', calculatedAt: '2026-09-06T01:50:00Z', inputSnapshotId: 'dss_demo', modelVersion: 'model-v1', reasonCode: null, uncertainty: { pointEstimate: null, lowerBound: null, upperBound: null, gradeSet: ['DEMO_GRADE_B', 'DEMO_GRADE_C'], calibrationMode: 'RULE_TABLE', calibrationVersion: 'demo-v1', demoOnly: true }, demoOnly: true },
  boundaryCheck: null, selection: null, submission: null, quality: null, supplementalAssessment: null, comparison: null, resolution: null,
}

const renderPage = () => render(<MemoryRouter initialEntries={['/admin/reviews/uwr_assessment']}><Routes><Route path="/admin/reviews/:reviewId" element={<AdminReviewDetailPage />} /></Routes></MemoryRouter>)

describe('AdminReviewDetailPage', () => {
  beforeEach(() => {
    vi.mocked(adminReviewProvider.get).mockReset().mockResolvedValue({ review: pending, context })
    vi.mocked(adminReviewProvider.claim).mockReset().mockResolvedValue({ review: inReview, context })
    vi.mocked(adminReviewProvider.complete).mockReset().mockResolvedValue({ review: completed, context })
  })

  it('loads the detail without an administrator credential', async () => {
    renderPage()

    await waitFor(() => expect(adminReviewProvider.get).toHaveBeenCalledWith('uwr_assessment', expect.any(AbortSignal)))
    expect(screen.getByText(/이 화면은 시연에서만/)).toBeInTheDocument()
  })

  it('follows the server state from claim through completion', async () => {
    renderPage()

    await waitFor(() => expect(adminReviewProvider.get).toHaveBeenCalledWith('uwr_assessment', expect.any(AbortSignal)))
    expect(await screen.findByText('접수 대기 상태입니다.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '고객이 평가 결과 재확인을 요청했습니다' })).toBeInTheDocument()
    expect(screen.getByText('평가 구간 B · 평가 구간 C')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '전체 처리 이력' })).toHaveAttribute('href', '/admin/sessions/ses_sole/audit')
    fireEvent.click(screen.getByRole('button', { name: '검토 시작' }))

    await waitFor(() => expect(adminReviewProvider.claim).toHaveBeenCalledWith('uwr_assessment', expect.any(AbortSignal)))
    const resultSelect = await screen.findByLabelText('최종 처리 결과')
    expect(screen.getByRole('option', { name: /평가 확인/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Evidence 확인/ })).not.toBeInTheDocument()
    fireEvent.change(resultSelect, { target: { value: 'ASSESSMENT_CONFIRMED' } })
    // 판단 사유를 적기 전에는 확정할 수 없다.
    expect(screen.getByRole('button', { name: '선택한 결과로 확정' })).toBeDisabled()
    fireEvent.change(screen.getByLabelText('판단 사유'), { target: { value: decisionNote } })
    fireEvent.click(screen.getByRole('button', { name: '선택한 결과로 확정' }))

    await waitFor(() => expect(adminReviewProvider.complete).toHaveBeenCalledWith('uwr_assessment', 'ASSESSMENT_CONFIRMED', decisionNote, expect.any(AbortSignal)))
    expect(await screen.findByText(/이 건은/)).toHaveTextContent('평가 확인')
    expect(screen.getByText(decisionNote)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '선택한 결과로 확정' })).not.toBeInTheDocument()
  })

  it('shows the AI summary separately from the underwriter decision', async () => {
    vi.mocked(adminReviewProvider.get).mockResolvedValue({ review: pending, context })
    renderPage()

    expect(await screen.findByRole('heading', { name: '서버가 확정한 결과의 요약' })).toBeInTheDocument()
    expect(screen.getByText('AI 설명 패널')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '검토를 시작해주세요' })).toBeInTheDocument()
  })

  it('rejects a detail response for another review id', async () => {
    vi.mocked(adminReviewProvider.get).mockResolvedValue({ review: { ...pending, reviewId: 'uwr_other' }, context })
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('요청한 검토 ID와 서버 응답이 일치하지 않습니다.')
    expect(screen.queryByText('uwr_other')).not.toBeInTheDocument()
  })

  it('supports the assessment result contract for an automated stop trigger', async () => {
    vi.mocked(adminReviewProvider.get).mockResolvedValue({
      review: {
        ...inReview,
        triggerType: 'POLICY_BOUNDARY',
        triggerId: 'pbc_demo',
        reasonCodes: ['DEMO_GRADE_POLICY_NOT_CONFIGURED'],
      },
      context: { ...context, boundaryCheck: { boundaryCheckId: 'pbc_demo', assessmentId: 'asm_demo', checkedAt: '2026-09-06T01:55:00Z', decision: { status: 'POLICY_BLOCKED', possibleRoutes: [], crossedBoundaryCodes: [], stopReason: 'DEMO_GRADE_POLICY_NOT_CONFIGURED', underwriterRequired: true }, inputSnapshotId: 'dss_demo', calibrationVersion: 'demo-v1', policyVersion: 'demo-v1', demoOnly: true } },
    })
    renderPage()

    expect(await screen.findByRole('heading', { level: 3, name: '정책상 자동 판단 중단' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /평가 확인/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Evidence 확인/ })).not.toBeInTheDocument()
  })

  it('shows the exact submitted file and all quality checks for an evidence review', async () => {
    const evidenceReview: AdminReviewQueueItem = { ...inReview, triggerType: 'EVIDENCE_QUALITY', triggerId: 'evq_demo', evidenceType: 'CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY', targetType: undefined, targetAssessmentId: undefined, reasonCodes: ['DEMO_FILE_METADATA_OR_HASH_CHANGED'] }
    const evidenceContext: AdminReviewCaseContext = {
      submission: { submissionId: 'sub_demo', selectionId: 'evs_demo', evidenceType: evidenceReview.evidenceType!, sourceType: 'CUSTOMER_SUBMITTED', submissionMode: 'DEMO_FILE_UPLOAD', status: 'RECEIVED', submittedAt: '2026-09-06T01:59:00Z', observedAt: '2026-09-05T01:59:00Z', submissionSnapshotHash: 'a'.repeat(64), dataVersion: 'demo-v1', uploadedFile: { demoFileId: 'file_changed', fileName: '최근_매출_입금_요약서_변조의심.pdf', contentType: 'application/pdf', sizeBytes: 4096, sha256: 'b'.repeat(64) }, evidenceConsentId: 'evc_demo', consentScopeVersion: 'demo-v1', demoOnly: true },
      quality: { qualityCheckId: 'evq_demo', submissionId: 'sub_demo', evidenceType: evidenceReview.evidenceType!, status: 'REVIEW_REQUIRED', checks: [
        { dimension: 'PROVENANCE', status: 'PASSED', rationaleCode: 'DEMO_SERVER_DOCUMENT_PROVENANCE_CONFIRMED' }, { dimension: 'FRESHNESS', status: 'PASSED', rationaleCode: 'DEMO_MANIFEST_POINT_IN_TIME_VALID' }, { dimension: 'AUTHENTICITY', status: 'NOT_VERIFIED', rationaleCode: 'DEMO_SERVER_FILE_HASH_NOT_VERIFIED' }, { dimension: 'COMPLETENESS', status: 'PASSED', rationaleCode: 'DEMO_MANIFEST_REQUIRED_FIELDS_PRESENT' }, { dimension: 'CONSISTENCY', status: 'PASSED', rationaleCode: 'DEMO_MANIFEST_TOTALS_CONSISTENT' }, { dimension: 'MANIPULATION_RISK', status: 'FAILED', rationaleCode: 'DEMO_FILE_METADATA_OR_HASH_CHANGED' },
      ], rejectionCodes: ['DEMO_SERVER_FILE_HASH_NOT_VERIFIED', 'DEMO_FILE_METADATA_OR_HASH_CHANGED'], suspicionCodes: ['DEMO_FILE_METADATA_OR_HASH_CHANGED'], eligibleForReassessment: false, nextAction: 'UNDERWRITER_REVIEW', underwriterRequired: true, checkedAt: evidenceReview.requestedAt, submissionSnapshotHash: 'a'.repeat(64), dataVersion: 'demo-v1', qualityPolicyVersion: 'demo-v1', demoOnly: true },
    }
    vi.mocked(adminReviewProvider.get).mockResolvedValue({ review: evidenceReview, context: evidenceContext })
    renderPage()

    expect(await screen.findByRole('heading', { level: 3, name: '최근 매출·입금 요약' })).toBeInTheDocument()
    expect(screen.getByText('최근_매출_입금_요약서_변조의심.pdf')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '제출 파일 확인' })).toHaveAttribute('href', '/v1/sessions/ses_sole/evidence/selections/evs_demo/demo-files/file_changed/download')
    for (const label of ['출처', '최신성', '진위', '완전성', '일관성', '조작 위험']) expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.queryByText('CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY')).not.toBeInTheDocument()
  })
})
