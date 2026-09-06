import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AdminAuthProvider from '../components/AdminAuthProvider'
import { adminAuditProvider } from '../hooks/useAdminAuditState'
import type { AdminAuditEventListResponse } from '../types/adminAudit'
import AdminSessionAuditPage from './AdminSessionAuditPage'

vi.mock('../hooks/useAdminAuditState', () => ({ adminAuditProvider: { list: vi.fn() } }))

const firstPage: AdminAuditEventListResponse = {
  sessionId: 'ses_demo', demoOnly: true, nextCursor: 'cursor-next', events: [
    { eventId: 'aud_review', sessionId: 'ses_demo', requestId: 'req_review', stage: 'UNDERWRITER_REVIEW_STARTED', timestamp: '2026-09-06T02:10:00Z', actor: 'UNDERWRITER', inputVersion: 'review-input-v1', inputSnapshotHash: 'a'.repeat(64), outputSummary: { status: 'IN_REVIEW', reviewId: 'uwr_demo' }, dataVersion: 'demo-v1', modelVersion: null, policyVersion: 'review-policy-v1' },
  ],
}
const secondPage: AdminAuditEventListResponse = {
  sessionId: 'ses_demo', demoOnly: true, nextCursor: null, events: [
    { eventId: 'aud_session', sessionId: 'ses_demo', requestId: 'req_session', stage: 'SESSION_CREATED', timestamp: '2026-09-06T01:00:00Z', actor: 'CUSTOMER', inputVersion: 'session-input-v1', inputSnapshotHash: 'b'.repeat(64), outputSummary: { businessBorrowerType: 'SOLE_PROPRIETOR' }, dataVersion: 'demo-v1', modelVersion: null, policyVersion: null },
  ],
}
const renderPage = () => render(<MemoryRouter initialEntries={['/admin/sessions/ses_demo/audit']}><AdminAuthProvider><Routes><Route path="/admin/sessions/:sessionId/audit" element={<AdminSessionAuditPage />} /></Routes></AdminAuthProvider></MemoryRouter>)
const enterKey = () => {
  fireEvent.change(screen.getByLabelText('관리자 Demo API Key'), { target: { value: 'demo-secret' } })
  fireEvent.click(screen.getByRole('button', { name: '관리자 화면 확인' }))
}

describe('AdminSessionAuditPage', () => {
  beforeEach(() => {
    vi.mocked(adminAuditProvider.list).mockReset().mockImplementation(async (_key, _sessionId, _limit, cursor) => cursor ? secondPage : firstPage)
  })

  it('does not request audit data before an in-memory key is provided', () => {
    renderPage()

    expect(screen.getByLabelText('관리자 Demo API Key')).toHaveAttribute('type', 'password')
    expect(adminAuditProvider.list).not.toHaveBeenCalled()
  })

  it('renders server audit summaries and traceability without the key', async () => {
    renderPage()
    enterKey()

    await waitFor(() => expect(adminAuditProvider.list).toHaveBeenCalledWith('demo-secret', 'ses_demo', 20, null, expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '심사역 검토 시작' })).toBeInTheDocument()
    expect(screen.getByText('IN_REVIEW')).toBeInTheDocument()
    expect(screen.getByText('review-policy-v1')).toBeInTheDocument()
    expect(screen.queryByText('demo-secret')).not.toBeInTheDocument()
  })

  it('uses the opaque server cursor to move between audit pages', async () => {
    renderPage()
    enterKey()
    await screen.findByRole('heading', { name: '심사역 검토 시작' })

    fireEvent.click(screen.getByRole('button', { name: '이전 이력 보기' }))
    await waitFor(() => expect(adminAuditProvider.list).toHaveBeenLastCalledWith('demo-secret', 'ses_demo', 20, 'cursor-next', expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '세션 생성' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: '최신 이력 보기' }))
    await waitFor(() => expect(adminAuditProvider.list).toHaveBeenLastCalledWith('demo-secret', 'ses_demo', 20, null, expect.any(AbortSignal)))
  })

  it('rejects events belonging to another session', async () => {
    vi.mocked(adminAuditProvider.list).mockResolvedValue({ ...firstPage, events: [{ ...firstPage.events[0], sessionId: 'ses_other' }] })
    renderPage()
    enterKey()

    expect(await screen.findByRole('alert')).toHaveTextContent('요청한 세션과 일치하는 감사 이력을 확인할 수 없습니다.')
  })
})
