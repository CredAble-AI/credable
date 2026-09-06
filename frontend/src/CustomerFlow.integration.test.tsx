import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { evidenceSubmissionProvider } from './hooks/useEvidenceSubmissionState'
import type { EvidenceSubmissionOption, EvidenceSubmissionResponse } from './types/evidenceSubmission'

const submissionOption = (
  sessionId: string,
  selectionId: string,
  evidenceType: string,
  status: 'CONSENT_REQUIRED' | 'READY',
): EvidenceSubmissionOption => ({
  sessionId,
  selectionId,
  evidenceType,
  collectionMode: 'DEMO_FILE_UPLOAD',
  submissionRequirement: {
    status,
    reasonCode: status === 'READY' ? null : 'EVIDENCE_CONSENT_REQUIRED',
    consentSourceType: 'CUSTOMER_SUBMITTED',
  },
  demoFile: {
    demoFileId: 'file_customer_flow',
    displayName: '최근 매출·입금 요약서',
    description: '고객 흐름 통합 테스트용 합성 Demo 매출 증빙',
    fileName: 'recent-revenue-demo.pdf',
    contentType: 'application/pdf',
    sizeBytes: 4096,
    downloadUrl: `/v1/sessions/${sessionId}/evidence/selections/${selectionId}/demo-file/download`,
  },
  uploadPolicy: {
    allowedContentTypes: ['application/pdf'],
    allowedExtensions: ['.pdf'],
    maxSizeBytes: 5 * 1024 * 1024,
  },
  demoOnly: true,
})

const submittedEvidence = (
  sessionId: string,
  selectionId: string,
  evidenceType: string,
  file: File,
): EvidenceSubmissionResponse => ({
  sessionId,
  submission: {
    submissionId: `sub_flow_${sessionId}`,
    selectionId,
    evidenceType,
    sourceType: 'CUSTOMER_SUBMITTED',
    submissionMode: 'DEMO_FILE_UPLOAD',
    status: 'RECEIVED',
    submittedAt: '2026-09-06T10:00:00+09:00',
    observedAt: '2026-08-31T23:59:59+09:00',
    submissionSnapshotHash: 'a'.repeat(64),
    dataVersion: 'customer-flow-demo-v1',
    uploadedFile: {
      demoFileId: 'file_customer_flow',
      fileName: file.name,
      contentType: 'application/pdf',
      sizeBytes: file.size,
      sha256: 'b'.repeat(64),
    },
    evidenceConsentId: `evc_flow_${selectionId}`,
    consentScopeVersion: 'demo-recent-revenue-consent-v1',
    demoOnly: true,
  },
})

