import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { normalizeEvidenceSubmissionError } from '../api/evidenceSubmissionClient'
import { evidenceSubmissionProvider } from '../hooks/useEvidenceSubmissionState'
import type { ApiError } from '../types/api'
import type { EvidenceSubmissionOption, EvidenceSubmissionState } from '../types/evidenceSubmission'
import EvidenceConsentPanel from './EvidenceConsentPanel'
import CustomerTechnicalDetails from './CustomerTechnicalDetails'
import EvidenceQualityPanel from './EvidenceQualityPanel'

interface EvidenceFileSubmissionProps {
  sessionId: string
  selectionId: string
  evidenceType: string
}

type Phase = 'loading' | 'uploading' | 'idle'

const formatBytes = (value: number) => value < 1024 * 1024
  ? `${Math.ceil(value / 1024)}KB`
  : `${(value / (1024 * 1024)).toFixed(1)}MB`

const safeDownloadPath = (value: string) => {
  try {
    const url = new URL(value, window.location.href)
    if (url.origin !== window.location.origin) return null
    return `${url.pathname}${url.search}${url.hash}`
  } catch {
    return null
  }
}

const expectedStatusLabel = {
  ACCEPTED: '품질 통과 시나리오',
  REJECTED: '자동평가 제외 시나리오',
  REVIEW_REQUIRED: '심사역 확인 시나리오',
} as const

