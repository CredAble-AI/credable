import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { normalizeEvidenceSubmissionError } from '../api/evidenceSubmissionClient'
import { evidenceSubmissionProvider } from '../hooks/useEvidenceSubmissionState'
import type { ApiError } from '../types/api'
import type { EvidenceConsentScope } from '../types/evidenceConsent'
import type { EvidenceSubmissionOption, EvidenceSubmissionState } from '../types/evidenceSubmission'
import EvidenceConsentPanel from './EvidenceConsentPanel'
import CustomerTechnicalDetails from './CustomerTechnicalDetails'
import EvidenceQualityPanel from './EvidenceQualityPanel'
import { withMinimumDuration } from '../utils/pacedRequest'

interface EvidenceFileSubmissionProps {
  sessionId: string
  selectionId: string
  evidenceType: string
  /** Both come from the server's selection; the screen never restates the rule. */
  displayName: string
  consentScope: EvidenceConsentScope | null
}

type Phase = 'loading' | 'uploading' | 'connecting' | 'idle'

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

function EvidenceFileSubmission({ sessionId, selectionId, evidenceType, displayName, consentScope }: EvidenceFileSubmissionProps) {
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
      const response = await withMinimumDuration(evidenceSubmissionProvider.upload(sessionId, selectionId, file, controller.signal))
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

  const submitConnected = async () => {
    if (!option || option.submissionRequirement.status !== 'READY' || phase !== 'idle') return
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase('connecting'); setError(null)
    try {
      const response = await withMinimumDuration(evidenceSubmissionProvider.submitConnected(sessionId, selectionId, controller.signal))
      if (response.sessionId !== sessionId || response.submission?.selectionId !== selectionId || response.submission.evidenceType !== evidenceType) {
        throw { code: 'EVIDENCE_SUBMISSION_CONTEXT_MISMATCH', message: '현재 Evidence 선택과 일치하는 연결 자료를 확인할 수 없습니다.', retryable: true } satisfies ApiError
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
  const requirement = option.submissionRequirement
  const isConnectedEvidence = option.collectionMode === 'DEMO_CONNECTION'

  return <section className="evidence-submission" aria-labelledby="evidence-submit-title">
    <div className="evidence-submission__heading"><div><span>{isConnectedEvidence ? '연결 자료 확인' : '자료 제출'}</span><h2 id="evidence-submit-title">{isConnectedEvidence ? '요청된 연결 자료를 확인해주세요' : '요청된 추가 자료를 제출해주세요'}</h2></div></div>
    <p>{isConnectedEvidence
      ? '서버가 선택한 최소 증빙 한 건만 확인합니다. 동의한 범위의 연결 자료를 기준시점·출처·내용 일관성에 따라 검증한 뒤 보완평가에 반영합니다.'
      : '서버가 선택한 최소 증빙 한 건만 확인합니다. 제출한 파일은 형식·출처·기준시점·내용 일관성을 검증한 뒤 보완평가에 반영합니다.'}</p>

    {error && <div className="evidence-submission__error" role="alert"><strong>{error.message}</strong></div>}

    {option.collectionMode === 'DEMO_FILE_UPLOAD' && primaryFile && option.uploadPolicy && <>
      <div className="evidence-demo-step"><span>1</span><div><strong>제출 범위 동의</strong><p>서버가 선택한 최소 증빙 한 건의 이용 범위를 먼저 확인합니다.</p></div></div>
      <EvidenceConsentPanel sessionId={sessionId} selectionId={selectionId} evidenceType={evidenceType} onConsentChanged={load} />

      <div className="evidence-demo-step"><span>2</span><div><strong>요청 자료 준비</strong><p>요청된 자료의 범위와 기준 기간을 확인한 뒤 보유한 문서를 준비해주세요.</p></div></div>
      <div className="evidence-requested-file" aria-label="요청된 자료 기준">
        <div><span>제출 기준</span><strong>{displayName}</strong>{consentScope
          ? <p>위 이용 범위와 같은 <b>{consentScope.periodStart} ~ {consentScope.periodEnd}</b> 기간의 자료를 준비해주세요.</p>
          : <p>확인 기간과 정보 항목은 위 이용 범위에서 확인할 수 있습니다.</p>}<small>PDF · 최대 {formatBytes(option.uploadPolicy.maxSizeBytes)}</small></div>
      </div>

      {scenarioFiles.length > 0 && <section className="evidence-demo-library" aria-labelledby="demo-library-title">
        <div className="evidence-demo-library__heading"><span>DEMO</span><div><strong id="demo-library-title">다양한 검증 분기를 직접 확인해보세요</strong><p>정상·기준시점 오류·필수항목 누락·변조 의심 자료 중 하나를 받아 서버의 서로 다른 검증 결과를 확인할 수 있습니다.</p></div></div>
        <p className="evidence-demo-library__notice">이 자료는 제출 URL만으로 품질검증을 시연하기 위한 테스트 문서입니다. 운영 환경에서는 고객이 보유하거나 발급기관을 통해 확보한 문서를 제출합니다.</p>
        <div className="evidence-scenario-set" aria-label="품질 검증 심사용 시나리오 파일">
        {scenarioFiles.map((scenario) => {
          const scenarioDownloadPath = safeDownloadPath(scenario.downloadUrl)
          return <div className="evidence-file-card" key={scenario.demoFileId}><div>{scenario.expectedQualityStatus && <span className={`evidence-file-card__status evidence-file-card__status--${scenario.expectedQualityStatus.toLowerCase()}`}>{expectedStatusLabel[scenario.expectedQualityStatus]}</span>}<strong>{scenario.displayName}</strong><p>{scenario.description}</p><small>{scenario.fileName} · PDF · {formatBytes(scenario.sizeBytes)}</small></div>{requirement.status !== 'READY' ? <span className="button button--secondary" aria-disabled="true">동의 후 다운로드</span> : scenarioDownloadPath ? <a aria-label={`${scenario.displayName} 다운로드`} className="button button--secondary" href={scenarioDownloadPath} download={scenario.fileName}>다운로드</a> : <span className="evidence-file-card__invalid" role="alert">다운로드 주소를 확인할 수 없습니다.</span>}</div>
        })}
        </div>
      </section>}

      <div className="evidence-demo-step"><span>3</span><div><strong>요청한 자료 준비 완료 후 업로드</strong><p>보유하거나 발급받은 PDF를 선택해 제출해주세요. 시연에서는 위 테스트 자료 중 하나를 사용할 수 있습니다.</p></div></div>

      {requirement.status === 'UNAVAILABLE' && <div className="evidence-submission__notice evidence-submission__notice--blocked"><strong>현재 파일을 제출할 수 없습니다</strong><p>자료 제출 가능 상태를 확인해주세요.</p></div>}

      {requirement.status === 'READY' && !submission && <div className="evidence-upload-control"><label htmlFor={inputId}>제출할 PDF 선택</label><input id={inputId} type="file" accept={option.uploadPolicy.allowedContentTypes.join(',')} onChange={(event) => selectFile(event.target.files?.[0] ?? null)} disabled={phase === 'uploading'} /><small>PDF · 최대 {formatBytes(option.uploadPolicy.maxSizeBytes)}</small>{file && <p>선택 파일: <strong>{file.name}</strong> · {formatBytes(file.size)}</p>}{fileError && <p className="evidence-upload-control__error" role="alert">{fileError}</p>}<button className="button button--primary" type="button" onClick={() => void upload()} disabled={!file || phase === 'uploading'}>{phase === 'uploading' ? '파일을 확인하는 중…' : '선택한 파일 제출'}</button></div>}
    </>}

    {option.collectionMode === 'DEMO_CONNECTION' && <>
      <div className="evidence-demo-step"><span>1</span><div><strong>연결 정보 이용 범위 확인</strong><p>외부 정산·입금 정보를 보완평가에 사용할 범위를 확인합니다.</p></div></div>
      <EvidenceConsentPanel sessionId={sessionId} selectionId={selectionId} evidenceType={evidenceType} onConsentChanged={load} />
      <div className="evidence-demo-step"><span>2</span><div><strong>연결 자료 확인</strong><p>동의한 범위의 최신 자료를 불러와 기준시점·출처·내용 일관성을 확인할 스냅샷을 만듭니다.</p></div></div>
      {requirement.status === 'CONSENT_REQUIRED' && <div className="evidence-submission__notice"><strong>이용 범위 동의가 필요합니다</strong><p>동의를 반영한 뒤 연결 자료 확인을 시작할 수 있습니다.</p></div>}
      {requirement.status === 'READY' && !submission && <div className="evidence-connection-action"><div><strong>연결된 원천 자료를 직접 확인하므로 PDF가 필요하지 않습니다</strong><p>동의한 범위의 정산·입금 정보를 연결 서비스에서 불러와 기준시점·출처·내용 일관성을 검증합니다. 같은 내용을 PDF로 다시 제출하지 않아도 됩니다.</p></div><button className="button button--primary" type="button" onClick={() => void submitConnected()} disabled={phase === 'connecting'}>{phase === 'connecting' ? '연결 자료를 확인하는 중…' : '연결 자료 확인 시작'}</button></div>}
    </>}
    {option.collectionMode === 'UNAVAILABLE' && <div className="evidence-submission__notice evidence-submission__notice--blocked"><strong>현재 이용할 수 없는 제출 방식입니다</strong><p>다른 확인 방법이 제공되는지 확인해주세요.</p></div>}

    {submission && <><div className="evidence-submission__complete" role="status"><span aria-hidden="true">✓</span><div><strong>{isConnectedEvidence ? '연결 자료를 확인했습니다' : '파일 제출을 완료했습니다'}</strong><p>이제 서버가 자료 품질을 확인하고 보완평가와 결과 비교를 순서대로 진행합니다.</p><small>{submission.uploadedFile?.fileName ?? '연결 자료 스냅샷'}</small></div></div><CustomerTechnicalDetails><dl><div><dt>제출 상태</dt><dd><code>{submission.status}</code></dd></div><div><dt>제출 ID</dt><dd><code>{submission.submissionId}</code></dd></div><div><dt>제출 스냅샷 해시</dt><dd><code>{submission.submissionSnapshotHash}</code></dd></div><div><dt>수집 방식</dt><dd><code>{submission.submissionMode}</code></dd></div></dl></CustomerTechnicalDetails></>}
    <CustomerTechnicalDetails><dl><div><dt>제출 가능 상태</dt><dd><code>{requirement.status}</code></dd></div><div><dt>수집 방식</dt><dd><code>{option.collectionMode}</code></dd></div>{requirement.reasonCode && <div><dt>상태 코드</dt><dd><code>{requirement.reasonCode}</code></dd></div>}{error && <><div><dt>오류 코드</dt><dd><code>{error.code}</code></dd></div>{error.requestId && <div><dt>요청 ID</dt><dd><code>{error.requestId}</code></dd></div>}</>}</dl></CustomerTechnicalDetails>
    {submission && <EvidenceQualityPanel sessionId={sessionId} submission={submission} />}
  </section>
}

export default EvidenceFileSubmission
