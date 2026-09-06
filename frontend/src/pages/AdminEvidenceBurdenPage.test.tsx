import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { adminEvidenceBurdenProvider } from '../hooks/useAdminEvidenceBurdenState'
import type { AdminEvidenceBurdenResponse } from '../types/adminEvidenceBurden'
import AdminEvidenceBurdenPage from './AdminEvidenceBurdenPage'

vi.mock('../hooks/useAdminEvidenceBurdenState', () => ({ adminEvidenceBurdenProvider: { get: vi.fn() } }))

const result: AdminEvidenceBurdenResponse = {
  sessionId: 'ses_demo', asOf: '2026-09-06T02:00:00Z', evidenceRequestCount: 2, repeatedRequestCount: 1, availableRequestCount: 0, requestableRequestCount: 1, consentRequiredRequestCount: 1, unavailableRequestCount: 0, submissionCount: 1, pendingSubmissionCount: 1, acceptedCount: 1, rejectedCount: 0, reviewRequiredCount: 0, unverifiedSubmissionCount: 0, failedQualityDimensionCount: 0, supplementalAssessmentCount: 1, resolutionCount: 1, latestResolutionStatus: 'MORE_EVIDENCE_REQUIRED', collectionStopped: false, maxRequestIteration: 2, measurementVersion: 'evidence-burden-metrics-v1', policyThresholdApplied: false, demoOnly: true,
  evidenceTypes: [{ evidenceType: 'RECENT_REVENUE_SUMMARY', sourceType: 'CUSTOMER_SUBMITTED', requestCount: 2, submissionCount: 1, acceptedCount: 1, rejectedCount: 0, reviewRequiredCount: 0, firstRequestedAt: '2026-09-06T01:00:00Z', lastRequestedAt: '2026-09-06T01:30:00Z' }],
}
const renderPage = () => render(<MemoryRouter initialEntries={['/admin/sessions/ses_demo/evidence-burden']}><Routes><Route path="/admin/sessions/:sessionId/evidence-burden" element={<AdminEvidenceBurdenPage />} /></Routes></MemoryRouter>)

describe('AdminEvidenceBurdenPage', () => {
  beforeEach(() => { vi.mocked(adminEvidenceBurdenProvider.get).mockReset().mockResolvedValue(result) })

  it('loads metrics without an administrator credential', async () => {
    renderPage()

    await waitFor(() => expect(adminEvidenceBurdenProvider.get).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal)))
    expect(screen.getByText(/합성 Demo 데이터 전용 화면/)).toBeInTheDocument()
  })

  it('shows policy-neutral server metrics', async () => {
    renderPage()

    await waitFor(() => expect(adminEvidenceBurdenProvider.get).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal)))
    expect(await screen.findByText('정책 임계치가 적용되지 않은 사실 지표입니다')).toBeInTheDocument()
    const requests = screen.getByRole('heading', { name: '요청 현황' }).closest('section') as HTMLElement
    expect(within(requests).getByText('전체 요청').parentElement).toHaveTextContent('2건')
    expect(screen.getByRole('heading', { name: 'RECENT_REVENUE_SUMMARY' })).toBeInTheDocument()
    expect(screen.getByText('추가 Evidence 필요')).toBeInTheDocument()
  })

  it('shows a neutral empty breakdown when no evidence was requested', async () => {
    vi.mocked(adminEvidenceBurdenProvider.get).mockResolvedValue({ ...result, evidenceRequestCount: 0, repeatedRequestCount: 0, requestableRequestCount: 0, consentRequiredRequestCount: 0, submissionCount: 0, pendingSubmissionCount: 0, acceptedCount: 0, supplementalAssessmentCount: 0, resolutionCount: 0, latestResolutionStatus: null, collectionStopped: null, maxRequestIteration: 0, evidenceTypes: [] })
    renderPage()

    expect(await screen.findByText('기록된 Evidence 요청이 없습니다.')).toBeInTheDocument()
    expect(screen.getByText('수집 결정 전')).toBeInTheDocument()
  })

  it('rejects a response for another session', async () => {
    vi.mocked(adminEvidenceBurdenProvider.get).mockResolvedValue({ ...result, sessionId: 'ses_other' })
    renderPage()

    expect(await screen.findByRole('alert')).toHaveTextContent('요청한 세션의 정책 중립적 Evidence 부담 지표를 확인할 수 없습니다.')
  })
})
