import { describe, expect, it, vi } from 'vitest'
import type { EvidenceSubmissionOption, EvidenceSubmissionResponse } from '../types/evidenceSubmission'
import { liveEvidenceSubmissionProvider } from './evidenceSubmissionClient'

const option = { sessionId: 'ses_demo', selectionId: 'evs_demo' } as EvidenceSubmissionOption
const latest = { sessionId: 'ses_demo', submission: null } satisfies EvidenceSubmissionResponse

describe('liveEvidenceSubmissionProvider', () => {
  it('uses the server submission-option and latest endpoints', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => option })
      .mockResolvedValueOnce({ ok: true, json: async () => latest })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveEvidenceSubmissionProvider.getOption('ses_demo', 'evs_demo', 'RECENT_REVENUE', signal)
    await liveEvidenceSubmissionProvider.getLatest('ses_demo', signal)

    expect(fetchMock).toHaveBeenNthCalledWith(1, '/v1/sessions/ses_demo/evidence/selections/evs_demo/submission-option', { signal })
    expect(fetchMock).toHaveBeenNthCalledWith(2, '/v1/sessions/ses_demo/evidence/submissions/latest', { signal })
  })

  it('uploads the server selection id and file as multipart data', async () => {
    const response = { sessionId: 'ses_demo', submission: null } satisfies EvidenceSubmissionResponse
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['%PDF-demo'], 'demo.pdf', { type: 'application/pdf' })
    const signal = new AbortController().signal

    await liveEvidenceSubmissionProvider.upload('ses_demo', 'evs_demo', file, signal)

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(fetchMock.mock.calls[0][0]).toBe('/v1/sessions/ses_demo/evidence/submissions/upload')
    expect(init.method).toBe('POST')
    expect(init.signal).toBe(signal)
    expect(init.headers).toBeUndefined()
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.body as FormData).get('selectionId')).toBe('evs_demo')
    expect((init.body as FormData).get('file')).toBe(file)
  })

  it('submits a connected-data snapshot through the server endpoint', async () => {
    const response = { sessionId: 'ses_demo', submission: null } satisfies EvidenceSubmissionResponse
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
    const signal = new AbortController().signal

    await liveEvidenceSubmissionProvider.submitConnected('ses_demo', 'evs_demo', signal)

    expect(fetchMock).toHaveBeenCalledWith('/v1/sessions/ses_demo/evidence/submissions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selectionId: 'evs_demo', submissionMode: 'DEMO_FIXTURE_REFERENCE' }),
      signal,
    })
  })
})
