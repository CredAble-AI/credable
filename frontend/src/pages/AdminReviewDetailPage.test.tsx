import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminAuditProvider } from '../hooks/useAdminAuditState'
import { adminReviewProvider } from '../hooks/useAdminReviewState'
import type { AdminReviewQueueItem } from '../types/adminReview'
import AdminReviewDetailPage from './AdminReviewDetailPage'

vi.mock('../hooks/useAdminReviewState', () => ({ adminReviewProvider: { get: vi.fn(), claim: vi.fn(), complete: vi.fn() } }))
vi.mock('../hooks/useAdminAuditState', () => ({ adminAuditProvider: { list: vi.fn() } }))

const pending: AdminReviewQueueItem = { reviewId: 'uwr_assessment', sessionId: 'ses_sole', triggerType: 'CUSTOMER_ASSESSMENT_REVIEW', triggerId: 'arr_demo', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCodes: ['CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'], requestedAt: '2026-09-06T02:00:00Z', dataVersion: 'demo-v1', policyVersion: 'assessment-review-request-policy-v1', status: 'PENDING', demoOnly: true }
const inReview: AdminReviewQueueItem = { ...pending, status: 'IN_REVIEW', startedAt: '2026-09-06T02:10:00Z' }
const completed: AdminReviewQueueItem = { ...inReview, status: 'COMPLETED', resultCode: 'ASSESSMENT_CONFIRMED', completedAt: '2026-09-06T02:20:00Z' }

const renderPage = () => render(<MemoryRouter initialEntries={['/admin/reviews/uwr_assessment']}><Routes><Route path="/admin/reviews/:reviewId" element={<AdminReviewDetailPage />} /></Routes></MemoryRouter>)

describe('AdminReviewDetailPage', () => {
  beforeEach(() => {
    vi.mocked(adminReviewProvider.get).mockReset().mockResolvedValue({ review: pending })
    vi.mocked(adminReviewProvider.claim).mockReset().mockResolvedValue({ review: inReview })
    vi.mocked(adminReviewProvider.complete).mockReset().mockResolvedValue({ review: completed })
    vi.mocked(adminAuditProvider.list).mockReset().mockResolvedValue({
      sessionId: 'ses_sole', demoOnly: true, nextCursor: null,
      events: [
        { eventId: 'evt_boundary', sessionId: 'ses_sole', requestId: 'req_boundary', stage: 'POLICY_BOUNDARY_CHECKED', timestamp: '2026-09-06T01:55:00Z', actor: 'SYSTEM', inputVersion: 'pbc_demo', inputSnapshotHash: 'a'.repeat(64), outputSummary: { boundaryStatus: 'AMBIGUOUS', possibleRouteCount: 2, underwriterRequired: false }, dataVersion: 'demo-v1', modelVersion: null, policyVersion: 'boundary-v1' },
        { eventId: 'evt_baseline', sessionId: 'ses_sole', requestId: 'req_baseline', stage: 'ASSESSMENT_RUN', timestamp: '2026-09-06T01:50:00Z', actor: 'SYSTEM', inputVersion: 'asm_demo', inputSnapshotHash: 'b'.repeat(64), outputSummary: { assessmentStatus: 'COMPLETED' }, dataVersion: 'demo-v1', modelVersion: 'model-v1', policyVersion: null },
      ],
    })
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
    expect(screen.getByText('경계에 걸침')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '전체 처리 이력' })).toHaveAttribute('href', '/admin/sessions/ses_sole/audit')
    fireEvent.click(screen.getByRole('button', { name: '검토 시작' }))

    await waitFor(() => expect(adminReviewProvider.claim).toHaveBeenCalledWith('uwr_assessment', expect.any(AbortSignal)))
    const resultSelect = await screen.findByLabelText('최종 처리 결과')
    expect(screen.getByRole('option', { name: /평가 확인/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Evidence 확인/ })).not.toBeInTheDocument()
    fireEvent.change(resultSelect, { target: { value: 'ASSESSMENT_CONFIRMED' } })
    fireEvent.click(screen.getByRole('button', { name: '선택한 결과로 확정' }))

    await waitFor(() => expect(adminReviewProvider.complete).toHaveBeenCalledWith('uwr_assessment', 'ASSESSMENT_CONFIRMED', expect.any(AbortSignal)))
    expect(await screen.findByText(/이 건은/)).toHaveTextContent('평가 확인')
    expect(screen.queryByRole('button', { name: '선택한 결과로 확정' })).not.toBeInTheDocument()
  })

  it('rejects a detail response for another review id', async () => {
    vi.mocked(adminReviewProvider.get).mockResolvedValue({ review: { ...pending, reviewId: 'uwr_other' } })
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
    })
    renderPage()

    expect(await screen.findByRole('heading', { level: 3, name: '정책 경계 확인' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: /평가 확인/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Evidence 확인/ })).not.toBeInTheDocument()
  })
})
