import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminAuthProvider from '../components/AdminAuthProvider'
import { adminReviewProvider } from '../hooks/useAdminReviewState'
import type { AdminReviewQueueResponse } from '../types/adminReview'
import AdminReviewListPage from './AdminReviewListPage'

vi.mock('../hooks/useAdminReviewState', () => ({ adminReviewProvider: { list: vi.fn() } }))

const queue: AdminReviewQueueResponse = {
  totalCount: 2, limit: 20, offset: 0, demoOnly: true,
  items: [
    { reviewId: 'uwr_assessment', sessionId: 'ses_sole', triggerType: 'CUSTOMER_ASSESSMENT_REVIEW', triggerId: 'arr_demo', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCodes: ['CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'], requestedAt: '2026-09-06T02:00:00Z', dataVersion: 'demo-v1', policyVersion: 'assessment-review-request-policy-v1', status: 'PENDING', demoOnly: true },
    { reviewId: 'uwr_evidence', sessionId: 'ses_corp', triggerType: 'EVIDENCE_QUALITY', triggerId: 'evq_demo', evidenceType: 'RECENT_REVENUE_SUMMARY', reasonCodes: ['DEMO_FILE_HASH_MISMATCH'], requestedAt: '2026-09-06T01:00:00Z', dataVersion: 'demo-v1', policyVersion: 'demo-quality-v1', status: 'IN_REVIEW', startedAt: '2026-09-06T01:10:00Z', demoOnly: true },
  ],
}
const renderPage = () => render(<MemoryRouter><AdminAuthProvider><AdminReviewListPage /></AdminAuthProvider></MemoryRouter>)
const enterKey = () => {
  fireEvent.change(screen.getByLabelText('관리자 Demo API Key'), { target: { value: 'demo-secret' } })
  fireEvent.click(screen.getByRole('button', { name: '관리자 화면 확인' }))
}

describe('AdminReviewListPage', () => {
  beforeEach(() => { localStorage.clear(); vi.mocked(adminReviewProvider.list).mockReset().mockResolvedValue(queue) })

  it('does not request the queue before an in-memory key is provided', () => {
    renderPage()

    expect(screen.getByLabelText('관리자 Demo API Key')).toHaveAttribute('type', 'password')
    expect(adminReviewProvider.list).not.toHaveBeenCalled()
    expect(localStorage.length).toBe(0)
  })

  it('loads both trigger shapes without exposing the key in the page', async () => {
    renderPage()
    enterKey()

    await waitFor(() => expect(adminReviewProvider.list).toHaveBeenCalledWith('demo-secret', { limit: 20, offset: 0, status: null }, expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: 'uwr_assessment' })).toBeInTheDocument()
    expect(screen.getByText('보완평가')).toBeInTheDocument()
    expect(screen.getByText('RECENT_REVENUE_SUMMARY')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: '상세 확인' })[0]).toHaveAttribute('href', '/admin/reviews/uwr_assessment')
    expect(screen.queryByText('demo-secret')).not.toBeInTheDocument()
  })

  it('requests a server-filtered page and supports manual refresh', async () => {
    renderPage()
    enterKey()
    await screen.findByRole('heading', { name: 'uwr_assessment' })

    fireEvent.change(screen.getByLabelText('처리 상태'), { target: { value: 'PENDING' } })
    await waitFor(() => expect(adminReviewProvider.list).toHaveBeenLastCalledWith('demo-secret', { limit: 20, offset: 0, status: 'PENDING' }, expect.any(AbortSignal)))
    const callsBeforeRefresh = vi.mocked(adminReviewProvider.list).mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: '상태 새로고침' }))
    await waitFor(() => expect(adminReviewProvider.list).toHaveBeenCalledTimes(callsBeforeRefresh + 1))
  })

  it('returns to key input after authentication failure', async () => {
    vi.mocked(adminReviewProvider.list).mockRejectedValue({ code: 'ADMIN_AUTHENTICATION_FAILED', message: '관리자 인증에 실패했습니다.', retryable: false })
    renderPage()
    enterKey()

    expect(await screen.findByRole('alert')).toHaveTextContent('관리자 인증에 실패했습니다.')
    fireEvent.click(screen.getByRole('button', { name: '키 다시 입력' }))
    expect(screen.getByLabelText('관리자 Demo API Key')).toBeInTheDocument()
  })

  it('requests the next bounded server page', async () => {
    vi.mocked(adminReviewProvider.list).mockImplementation(async (_key, query) => ({ ...queue, totalCount: 21, offset: query.offset, items: [queue.items[query.offset === 0 ? 0 : 1]] }))
    renderPage()
    enterKey()

    fireEvent.click(await screen.findByRole('button', { name: '다음 페이지' }))

    await waitFor(() => expect(adminReviewProvider.list).toHaveBeenLastCalledWith('demo-secret', { limit: 20, offset: 20, status: null }, expect.any(AbortSignal)))
    expect(await screen.findByText('21–21 / 21건')).toBeInTheDocument()
  })

  it('rejects a blank key before calling the provider', () => {
    renderPage()
    fireEvent.change(screen.getByLabelText('관리자 Demo API Key'), { target: { value: '   ' } })
    fireEvent.click(screen.getByRole('button', { name: '관리자 화면 확인' }))

    expect(screen.getByRole('alert')).toHaveTextContent('관리자 Demo API Key를 입력해주세요.')
    expect(adminReviewProvider.list).not.toHaveBeenCalled()
  })
})
