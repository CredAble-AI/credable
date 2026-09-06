import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { assessmentReviewProvider } from '../hooks/useAssessmentReviewState'
import type { AssessmentReviewRequestResponse } from '../types/assessmentReview'
import AssessmentReviewPanel from './AssessmentReviewPanel'

vi.mock('../hooks/useAssessmentReviewState', () => ({ assessmentReviewProvider: { get: vi.fn(), request: vi.fn() } }))

const empty: AssessmentReviewRequestResponse = { sessionId: 'ses_demo', reviewRequest: null, underwriterReviewId: null, processing: null }
const pending: AssessmentReviewRequestResponse = {
  sessionId: 'ses_demo',
  reviewRequest: {
    reviewRequestId: 'arr_demo', targetType: 'SUPPLEMENTAL_ASSESSMENT', targetAssessmentId: 'sam_demo', reasonCode: 'CUSTOMER_REQUESTED_ASSESSMENT_REVIEW', requestedAt: '2026-09-06T06:00:00+09:00', requestSnapshotHash: 'a'.repeat(64), dataVersion: 'demo-v1', modelVersion: 'demo-supplemental-v1', requestPolicyVersion: 'assessment-review-request-policy-v1', demoOnly: true,
  },
  underwriterReviewId: 'uwr_demo',
  processing: { status: 'PENDING', resultCode: null, startedAt: null, completedAt: null },
}

describe('AssessmentReviewPanel', () => {
  const renderPanel = () => render(<MemoryRouter><AssessmentReviewPanel sessionId="ses_demo" /></MemoryRouter>)

  beforeEach(() => {
    vi.mocked(assessmentReviewProvider.get).mockReset().mockResolvedValue(empty)
    vi.mocked(assessmentReviewProvider.request).mockReset().mockResolvedValue(pending)
  })

  it('recovers state with GET without automatically creating a review request', async () => {
    renderPanel()

    expect(await screen.findByRole('button', { name: '평가 결과 재확인 요청' })).toBeInTheDocument()
    expect(assessmentReviewProvider.get).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal))
    expect(assessmentReviewProvider.request).not.toHaveBeenCalled()
    expect(screen.queryByRole('complementary', { name: 'Demo 화면 전환' })).not.toBeInTheDocument()
  })

  it('submits an explicit request and displays the server-selected assessment target', async () => {
    renderPanel()

    fireEvent.click(await screen.findByRole('button', { name: '평가 결과 재확인 요청' }))

    await waitFor(() => expect(assessmentReviewProvider.request).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '평가 결과 재확인 요청이 접수됐습니다' })).toBeInTheDocument()
    expect(screen.getByText('보완평가')).toBeInTheDocument()
    expect(screen.getByText('sam_demo')).toBeInTheDocument()
    expect(screen.getByText('PENDING')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '심사역 검토 화면 보기 (Demo)' })).toHaveAttribute('href', '/admin/reviews/uwr_demo')
    expect(screen.getByRole('complementary', { name: 'Demo 화면 전환' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '심사역 검토로 전환' })).toHaveAttribute('href', '/admin/reviews/uwr_demo')
    expect(screen.getByText(/실제 운영 환경에서는 권한이 분리된 별도 심사역 시스템/)).toBeInTheDocument()
  })

  it('shows a completed processing result code without reinterpreting it', async () => {
    vi.mocked(assessmentReviewProvider.get).mockResolvedValue({
      ...pending,
      processing: { status: 'COMPLETED', resultCode: 'ADDITIONAL_INFORMATION_REQUIRED', startedAt: '2026-09-06T06:10:00+09:00', completedAt: '2026-09-06T06:20:00+09:00' },
    })
    renderPanel()

    expect(await screen.findByRole('heading', { name: '처리 결과가 기록되었습니다' })).toBeInTheDocument()
    expect(screen.getByText('ADDITIONAL_INFORMATION_REQUIRED')).toBeInTheDocument()
  })

  it('rejects a response from another session', async () => {
    vi.mocked(assessmentReviewProvider.get).mockResolvedValue({ ...pending, sessionId: 'ses_other' })
    renderPanel()

    expect(await screen.findByRole('alert')).toHaveTextContent('현재 세션의 평가 재확인 요청을 확인할 수 없습니다.')
    expect(screen.getByRole('button', { name: '요청 상태 다시 확인' })).toBeInTheDocument()
  })

  it('rejects a review response without its linked underwriter review id', async () => {
    vi.mocked(assessmentReviewProvider.get).mockResolvedValue({ ...pending, underwriterReviewId: null })
    renderPanel()

    expect(await screen.findByRole('alert')).toHaveTextContent('현재 요청과 연결된 심사역 검토 화면을 확인할 수 없습니다.')
  })
})
