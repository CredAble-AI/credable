import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminReviewProvider } from '../hooks/useAdminReviewState'
import type { AdminReviewQueueResponse } from '../types/adminReview'
import AdminReviewListPage from './AdminReviewListPage'

vi.mock('../hooks/useAdminReviewState', () => ({ adminReviewProvider: { list: vi.fn() } }))

const queue: AdminReviewQueueResponse = {
  totalCount: 5, limit: 20, offset: 0, demoOnly: true,
  items: [
    { reviewId: 'uwr_assessment', sessionId: 'ses_sole', triggerType: 'CUSTOMER_ASSESSMENT_REVIEW', triggerId: 'arr_demo', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCodes: ['CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'], requestedAt: '2026-09-06T02:00:00Z', dataVersion: 'demo-v1', policyVersion: 'assessment-review-request-policy-v1', status: 'PENDING', demoOnly: true },
    { reviewId: 'uwr_evidence', sessionId: 'ses_corp', triggerType: 'EVIDENCE_QUALITY', triggerId: 'evq_demo', evidenceType: 'RECENT_REVENUE_SUMMARY', reasonCodes: ['DEMO_FILE_HASH_MISMATCH'], requestedAt: '2026-09-06T01:00:00Z', dataVersion: 'demo-v1', policyVersion: 'demo-quality-v1', status: 'IN_REVIEW', startedAt: '2026-09-06T01:10:00Z', demoOnly: true },
    { reviewId: 'uwr_boundary', sessionId: 'ses_sole', triggerType: 'POLICY_BOUNDARY', triggerId: 'pbc_demo', reasonCodes: ['DEMO_GRADE_POLICY_NOT_CONFIGURED'], requestedAt: '2026-09-06T00:50:00Z', dataVersion: 'snap-v1', policyVersion: 'demo-policy-v1', status: 'PENDING', demoOnly: true },
    { reviewId: 'uwr_selection', sessionId: 'ses_sole', triggerType: 'EVIDENCE_SELECTION', triggerId: 'evs_demo', reasonCodes: ['NO_NOVEL_EVIDENCE'], requestedAt: '2026-09-06T00:40:00Z', dataVersion: 'snap-v1', policyVersion: 'demo-selection-v1', status: 'PENDING', demoOnly: true },
    { reviewId: 'uwr_resolution', sessionId: 'ses_sole', triggerType: 'EVIDENCE_RESOLUTION', triggerId: 'res_demo', reasonCodes: ['UNCERTAINTY_COMPARISON_NOT_RELIABLE'], requestedAt: '2026-09-06T00:30:00Z', dataVersion: 'sam-v1', policyVersion: 'demo-policy-v1', status: 'PENDING', demoOnly: true },
  ],
}
const renderPage = () => render(<MemoryRouter><AdminReviewListPage /></MemoryRouter>)

describe('AdminReviewListPage', () => {
  beforeEach(() => { localStorage.clear(); vi.mocked(adminReviewProvider.list).mockReset().mockResolvedValue(queue) })

  it('loads the demo queue without an administrator credential', async () => {
    renderPage()

    await waitFor(() => expect(adminReviewProvider.list).toHaveBeenCalledWith({ limit: 20, offset: 0, status: null }, expect.any(AbortSignal)))
    expect(screen.getByText(/합성 Demo 데이터 전용 화면/)).toBeInTheDocument()
    expect(localStorage.length).toBe(0)
  })

  it('loads every trigger shape', async () => {
    renderPage()

    await waitFor(() => expect(adminReviewProvider.list).toHaveBeenCalledWith({ limit: 20, offset: 0, status: null }, expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: 'uwr_assessment' })).toBeInTheDocument()
    expect(screen.getByText('보완평가')).toBeInTheDocument()
    expect(screen.getByText('RECENT_REVENUE_SUMMARY')).toBeInTheDocument()
    expect(screen.getByText('정책 경계 검토')).toBeInTheDocument()
    expect(screen.getByText('최소 증빙 선택 검토')).toBeInTheDocument()
    expect(screen.getByText('증빙 수집 종료 검토')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: '상세 확인' })[0]).toHaveAttribute('href', '/admin/reviews/uwr_assessment')
  })

  it('requests a server-filtered page and supports manual refresh', async () => {
    renderPage()
    await screen.findByRole('heading', { name: 'uwr_assessment' })

    fireEvent.change(screen.getByLabelText('처리 상태'), { target: { value: 'PENDING' } })
    await waitFor(() => expect(adminReviewProvider.list).toHaveBeenLastCalledWith({ limit: 20, offset: 0, status: 'PENDING' }, expect.any(AbortSignal)))
    const callsBeforeRefresh = vi.mocked(adminReviewProvider.list).mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: '상태 새로고침' }))
    await waitFor(() => expect(adminReviewProvider.list).toHaveBeenCalledTimes(callsBeforeRefresh + 1))
  })

  it('shows a retry action after a server failure', async () => {
    vi.mocked(adminReviewProvider.list).mockRejectedValue({ code: 'ADMIN_REVIEW_LIST_FAILED', message: '검토 목록을 불러오지 못했습니다.', retryable: true })
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('검토 목록을 불러오지 못했습니다.')
    expect(screen.getByRole('button', { name: '다시 확인' })).toBeInTheDocument()
  })

  it('requests the next bounded server page', async () => {
    vi.mocked(adminReviewProvider.list).mockImplementation(async (query) => ({ ...queue, totalCount: 21, offset: query.offset, items: [queue.items[query.offset === 0 ? 0 : 1]] }))
    renderPage()

    fireEvent.click(await screen.findByRole('button', { name: '다음 페이지' }))

    await waitFor(() => expect(adminReviewProvider.list).toHaveBeenLastCalledWith({ limit: 20, offset: 20, status: null }, expect.any(AbortSignal)))
    expect(await screen.findByText('21–21 / 21건')).toBeInTheDocument()
  })
})
