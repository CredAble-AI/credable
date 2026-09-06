import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { evidenceSubmissionProvider } from '../hooks/useEvidenceSubmissionState'
import type { EvidenceSubmissionOption, EvidenceSubmissionResponse } from '../types/evidenceSubmission'
import type { EvidenceConsentScope } from '../types/evidenceConsent'
import EvidenceFileSubmission from './EvidenceFileSubmission'

vi.mock('../hooks/useEvidenceSubmissionState', () => ({
  evidenceSubmissionProvider: { getOption: vi.fn(), getLatest: vi.fn(), upload: vi.fn(), submitConnected: vi.fn() },
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

const connectedOption = (): EvidenceSubmissionOption => ({
  sessionId: 'ses_demo', selectionId: 'evs_demo', evidenceType: 'RECENT_REVENUE', collectionMode: 'DEMO_CONNECTION', demoOnly: true,
  submissionRequirement: { status: 'READY', reasonCode: null, consentSourceType: 'EXTERNAL_CONNECTED' },
  demoFile: null,
  uploadPolicy: null,
})

const connectedSubmission: EvidenceSubmissionResponse = {
  sessionId: 'ses_demo',
  submission: { ...submitted.submission!, sourceType: 'EXTERNAL_CONNECTED', submissionMode: 'DEMO_FIXTURE_REFERENCE', uploadedFile: null, evidenceConsentId: null, consentScopeVersion: null },
}

const consentScope = {
  scopeVersion: 'demo-recent-revenue-consent-v1',
  purposeCode: 'SUPPLEMENTAL_CREDIT_ASSESSMENT',
  purposeDescription: '기존 평가의 불확실성을 확인하기 위한 보완평가에 사용',
  dataCategories: ['BUSINESS_IDENTITY', 'MONTHLY_SALES', 'PERIOD_TOTALS'],
  periodStart: '2026-03-01',
  periodEnd: '2026-08-31',
  required: true,
} satisfies EvidenceConsentScope

const renderComponent = () => render(<MemoryRouter><EvidenceFileSubmission sessionId="ses_demo" selectionId="evs_demo" evidenceType="RECENT_REVENUE" displayName="최근 매출·입금 요약" consentScope={consentScope} /></MemoryRouter>)

describe('EvidenceFileSubmission', () => {
  beforeEach(() => {
    vi.mocked(evidenceSubmissionProvider.getOption).mockReset().mockResolvedValue(option())
    vi.mocked(evidenceSubmissionProvider.getLatest).mockReset().mockResolvedValue({ sessionId: 'ses_demo', submission: null })
    vi.mocked(evidenceSubmissionProvider.upload).mockReset().mockResolvedValue(submitted)
    vi.mocked(evidenceSubmissionProvider.submitConnected).mockReset().mockResolvedValue(connectedSubmission)
  })

  it('downloads the server file and uploads the selected PDF', async () => {
    renderComponent()

    const download = await screen.findByRole('link', { name: '최근 매출·입금 요약서 다운로드' })
    expect(download).toHaveAttribute('href', '/v1/sessions/ses_demo/evidence/selections/evs_demo/demo-file/download')
    expect(download).toHaveAttribute('download', '최근_매출_입금_요약서_DEMO.pdf')

    const file = new File(['%PDF-demo'], '최근_매출_입금_요약서_DEMO.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText('제출할 PDF 선택'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: '선택한 파일 제출' }))

    await waitFor(() => expect(evidenceSubmissionProvider.upload).toHaveBeenCalledWith('ses_demo', 'evs_demo', file, expect.any(AbortSignal)))
    expect(await screen.findByText('파일 제출을 완료했습니다')).toBeInTheDocument()
  })

  it('shows each server-provided quality scenario without calculating its result', async () => {
    const scenarioOption = option()
    scenarioOption.demoFiles = [
      { ...scenarioOption.demoFile!, scenarioCode: 'VALID_ORIGINAL', expectedQualityStatus: 'ACCEPTED' },
      { ...scenarioOption.demoFile!, demoFileId: 'file_stale', displayName: '기준시점 이후 자료', fileName: '기준시점불일치.pdf', downloadUrl: '/v1/demo-files/file_stale/download', scenarioCode: 'POINT_IN_TIME_INVALID', expectedQualityStatus: 'REJECTED' },
      { ...scenarioOption.demoFile!, demoFileId: 'file_changed', displayName: '변조 의심 자료', fileName: '변조의심.pdf', downloadUrl: '/v1/demo-files/file_changed/download', scenarioCode: 'HASH_MISMATCH', expectedQualityStatus: 'REVIEW_REQUIRED' },
    ]
    vi.mocked(evidenceSubmissionProvider.getOption).mockResolvedValue(scenarioOption)

    renderComponent()

    expect(await screen.findByRole('link', { name: '최근 매출·입금 요약서 다운로드' })).toHaveAttribute('href', '/v1/sessions/ses_demo/evidence/selections/evs_demo/demo-file/download')
    expect(screen.getByText('다양한 검증 분기를 직접 확인해보세요')).toBeInTheDocument()
    expect(screen.getByText('자동평가 제외 시나리오')).toBeInTheDocument()
    expect(screen.getByText('심사역 확인 시나리오')).toBeInTheDocument()
    expect(screen.getAllByRole('link', { name: /다운로드/ })).toHaveLength(3)
  })

  it('keeps upload blocked until the server reports the required consent', async () => {
    vi.mocked(evidenceSubmissionProvider.getOption).mockResolvedValue(option('CONSENT_REQUIRED'))
    renderComponent()

    expect(await screen.findByText('선택 증빙 이용 동의')).toBeInTheDocument()
    expect(screen.getByText('동의 후 다운로드')).toHaveAttribute('aria-disabled', 'true')
    expect(screen.queryByRole('link', { name: /다운로드/ })).not.toBeInTheDocument()
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

  it('starts connected-data collection and exposes the resulting quality check', async () => {
    vi.mocked(evidenceSubmissionProvider.getOption).mockResolvedValue(connectedOption())
    renderComponent()

    expect(await screen.findByText('연결된 원천 자료를 직접 확인하므로 PDF가 필요하지 않습니다')).toBeInTheDocument()
    expect(screen.getByText(/같은 내용을 PDF로 다시 제출하지 않아도 됩니다/)).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '연결 자료 확인 시작' }))

    await waitFor(() => expect(evidenceSubmissionProvider.submitConnected).toHaveBeenCalledWith('ses_demo', 'evs_demo', expect.any(AbortSignal)))
    expect(await screen.findByText('연결 자료를 확인했습니다')).toBeInTheDocument()
    expect(screen.getByText('Evidence 품질검증')).toBeInTheDocument()
    expect(screen.queryByLabelText('제출할 PDF 선택')).not.toBeInTheDocument()
  })

  it('rejects a non-PDF file before calling the backend', async () => {
    renderComponent()
    await screen.findByRole('link', { name: '최근 매출·입금 요약서 다운로드' })

    fireEvent.change(screen.getByLabelText('제출할 PDF 선택'), { target: { files: [new File(['text'], 'evidence.txt', { type: 'text/plain' })] } })

    expect(screen.getByRole('alert')).toHaveTextContent('PDF 파일만 선택할 수 있습니다.')
    expect(evidenceSubmissionProvider.upload).not.toHaveBeenCalled()
  })

  it('states the requested period and fields from the server selection', async () => {
    renderComponent()

    expect(await screen.findByText('최근 매출·입금 요약')).toBeInTheDocument()
    expect(screen.getByText('확인 기간 2026-03-01 ~ 2026-08-31')).toBeInTheDocument()
    expect(screen.getByText('확인할 정보: 사업자 식별 정보 · 월별 매출 · 대상 기간 합계')).toBeInTheDocument()
  })
})