function EvidenceFileSubmission({ sessionId, selectionId, evidenceType }: EvidenceFileSubmissionProps) {
  const inputId = useId()
  const [option, setOption] = useState<EvidenceSubmissionOption | null>(null)
  const [submission, setSubmission] = useState<EvidenceSubmissionState | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [fileError, setFileError] = useState('')
  const [error, setError] = useState<ApiError | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const load = useCallback(async () => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase('loading'); setError(null)
    try {
      const [nextOption, latest] = await Promise.all([
        evidenceSubmissionProvider.getOption(sessionId, selectionId, evidenceType, controller.signal),
        evidenceSubmissionProvider.getLatest(sessionId, controller.signal),
      ])
      if (nextOption.sessionId !== sessionId || nextOption.selectionId !== selectionId || nextOption.evidenceType !== evidenceType || latest.sessionId !== sessionId) {
        throw { code: 'EVIDENCE_SUBMISSION_CONTEXT_MISMATCH', message: '현재 Evidence 선택과 일치하는 제출 상태를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      }
      if (sequence === sequenceRef.current) {
        setOption(nextOption)
        setSubmission(latest.submission?.selectionId === selectionId ? latest.submission : null)
      }
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeEvidenceSubmissionError(caught))
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [evidenceType, selectionId, sessionId])

  useEffect(() => {
    queueMicrotask(() => void load())
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [load])

  const selectFile = (nextFile: File | null) => {
    setFile(null); setFileError(''); setError(null)
    if (!nextFile || !option?.uploadPolicy) return
    const extension = nextFile.name.includes('.') ? `.${nextFile.name.split('.').pop()?.toLowerCase()}` : ''
    if (!option.uploadPolicy.allowedExtensions.includes(extension) || !option.uploadPolicy.allowedContentTypes.includes(nextFile.type)) {
      setFileError('PDF 파일만 선택할 수 있습니다.')
      return
    }
    if (nextFile.size > option.uploadPolicy.maxSizeBytes) {
      setFileError(`파일 크기는 ${formatBytes(option.uploadPolicy.maxSizeBytes)} 이하여야 합니다.`)
      return
    }
    setFile(nextFile)
  }

  const upload = async () => {
    if (!file || !option || option.submissionRequirement.status !== 'READY' || phase !== 'idle') return
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase('uploading'); setError(null)
    try {
      const response = await evidenceSubmissionProvider.upload(sessionId, selectionId, file, controller.signal)
      if (response.sessionId !== sessionId || response.submission?.selectionId !== selectionId || response.submission.evidenceType !== evidenceType) {
        throw { code: 'EVIDENCE_SUBMISSION_CONTEXT_MISMATCH', message: '현재 Evidence 선택과 일치하는 제출 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      }
      if (sequence === sequenceRef.current) setSubmission(response.submission)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeEvidenceSubmissionError(caught))
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }

  if (phase === 'loading' && !option) return <section className="evidence-submission evidence-submission--loading" aria-label="추가 자료 제출 준비"><span /><span /></section>

  if (!option) return <section className="evidence-submission" aria-labelledby="evidence-submit-title"><h2 id="evidence-submit-title">추가 자료 제출</h2>{error && <div className="evidence-submission__error" role="alert"><strong>{error.message}</strong>{error.retryable && <button type="button" onClick={() => void load()}>다시 확인</button>}</div>}</section>

  const scenarioFiles = option.demoFiles?.length ? option.demoFiles : option.demoFile ? [option.demoFile] : []
  const primaryFile = option.demoFile
  const reviewerFiles = scenarioFiles.filter((scenario) => scenario.demoFileId !== primaryFile?.demoFileId)
  const primaryDownloadPath = primaryFile ? safeDownloadPath(primaryFile.downloadUrl) : null
  const requirement = option.submissionRequirement

  return <section className="evidence-submission" aria-labelledby="evidence-submit-title">
    <div className="evidence-submission__heading"><div><span>자료 제출</span><h2 id="evidence-submit-title">요청된 추가 자료를 제출해주세요</h2></div></div>
    <p>서버가 선택한 최소 증빙 한 건만 확인합니다. 제출한 파일은 형식·출처·기준시점·내용 일관성을 검증한 뒤 보완평가에 반영합니다.</p>

    {error && <div className="evidence-submission__error" role="alert"><strong>{error.message}</strong></div>}

    {option.collectionMode === 'DEMO_FILE_UPLOAD' && primaryFile && option.uploadPolicy && <>
      <div className="evidence-demo-step"><span>1</span><div><strong>제출 범위 동의</strong><p>서버가 선택한 최소 증빙 한 건의 이용 범위를 먼저 확인합니다.</p></div></div>
      <EvidenceConsentPanel sessionId={sessionId} selectionId={selectionId} evidenceType={evidenceType} onConsentChanged={load} />

      <div className="evidence-demo-step"><span>2</span><div><strong>요청 자료 준비</strong><p>제출 URL에서도 흐름을 실습할 수 있도록 요청된 정상 자료를 제공합니다.</p></div></div>
      <div className="evidence-requested-file" aria-label="요청된 정상 자료">
        <div><span>요청된 최소 증빙</span><strong>{primaryFile.displayName}</strong><p>{primaryFile.description}</p><small>{primaryFile.fileName} · PDF · {formatBytes(primaryFile.sizeBytes)}</small></div>
        {requirement.status !== 'READY'
          ? <span className="button button--secondary" aria-disabled="true">동의 후 다운로드</span>
          : primaryDownloadPath
            ? <a className="button button--secondary" href={primaryDownloadPath} download={primaryFile.fileName}>요청 자료 다운로드</a>
            : <span className="evidence-file-card__invalid" role="alert">다운로드 주소를 확인할 수 없습니다.</span>}
      </div>

      {reviewerFiles.length > 0 && <details className="evidence-reviewer-tools">
        <summary><span><strong>심사용 테스트 자료</strong><small>기준시점 오류·누락·변조 분기를 확인하려면 열어보세요.</small></span></summary>
        <p>이 영역은 제출 URL만으로 서버 품질검증 분기를 확인하기 위한 심사용 도구입니다. 운영환경에서는 고객 보유 문서 또는 기관 연결 자료를 사용합니다.</p>
        <div className="evidence-scenario-set" aria-label="품질 검증 심사용 시나리오 파일">
        {reviewerFiles.map((scenario) => {
          const scenarioDownloadPath = safeDownloadPath(scenario.downloadUrl)
          return <div className="evidence-file-card" key={scenario.demoFileId}><div>{scenario.expectedQualityStatus && <span className={`evidence-file-card__status evidence-file-card__status--${scenario.expectedQualityStatus.toLowerCase()}`}>{expectedStatusLabel[scenario.expectedQualityStatus]}</span>}<strong>{scenario.displayName}</strong><p>{scenario.description}</p><small>{scenario.fileName} · PDF · {formatBytes(scenario.sizeBytes)}</small></div>{requirement.status !== 'READY' ? <span className="button button--secondary" aria-disabled="true">동의 후 다운로드</span> : scenarioDownloadPath ? <a className="button button--secondary" href={scenarioDownloadPath} download={scenario.fileName}>테스트 자료 다운로드</a> : <span className="evidence-file-card__invalid" role="alert">다운로드 주소를 확인할 수 없습니다.</span>}</div>
        })}
        </div>
      </details>}

      <div className="evidence-demo-step"><span>3</span><div><strong>내려받은 PDF 업로드</strong><p>선택한 파일을 그대로 올려 서버 품질검증 결과를 확인합니다.</p></div></div>

      {requirement.status === 'UNAVAILABLE' && <div className="evidence-submission__notice evidence-submission__notice--blocked"><strong>현재 파일을 제출할 수 없습니다</strong><p>자료 제출 가능 상태를 확인해주세요.</p></div>}

      {requirement.status === 'READY' && !submission && <div className="evidence-upload-control"><label htmlFor={inputId}>제출할 PDF 선택</label><input id={inputId} type="file" accept={option.uploadPolicy.allowedContentTypes.join(',')} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} disabled={phase === 'uploading'} /><small>PDF · 최대 {formatBytes(option.uploadPolicy.maxSizeBytes)}</small>{file && <p>선택 파일: <strong>{file.name}</strong> · {formatBytes(file.size)}</p>}{fileError && <p className="evidence-upload-control__error" role="alert">{fileError}</p>}<button className="button button--primary" type="button" onClick={() => void upload()} disabled={!file || phase === 'uploading'}>{phase === 'uploading' ? '파일을 확인하는 중…' : '선택한 파일 제출'}</button></div>}
    </>}

    {option.collectionMode === 'DEMO_CONNECTION' && <div className="evidence-submission__notice"><strong>연결된 정보로 확인합니다</strong><p>별도의 파일을 제출하지 않아도 됩니다.</p></div>}
    {option.collectionMode === 'UNAVAILABLE' && <div className="evidence-submission__notice evidence-submission__notice--blocked"><strong>현재 이용할 수 없는 제출 방식입니다</strong><p>다른 확인 방법이 제공되는지 확인해주세요.</p></div>}

    {submission && <><div className="evidence-submission__complete" role="status"><span aria-hidden="true">✓</span><div><strong>파일 제출을 완료했습니다</strong><p>제출한 파일의 품질을 다음 단계에서 확인할 수 있습니다.</p><small>{submission.uploadedFile?.fileName ?? '제출 자료'}</small></div></div><CustomerTechnicalDetails><dl><div><dt>제출 상태</dt><dd><code>{submission.status}</code></dd></div><div><dt>제출 ID</dt><dd><code>{submission.submissionId}</code></dd></div><div><dt>파일 해시</dt><dd><code>{submission.submissionSnapshotHash}</code></dd></div><div><dt>수집 방식</dt><dd><code>{submission.submissionMode}</code></dd></div></dl></CustomerTechnicalDetails></>}
    <CustomerTechnicalDetails><dl><div><dt>제출 가능 상태</dt><dd><code>{requirement.status}</code></dd></div><div><dt>수집 방식</dt><dd><code>{option.collectionMode}</code></dd></div>{requirement.reasonCode && <div><dt>상태 코드</dt><dd><code>{requirement.reasonCode}</code></dd></div>}{error && <><div><dt>오류 코드</dt><dd><code>{error.code}</code></dd></div>{error.requestId && <div><dt>요청 ID</dt><dd><code>{error.requestId}</code></dd></div>}</>}</dl></CustomerTechnicalDetails>
    {submission && <EvidenceQualityPanel sessionId={sessionId} submission={submission} />}
  </section>
}

export default EvidenceFileSubmission
