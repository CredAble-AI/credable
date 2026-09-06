import { useCallback, useEffect, useRef, useState } from 'react'
import { normalizeEvidenceQualityError } from '../api/evidenceQualityClient'
import { evidenceQualityProvider } from '../hooks/useEvidenceQualityState'
import type { ApiError } from '../types/api'
import type { EvidenceQualityResponse, EvidenceQualityState } from '../types/evidenceQuality'
import type { EvidenceSubmissionState } from '../types/evidenceSubmission'

interface EvidenceQualityPanelProps { sessionId: string; submission: EvidenceSubmissionState }
type Phase = 'loading' | 'checking' | 'idle'

const dimensionLabels: Record<EvidenceQualityState['checks'][number]['dimension'], string> = {
  PROVENANCE: '출처', FRESHNESS: '최신성', AUTHENTICITY: '진위', COMPLETENESS: '완전성', CONSISTENCY: '일관성', MANIPULATION_RISK: '조작 위험',
}
const statusCopy: Record<EvidenceQualityState['status'], { title: string; description: string }> = {
  ACCEPTED: { title: '품질검증을 통과했습니다', description: '서버 응답상 보완평가 입력으로 사용할 수 있습니다.' },
  REJECTED: { title: '이 증빙은 자동 재평가에서 제외됩니다', description: '통과하지 못한 항목과 서버 사유 코드를 확인해주세요.' },
  REVIEW_REQUIRED: { title: '심사역 확인이 필요합니다', description: '서버가 이상 징후를 확인해 자동 보완평가를 중단했습니다.' },
}
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

  if (!quality) return <section className="evidence-quality" aria-labelledby="evidence-quality-title"><div className="evidence-quality__heading"><div><span>EVIDENCE QUALITY</span><h3 id="evidence-quality-title">제출한 증빙의 품질을 확인해주세요</h3></div><strong>검증 전</strong></div><p>출처·최신성·진위·완전성·일관성·조작 위험을 백엔드가 확인합니다. 버튼을 누르기 전에는 자동으로 검증하지 않습니다.</p>{error && <div className="evidence-quality__error" role="alert"><p>{error.message}</p><small>{error.code}{error.requestId ? ` · 요청 ID ${error.requestId}` : ''}</small></div>}<button className="button button--primary" type="button" disabled={phase === 'checking'} onClick={() => void request(true)}>{phase === 'checking' ? '백엔드에서 확인 중…' : '증빙 품질 확인'}</button></section>

  const copy = statusCopy[quality.status]
  return <section className={`evidence-quality evidence-quality--${quality.status.toLowerCase()}`} aria-labelledby="evidence-quality-title">
    <div className="evidence-quality__heading"><div><span>EVIDENCE QUALITY</span><h3 id="evidence-quality-title">{copy.title}</h3></div><strong>{quality.status}</strong></div><p>{copy.description}</p>
    {error && <div className="evidence-quality__error" role="alert"><p>{error.message}</p><small>{error.code}</small></div>}
    <ul className="evidence-quality__checks">{quality.checks.map((check) => <li key={check.dimension}><div><strong>{dimensionLabels[check.dimension]}</strong><code>{check.rationaleCode}</code></div><span className={`evidence-quality__check-status evidence-quality__check-status--${check.status.toLowerCase()}`}>{check.status}</span></li>)}</ul>
    {(quality.rejectionCodes.length > 0 || quality.suspicionCodes.length > 0) && <div className="evidence-quality__codes">{quality.rejectionCodes.length > 0 && <p><strong>미통과 사유</strong>{quality.rejectionCodes.join(' · ')}</p>}{quality.suspicionCodes.length > 0 && <p><strong>이상 징후</strong>{quality.suspicionCodes.join(' · ')}</p>}</div>}
    <dl className="evidence-quality__metadata"><div><dt>다음 조치</dt><dd><code>{quality.nextAction}</code></dd></div><div><dt>재평가 입력</dt><dd>{quality.eligibleForReassessment ? '서버 응답상 가능' : '서버 응답상 불가'}</dd></div><div><dt>심사역 확인</dt><dd>{quality.underwriterRequired ? '필요' : '서버 응답상 필요 없음'}</dd></div><div><dt>검증 시점</dt><dd>{formatDate(quality.checkedAt)}</dd></div><div><dt>품질 정책 버전</dt><dd><code>{quality.qualityPolicyVersion}</code></dd></div><div><dt>품질검증 ID</dt><dd><code>{quality.qualityCheckId}</code></dd></div></dl>
  </section>
}

export default EvidenceQualityPanel
