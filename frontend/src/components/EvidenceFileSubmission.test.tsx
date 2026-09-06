import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { evidenceSubmissionProvider } from '../hooks/useEvidenceSubmissionState'
import type { EvidenceSubmissionOption, EvidenceSubmissionResponse } from '../types/evidenceSubmission'
import EvidenceFileSubmission from './EvidenceFileSubmission'

vi.mock('../hooks/useEvidenceSubmissionState', () => ({
  evidenceSubmissionProvider: { getOption: vi.fn(), getLatest: vi.fn(), upload: vi.fn() },
}))
vi.mock('./EvidenceConsentPanel', () => ({ default: () => <div>선택 증빙 이용 동의</div> }))
vi.mock('./EvidenceQualityPanel', () => ({ default: () => <div>Evidence 품질검증</div> }))

const option = (status: 'READY' | 'CONSENT_REQUIRED' = 'READY'): EvidenceSubmissionOption => ({
  sessionId: 'ses_demo', selectionId: 'evs_demo', evidenceType: 'RECENT_REVENUE', collectionMode: 'DEMO_FILE_UPLOAD', demoOnly: true,
  submissionRequirement: { status, reasonCode: status === 'READY' ? null : 'CUSTOMER_SUBMITTED_CONSENT_REQUIRED', consentSourceType: 'CUSTOMER_SUBMITTED' },
  demoFile: { demoFileId: 'file_demo', displayName: '최근 매출·입금 요약서', description: '합성 Demo 매출 증빙', fileName: '최근_매출_입금_요약서_DEMO.pdf', contentType: 'application/pdf', sizeBytes: 4096, downloadUrl: '/v1/sessions/ses_demo/evidence/selections/evs_demo/demo-file/download' },
  uploadPolicy: { allowedContentTypes: ['application/pdf'], allowedExtensions: ['.pdf'], maxSizeBytes: 5 * 1024 * 1024 },
})

const submitted: EvidenceSubmissionResponse = {
  sessionId: 'ses_demo',
  submission: { submissionId: 'sub_demo', selectionId: 'evs_demo', evidenceType: 'RECENT_REVENUE', sourceType: 'CUSTOMER_SUBMITTED', submissionMode: 'DEMO_FILE_UPLOAD', status: 'RECEIVED', submittedAt: '2026-09-06T01:00:00+09:00', observedAt: '2026-09-01T01:00:00+09:00', submissionSnapshotHash: 'a'.repeat(64), dataVersion: 'demo-v1', uploadedFile: { demoFileId: 'file_demo', fileName: '최근_매출_입금_요약서_DEMO.pdf', contentType: 'application/pdf', sizeBytes: 4096, sha256: 'b'.repeat(64) }, evidenceConsentId: 'evc_demo', consentScopeVersion: 'demo-scope-v1', demoOnly: true },
}

const renderComponent = () => render(<MemoryRouter><EvidenceFileSubmission sessionId="ses_demo" selectionId="evs_demo" evidenceType="RECENT_REVENUE" /></MemoryRouter>)

describe('EvidenceFileSubmission', () => {
  beforeEach(() => {
    vi.mocked(evidenceSubmissionProvider.getOption).mockReset().mockResolvedValue(option())
    vi.mocked(evidenceSubmissionProvider.getLatest).mockReset().mockResolvedValue({ sessionId: 'ses_demo', submission: null })
    vi.mocked(evidenceSubmissionProvider.upload).mockReset().mockResolvedValue(submitted)
  })

  it('downloads the server file and uploads the selected PDF', async () => {
    renderComponent()

    const download = await screen.findByRole('link', { name: '시연용 PDF 내려받기' })
    expect(download).toHaveAttribute('href', '/v1/sessions/ses_demo/evidence/selections/evs_demo/demo-file/download')
    expect(download).toHaveAttribute('download', '최근_매출_입금_요약서_DEMO.pdf')

    const file = new File(['%PDF-demo'], '최근_매출_입금_요약서_DEMO.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText('제출할 PDF 선택'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: '선택한 파일 제출' }))

    await waitFor(() => expect(evidenceSubmissionProvider.upload).toHaveBeenCalledWith('ses_demo', 'evs_demo', file, expect.any(AbortSignal)))
    expect(await screen.findByText('파일 제출을 완료했습니다')).toBeInTheDocument()
  })

  it('keeps upload blocked until the server reports the required consent', async () => {
    vi.mocked(evidenceSubmissionProvider.getOption).mockResolvedValue(option('CONSENT_REQUIRED'))
    renderComponent()

    expect(await screen.findByText('선택 증빙 이용 동의')).toBeInTheDocument()
    expect(screen.getByText('동의 후 다운로드')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByRole('link', { name: '시연용 PDF 내려받기' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('제출할 PDF 선택')).not.toBeInTheDocument()
    expect(evidenceSubmissionProvider.upload).not.toHaveBeenCalled()
  })

  it('restores the latest submission for the current selection', async () => {
    vi.mocked(evidenceSubmissionProvider.getLatest).mockResolvedValue(submitted)
    renderComponent()

    expect(await screen.findByText('파일 제출을 완료했습니다')).toBeInTheDocument()
    expect(screen.getByText('Evidence 품질검증')).toBeInTheDocument()
    expect(screen.queryByLabelText('제출할 PDF 선택')).not.toBeInTheDocument()
  })

  it('rejects a non-PDF file before calling the backend', async () => {
    renderComponent()
    await screen.findByRole('link', { name: '시연용 PDF 내려받기' })

    fireEvent.change(screen.getByLabelText('제출할 PDF 선택'), { target: { files: [new File(['text'], 'evidence.txt', { type: 'text/plain' })] } })

    expect(screen.getByRole('alert')).toHaveTextContent('PDF 파일만 선택할 수 있습니다.')
    expect(evidenceSubmissionProvider.upload).not.toHaveBeenCalled()
  })
})
