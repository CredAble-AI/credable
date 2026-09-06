import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { normalizeEvidenceSubmissionError } from '../api/evidenceSubmissionClient'
import { evidenceSubmissionProvider } from '../hooks/useEvidenceSubmissionState'
import type { ApiError } from '../types/api'
import type { EvidenceSubmissionOption, EvidenceSubmissionState } from '../types/evidenceSubmission'
import EvidenceConsentPanel from './EvidenceConsentPanel'
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
      setFileError('서버가 허용한 PDF 파일만 선택할 수 있습니다.')
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

  if (phase === 'loading' && !option) return <section className="evidence-submission evidence-submission--loading" aria-label="Demo 증빙 제출 준비"><span /><span /></section>

  if (!option) return <section className="evidence-submission" aria-labelledby="evidence-submit-title"><h2 id="evidence-submit-title">Demo 증빙 제출</h2>{error && <div className="evidence-submission__error" role="alert"><strong>{error.message}</strong><small>{error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small>{error.retryable && <button type="button" onClick={() => void load()}>다시 확인</button>}</div>}</section>

  const downloadPath = option.demoFile ? safeDownloadPath(option.demoFile.downloadUrl) : null
  const requirement = option.submissionRequirement

  return <section className="evidence-submission" aria-labelledby="evidence-submit-title">
    <div className="evidence-submission__heading"><div><span>DEMO FILE SUBMISSION</span><h2 id="evidence-submit-title">시연용 증빙을 직접 제출합니다</h2></div><span className={`evidence-submission__status evidence-submission__status--${requirement.status.toLowerCase()}`}>{requirement.status}</span></div>
    <p>서버가 제공한 합성 파일을 내려받아 그대로 업로드하세요. 선택한 파일은 프론트가 아니라 백엔드에서 다시 검증합니다.</p>

    {error && <div className="evidence-submission__error" role="alert"><strong>{error.message}</strong><small>{error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div>}

    {option.collectionMode === 'DEMO_FILE_UPLOAD' && option.demoFile && option.uploadPolicy && <>
      <div className="evidence-file-card"><div><strong>{option.demoFile.displayName}</strong><p>{option.demoFile.description}</p><small>{option.demoFile.fileName} · PDF · {formatBytes(option.demoFile.sizeBytes)}</small></div>{requirement.status !== 'READY' ? <span className="button button--secondary" aria-disabled="true">동의 후 다운로드</span> : downloadPath ? <a className="button button--secondary" href={downloadPath} download={option.demoFile.fileName}>Demo 증빙 PDF 내려받기</a> : <span className="evidence-file-card__invalid" role="alert">안전한 다운로드 주소를 확인할 수 없습니다.</span>}</div>
      <EvidenceConsentPanel sessionId={sessionId} selectionId={selectionId} evidenceType={evidenceType} onConsentChanged={load} />

      {requirement.status === 'UNAVAILABLE' && <div className="evidence-submission__notice evidence-submission__notice--blocked"><strong>현재 파일을 제출할 수 없습니다</strong><p>{requirement.reasonCode ?? '서버에서 제출 가능한 상태를 확인하지 못했습니다.'}</p></div>}

      {requirement.status === 'READY' && !submission && <div className="evidence-upload-control"><label htmlFor={inputId}>제출할 PDF 선택</label><input id={inputId} type="file" accept={option.uploadPolicy.allowedContentTypes.join(',')} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} disabled={phase === 'uploading'} /><small>허용 형식 PDF · 최대 {formatBytes(option.uploadPolicy.maxSizeBytes)}</small>{file && <p>선택 파일: <strong>{file.name}</strong> · {formatBytes(file.size)}</p>}{fileError && <p className="evidence-upload-control__error" role="alert">{fileError}</p>}<button className="button button--primary" type="button" onClick={() => void upload()} disabled={!file || phase === 'uploading'}>{phase === 'uploading' ? '백엔드에서 검증하는 중…' : '선택한 파일 제출'}</button></div>}
    </>}

    {option.collectionMode === 'DEMO_CONNECTION' && <div className="evidence-submission__notice"><strong>연결 데이터로 확인하는 자료입니다</strong><p>서버가 지정한 연결 흐름을 사용하며 파일 업로드는 받지 않습니다.</p></div>}
    {option.collectionMode === 'UNAVAILABLE' && <div className="evidence-submission__notice evidence-submission__notice--blocked"><strong>현재 이용할 수 없는 제출 방식입니다</strong><p>{requirement.reasonCode ?? '백엔드에서 사용 가능한 수집 방식을 제공하지 않았습니다.'}</p></div>}

    {submission && <div className="evidence-submission__complete" role="status"><span aria-hidden="true">✓</span><div><strong>파일 제출을 확인했습니다</strong><p>백엔드가 제출 ID와 파일 메타데이터를 저장했습니다. 품질 검증 결과는 다음 단계에서 확인합니다.</p><small>{submission.uploadedFile?.fileName ?? submission.evidenceType} · {submission.status} · {submission.submissionId}</small></div></div>}
    {submission && <EvidenceQualityPanel sessionId={sessionId} submission={submission} />}
  </section>
}

export default EvidenceFileSubmission
