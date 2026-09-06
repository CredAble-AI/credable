import type { AdminAuditProvider } from '../api/adminAuditClient'
import type { SessionAuditEvent } from '../types/adminAudit'

const events: SessionAuditEvent[] = [
  { eventId: 'aud_demo_review_started', sessionId: 'ses_demo_sole', requestId: 'req_demo_review_started', stage: 'UNDERWRITER_REVIEW_STARTED', timestamp: '2026-09-06T02:10:00Z', actor: 'UNDERWRITER', inputVersion: 'underwriter-review-input-v1', inputSnapshotHash: 'a'.repeat(64), outputSummary: { reviewId: 'uwr_demo_assessment', status: 'IN_REVIEW' }, dataVersion: 'demo-v1', modelVersion: null, policyVersion: 'assessment-review-request-policy-v1' },
  { eventId: 'aud_demo_review_requested', sessionId: 'ses_demo_sole', requestId: 'req_demo_review_requested', stage: 'ASSESSMENT_REVIEW_REQUESTED', timestamp: '2026-09-06T02:00:00Z', actor: 'CUSTOMER', inputVersion: 'assessment-review-request-input-v1', inputSnapshotHash: 'b'.repeat(64), outputSummary: { targetType: 'SUPPLEMENTAL_ASSESSMENT', status: 'PENDING' }, dataVersion: 'demo-v1', modelVersion: 'demo-model-v1', policyVersion: 'assessment-review-request-policy-v1' },
  { eventId: 'aud_demo_session', sessionId: 'ses_demo_sole', requestId: 'req_demo_session', stage: 'SESSION_CREATED', timestamp: '2026-09-06T01:00:00Z', actor: 'CUSTOMER', inputVersion: 'session-create-input-v1', inputSnapshotHash: 'c'.repeat(64), outputSummary: { businessBorrowerType: 'SOLE_PROPRIETOR' }, dataVersion: 'demo-v1', modelVersion: null, policyVersion: null },
]

export const mockAdminAuditProvider: AdminAuditProvider = {
  async list(_apiKey, sessionId, limit, cursor, signal) {
    if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
    const matching = events.filter((event) => event.sessionId === sessionId)
    const offset = cursor ? Number(cursor) : 0
    const page = matching.slice(offset, offset + limit)
    const nextOffset = offset + page.length
    return { sessionId, demoOnly: true, events: page, nextCursor: nextOffset < matching.length ? String(nextOffset) : null }
  },
}