describe('customer journey integration', () => {
  beforeEach(() => {
    localStorage.clear()
    let optionRequestCount = 0
    vi.spyOn(evidenceSubmissionProvider, 'getOption').mockImplementation(async (sessionId, selectionId, evidenceType, signal) => {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
      optionRequestCount += 1
      return submissionOption(sessionId, selectionId, evidenceType, optionRequestCount === 1 ? 'CONSENT_REQUIRED' : 'READY')
    })
    vi.spyOn(evidenceSubmissionProvider, 'getLatest').mockImplementation(async (sessionId, signal) => {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
      return { sessionId, submission: null }
    })
    vi.spyOn(evidenceSubmissionProvider, 'upload').mockImplementation(async (sessionId, selectionId, file, signal) => {
      if (signal.aborted) throw new DOMException('Aborted', 'AbortError')
      return submittedEvidence(sessionId, selectionId, 'CUSTOMER_SUBMITTED_RECENT_REVENUE_SUMMARY', file)
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
  })

  it('continues from borrower selection through verified evidence and product handoff', async () => {
    render(<MemoryRouter initialEntries={['/start']}><App /></MemoryRouter>)

    fireEvent.click(await screen.findByRole('radio', { name: /개인사업자/ }))
    fireEvent.click(screen.getByRole('button', { name: '계속하기' }))

    expect(await screen.findByRole('heading', { level: 1, name: '연결할 데이터의 이용 범위를 확인해주세요' })).toBeInTheDocument()
    for (const sourceName of ['은행 내부 데이터', '신용정보', '고객 제출 데이터']) {
      const checkbox = await screen.findByRole('checkbox', { name: new RegExp(sourceName) })
      fireEvent.click(checkbox)
      await waitFor(() => expect(checkbox).toBeChecked())
    }
    fireEvent.click(screen.getByRole('button', { name: '데이터 연결로 이동' }))

    expect(await screen.findByRole('heading', { level: 1, name: '기준평가에 사용할 데이터 출처를 확인합니다' })).toBeInTheDocument()
    const loadBaselineData = await screen.findByRole('button', { name: '기준평가 데이터 불러오기' })
    await waitFor(() => expect(loadBaselineData).toBeEnabled())
    fireEvent.click(loadBaselineData)
    fireEvent.click(await screen.findByRole('button', { name: '기존 평가 결과 확인' }, { timeout: 10_000 }))

    fireEvent.click(await screen.findByRole('button', { name: '기존 평가 결과 불러오기' }, { timeout: 3_000 }))
    fireEvent.click(await screen.findByRole('button', { name: '다음 단계 확인' }))
    fireEvent.click(await screen.findByRole('button', { name: '평가 결과 설명 보기' }))
    expect(await screen.findByRole('heading', { level: 3, name: '다음으로 확인할 내용' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('link', { name: '필요한 자료 확인' }))

    fireEvent.click(await screen.findByRole('button', { name: '필요한 자료 확인' }))
    expect(await screen.findByRole('heading', { level: 2, name: '최근 매출·입금 요약' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '이 범위에 동의' }))

    const download = await screen.findByRole('link', { name: '요청 자료 다운로드' })
    expect(download).toHaveAttribute('download', 'recent-revenue-demo.pdf')
    expect(download.getAttribute('href')).toMatch(/^\/v1\/sessions\/[^/]+\/evidence\/selections\/[^/]+\/demo-file\/download$/)

    const file = new File(['%PDF-1.7 customer flow'], 'recent-revenue-demo.pdf', { type: 'application/pdf' })
    fireEvent.change(screen.getByLabelText('제출할 PDF 선택'), { target: { files: [file] } })
    fireEvent.click(screen.getByRole('button', { name: '선택한 파일 제출' }))
    expect(await screen.findByText('파일 제출을 완료했습니다')).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: '자료 품질 확인' }))
    expect(await screen.findByRole('heading', { level: 3, name: '자료 확인을 완료했습니다' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '보완평가 실행' }))
    expect(await screen.findByRole('heading', { level: 3, name: '보완평가를 완료했습니다' })).toBeInTheDocument()

    fireEvent.click(await screen.findByRole('button', { name: '평가 결과 재확인 요청' }))
    expect(await screen.findByRole('heading', { level: 3, name: '평가 결과 재확인 요청이 접수됐습니다' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '평가 전후 비교' }))
    expect(await screen.findByRole('heading', { level: 4, name: '가능한 결과 범위가 줄었습니다' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '다음 단계 확인' }))

    expect(await screen.findByRole('heading', { level: 5, name: '추가 자료 확인을 마쳤습니다' })).toBeInTheDocument()
    fireEvent.click(await screen.findByRole('button', { name: '평가 결과 설명 보기' }))
    expect(await screen.findByRole('heading', { level: 3, name: '추가 증빙 수집이 종료됐습니다' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '자사 상품 조건 확인' }))
    expect(await screen.findByRole('heading', { level: 1, name: '자사 대출상품 조건을 비교합니다' })).toBeInTheDocument()
    const productLink = await screen.findByRole('link', { name: '사업 운영자금 플러스 상세 보기' }, { timeout: 3_000 })
    expect(screen.getAllByRole('article')).toHaveLength(4)

    fireEvent.click(productLink)
    expect(await screen.findByRole('heading', { level: 1, name: '사업 운영자금 플러스' }, { timeout: 3_000 })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '신청 연결 안내 확인' }))
    expect(await screen.findByRole('heading', { level: 1, name: '사업 운영자금 플러스' }, { timeout: 3_000 })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '계속하기' })).toBeDisabled()
    expect(screen.getByText('Demo 환경에서는 실제 은행 신청 연결을 제공하지 않습니다.')).toBeInTheDocument()
  }, 30_000)
})
