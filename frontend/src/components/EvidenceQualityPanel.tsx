import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { normalizeEvidenceQualityError } from '../api/evidenceQualityClient'
import { evidenceQualityProvider } from '../hooks/useEvidenceQualityState'
import type { ApiError } from '../types/api'
import type { EvidenceQualityResponse, EvidenceQualityState } from '../types/evidenceQuality'
import type { EvidenceSubmissionState } from '../types/evidenceSubmission'
import CustomerTechnicalDetails from './CustomerTechnicalDetails'
import SupplementalAssessmentPanel from './SupplementalAssessmentPanel'

interface EvidenceQualityPanelProps { sessionId: string; submission: EvidenceSubmissionState }
type Phase = 'loading' | 'checking' | 'idle'

const dimensionLabels: Record<EvidenceQualityState['checks'][number]['dimension'], string> = {
  PROVENANCE: '출처', FRESHNESS: '최신성', AUTHENTICITY: '진위', COMPLETENESS: '완전성', CONSISTENCY: '일관성', MANIPULATION_RISK: '조작 위험',
}
const statusCopy: Record<EvidenceQualityState['status'], { title: string; description: string }> = {
  ACCEPTED: { title: '자료 확인을 완료했습니다', description: '제출한 자료를 보완평가에 사용할 수 있습니다.' },
  REJECTED: { title: '이 자료는 보완평가에 사용할 수 없습니다', description: '확인하지 못한 항목을 살펴보고 다음 자료를 제출해주세요.' },
  REVIEW_REQUIRED: { title: '담당자 확인이 필요합니다', description: '이상 징후가 있어 자동 평가를 진행하지 않습니다.' },
}
const checkStatusLabels = { PASSED: '확인 완료', FAILED: '확인 필요', NOT_VERIFIED: '확인되지 않음' } as const
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function EvidenceQualityPanel({ sessionId, submission }: EvidenceQualityPanelProps) {
  const [quality, setQuality] = useState<EvidenceQualityState | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const acceptResponse = useCallback((response: EvidenceQualityResponse) => {
    if (response.sessionId !== sessionId || (response.quality && (response.quality.submissionId !== submission.submissionId || response.quality.evidenceType !== submission.evidenceType || response.quality.submissionSnapshotHash !== submission.submissionSnapshotHash))) {
      throw { code: 'EVIDENCE_QUALITY_CONTEXT_MISMATCH', message: '현재 제출한 Evidence와 일치하는 품질검증 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
    }
    return response.quality
  }, [sessionId, submission.evidenceType, submission.submissionId, submission.submissionSnapshotHash])

  const request = useCallback(async (runCheck: boolean) => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase(runCheck ? 'checking' : 'loading'); setError(null)
    try {
      const response = runCheck
        ? await evidenceQualityProvider.check(sessionId, submission.submissionId, controller.signal)
        : await evidenceQualityProvider.get(sessionId, submission.submissionId, controller.signal)
      const result = acceptResponse(response)
      if (runCheck && !result) throw { code: 'EVIDENCE_QUALITY_RESULT_MISSING', message: '서버가 품질검증 결과를 반환하지 않았습니다.', retryable: true } satisfies ApiError
      if (sequence === sequenceRef.current) setQuality(result)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeEvidenceQualityError(caught))
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [acceptResponse, sessionId, submission.submissionId])

  useEffect(() => {
    queueMicrotask(() => void request(false))
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [request])

  if (phase === 'loading' && !quality) return <section className="evidence-quality evidence-quality--loading" aria-label="Evidence 품질검증 상태 확인"><span /><span /></section>

  if (!quality) return <section className="evidence-quality" aria-labelledby="evidence-quality-title"><div className="evidence-quality__heading"><div><span>자료 품질 확인</span><h3 id="evidence-quality-title">제출한 자료를 확인해주세요</h3></div><strong>확인 전</strong></div><p>출처·최신성·진위·완전성·일관성·변조 여부를 확인합니다. 버튼을 누르기 전에는 자동으로 확인하지 않습니다.</p>{error && <div className="evidence-quality__error" role="alert"><p>{error.message}</p></div>}<button className="button button--primary" type="button" disabled={phase === 'checking'} onClick={() => void request(true)}>{phase === 'checking' ? '자료를 확인하는 중…' : '자료 품질 확인'}</button></section>

  const copy = statusCopy[quality.status]
  return <section className={`evidence-quality evidence-quality--${quality.status.toLowerCase()}`} aria-labelledby="evidence-quality-title">
    <div className="evidence-quality__heading"><div><span>자료 품질 확인</span><h3 id="evidence-quality-title">{copy.title}</h3></div></div><p>{copy.description}</p>
    {error && <div className="evidence-quality__error" role="alert"><p>{error.message}</p></div>}
    <ul className="evidence-quality__checks">{quality.checks.map((check) => <li key={check.dimension}><div><strong>{dimensionLabels[check.dimension]}</strong></div><span className={`evidence-quality__check-status evidence-quality__check-status--${check.status.toLowerCase()}`}>{checkStatusLabels[check.status]}</span></li>)}</ul>
    <CustomerTechnicalDetails><dl><div><dt>전체 상태</dt><dd><code>{quality.status}</code></dd></div><div><dt>다음 처리</dt><dd><code>{quality.nextAction}</code></dd></div><div><dt>보완평가 사용</dt><dd>{quality.eligibleForReassessment ? '가능' : '불가'}</dd></div><div><dt>담당자 확인</dt><dd>{quality.underwriterRequired ? '필요' : '필요 없음'}</dd></div><div><dt>확인 시점</dt><dd>{formatDate(quality.checkedAt)}</dd></div><div><dt>품질 정책 버전</dt><dd><code>{quality.qualityPolicyVersion}</code></dd></div><div><dt>품질검증 ID</dt><dd><code>{quality.qualityCheckId}</code></dd></div>{quality.checks.map((check) => <div key={check.dimension}><dt>{dimensionLabels[check.dimension]} 근거</dt><dd><code>{check.rationaleCode}</code></dd></div>)}{quality.rejectionCodes.map((code) => <div key={code}><dt>미통과 코드</dt><dd><code>{code}</code></dd></div>)}{quality.suspicionCodes.map((code) => <div key={code}><dt>이상 징후 코드</dt><dd><code>{code}</code></dd></div>)}</dl></CustomerTechnicalDetails>
    {quality.status === 'REJECTED' && <Link className="button button--primary" to="/evidence?selectNext=1">다음 자료 한 건 확인</Link>}
    {quality.status === 'ACCEPTED' && <SupplementalAssessmentPanel sessionId={sessionId} submissionId={submission.submissionId} qualityCheckId={quality.qualityCheckId} />}
  </section>
}

export default EvidenceQualityPanel
