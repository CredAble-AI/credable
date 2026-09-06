import { describe, expect, it, vi } from 'vitest'
import type { AdminAuditEventListResponse } from '../types/adminAudit'
import { liveAdminAuditProvider } from './adminAuditClient'

const response: AdminAuditEventListResponse = { sessionId: 'ses_demo', demoOnly: true, events: [], nextCursor: 'cursor-next' }

describe('liveAdminAuditProvider', () => {
  it('encodes the session and cursor without authentication headers', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveAdminAuditProvider.list('ses/demo', 20, 'cursor/value', signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/admin/sessions/ses%2Fdemo/audit-events?limit=20&cursor=cursor%2Fvalue', { method: 'GET', signal })
  })

  it('preserves structured server errors', async () => {
    const error = { code: 'CUSTOMER_SESSION_NOT_FOUND', message: '세션을 찾을 수 없습니다.', requestId: 'req_demo', retryable: false }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 404, headers: new Headers(), json: async () => ({ error }) }))

    await expect(liveAdminAuditProvider.list('ses_missing', 20, null, new AbortController().signal)).rejects.toEqual(error)
  })
})
