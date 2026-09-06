import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminAuthProvider from '../components/AdminAuthProvider'
import { adminReviewProvider } from '../hooks/useAdminReviewState'
import type { AdminReviewQueueItem } from '../types/adminReview'
import AdminReviewDetailPage from './AdminReviewDetailPage'

vi.mock('../hooks/useAdminReviewState', () => ({ adminReviewProvider: { get: vi.fn(), claim: vi.fn(), complete: vi.fn() } }))

const pending: AdminReviewQueueItem = { reviewId: 'uwr_assessment', sessionId: 'ses_sole', triggerType: 'CUSTOMER_ASSESSMENT_REVIEW', triggerId: 'arr_demo', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCodes: ['CUSTOMER_REQUESTED_ASSESSMENT_REVIEW'], requestedAt: '2026-09-06T02:00:00Z', dataVersion: 'demo-v1', policyVersion: 'assessment-review-request-policy-v1', status: 'PENDING', demoOnly: true }
const inReview: AdminReviewQueueItem = { ...pending, status: 'IN_REVIEW', startedAt: '2026-09-06T02:10:00Z' }
const completed: AdminReviewQueueItem = { ...inReview, status: 'COMPLETED', resultCode: 'ASSESSMENT_CONFIRMED', completedAt: '2026-09-06T02:20:00Z' }

const renderPage = () => render(<MemoryRouter initialEntries={['/admin/reviews/uwr_assessment']}><AdminAuthProvider><Routes><Route path="/admin/reviews/:reviewId" element={<AdminReviewDetailPage />} /></Routes></AdminAuthProvider></MemoryRouter>)
const enterKey = () => {
  fireEvent.change(screen.getByLabelText('관리자 Demo API Key'), { target: { value: 'demo-secret' } })
  fireEvent.click(screen.getByRole('button', { name: '관리자 화면 확인' }))
}

describe('AdminReviewDetailPage', () => {
  beforeEach(() => {
    vi.mocked(adminReviewProvider.get).mockReset().mockResolvedValue({ review: pending })
    vi.mocked(adminReviewProvider.claim).mockReset().mockResolvedValue({ review: inReview })
    vi.mocked(adminReviewProvider.complete).mockReset().mockResolvedValue({ review: completed })
  })

  it('requires an in-memory key before loading the detail', () => {
    renderPage()

    expect(screen.getByLabelText('관리자 Demo API Key')).toHaveAttribute('type', 'password')
    expect(adminReviewProvider.get).not.toHaveBeenCalled()
  })

  it('follows the server state from claim through completion', async () => {
    renderPage()
    enterKey()

    await waitFor(() => expect(adminReviewProvider.get).toHaveBeenCalledWith('demo-secret', 'uwr_assessment', expect.any(AbortSignal)))
    expect(await screen.findByText('접수 대기 상태입니다.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '세션 처리 이력 보기' })).toHaveAttribute('href', '/admin/sessions/ses_sole/audit')
    expect(screen.getByRole('link', { name: 'Evidence 부담 지표 보기' })).toHaveAttribute('href', '/admin/sessions/ses_sole/evidence-burden')
    fireEvent.click(screen.getByRole('button', { name: '검토 접수' }))

    await waitFor(() => expect(adminReviewProvider.claim).toHaveBeenCalledWith('demo-secret', 'uwr_assessment', expect.any(AbortSignal)))
    const resultSelect = await screen.findByLabelText('처리 결과')
    expect(screen.getByRole('option', { name: /평가 확인/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Evidence 확인/ })).not.toBeInTheDocument()
    fireEvent.change(resultSelect, { target: { value: 'ASSESSMENT_CONFIRMED' } })
    fireEvent.click(screen.getByRole('button', { name: '선택한 결과로 검토 완료' }))

    await waitFor(() => expect(adminReviewProvider.complete).toHaveBeenCalledWith('demo-secret', 'uwr_assessment', 'ASSESSMENT_CONFIRMED', expect.any(AbortSignal)))
    expect(await screen.findByText(/이 검토 요청은/)).toHaveTextContent('평가 확인')
    expect(screen.queryByRole('button', { name: '선택한 결과로 검토 완료' })).not.toBeInTheDocument()
  })

  it('rejects a detail response for another review id', async () => {
    vi.mocked(adminReviewProvider.get).mockResolvedValue({ review: { ...pending, reviewId: 'uwr_other' } })
    renderPage()
    enterKey()

    expect(await screen.findByRole('alert')).toHaveTextContent('요청한 검토 ID와 서버 응답이 일치하지 않습니다.')
    expect(screen.queryByText('uwr_other')).not.toBeInTheDocument()
  })
})
