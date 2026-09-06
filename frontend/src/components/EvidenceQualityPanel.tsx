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
const verifiedScopeLabels = {
  DOCUMENT_INTEGRITY: '업로드 후 변경 여부',
  MANIFEST_BINDING: '문서와 검증정보 연결',
  DEMO_ISSUER_IDENTITY: '발급 서버 식별 정보',
} as const
const dimensionDescriptions: Record<EvidenceQualityState['checks'][number]['dimension'], string> = {
  PROVENANCE: '발급 주체와 문서에 연결된 검증정보를 확인했습니다.',
  FRESHNESS: '요청한 확인 기간과 문서의 기준시점을 비교했습니다.',
  AUTHENTICITY: '업로드한 파일의 해시와 발급 시점의 검증값을 비교했습니다.',
  COMPLETENESS: '사업자 식별·월별 내역·기간 합계 등 필수 항목의 누락 여부를 확인했습니다.',
  CONSISTENCY: '월별 내역과 기간 합계가 서로 맞는지 확인했습니다.',
  MANIPULATION_RISK: '파일명·형식·크기와 해시 변경 등 위·변조 의심 징후를 확인했습니다.',
}
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function EvidenceQualityPanel({ sessionId, submission }: EvidenceQualityPanelProps) {
  const [quality, setQuality] = useState<EvidenceQualityState | null>(null)
  const [underwriterReviewId, setUnderwriterReviewId] = useState<string | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const acceptResponse = useCallback((response: EvidenceQualityResponse) => {
    if (response.sessionId !== sessionId || (response.quality && (response.quality.submissionId !== submission.submissionId || response.quality.evidenceType !== submission.evidenceType || response.quality.submissionSnapshotHash !== submission.submissionSnapshotHash))) {
      throw { code: 'EVIDENCE_QUALITY_CONTEXT_MISMATCH', message: '현재 제출한 Evidence와 일치하는 품질검증 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
    }
    return response
  }, [sessionId, submission.evidenceType, submission.submissionId, submission.submissionSnapshotHash])

  const request = useCallback(async (runCheck: boolean) => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase(runCheck ? 'checking' : 'loading'); setError(null)
    try {
      let response = runCheck
        ? await evidenceQualityProvider.check(sessionId, submission.submissionId, controller.signal)
        : await evidenceQualityProvider.get(sessionId, submission.submissionId, controller.signal)
      if (!runCheck && !response.quality) {
        if (sequence === sequenceRef.current) setPhase('checking')
        response = await evidenceQualityProvider.check(sessionId, submission.submissionId, controller.signal)
        runCheck = true
      }
      const accepted = acceptResponse(response)
      if (runCheck && !accepted.quality) throw { code: 'EVIDENCE_QUALITY_RESULT_MISSING', message: '서버가 품질검증 결과를 반환하지 않았습니다.', retryable: true } satisfies ApiError
      if (sequence === sequenceRef.current) {
        setQuality(accepted.quality)
        setUnderwriterReviewId(accepted.underwriterReviewId ?? null)
      }
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

  if (phase !== 'idle' && !quality) return <section className="evidence-quality evidence-quality--loading" aria-label="제출 자료 품질 확인 중"><span /><span /><p>제출한 자료의 출처·기준시점·누락·변경 여부를 확인하고 있습니다.</p></section>

  if (!quality) return <section className="evidence-quality" aria-labelledby="evidence-quality-title"><div className="evidence-quality__heading"><div><span>자료 품질 확인</span><h3 id="evidence-quality-title">자료를 확인하지 못했습니다</h3></div><strong>확인 필요</strong></div><p>제출한 자료는 보완평가에 반영되지 않았습니다. 일시적인 문제인지 다시 확인해주세요.</p>{error && <div className="evidence-quality__error" role="alert"><p>{error.message}</p></div>}<button className="button button--primary" type="button" disabled={phase === 'checking'} onClick={() => void request(true)}>{phase === 'checking' ? '자료를 다시 확인하는 중…' : '자료 품질 다시 확인'}</button></section>

  const copy = statusCopy[quality.status]
  return <section className={`evidence-quality evidence-quality--${quality.status.toLowerCase()}`} aria-labelledby="evidence-quality-title">
    <div className="evidence-quality__heading"><div><span>자료 품질 확인</span><h3 id="evidence-quality-title">{copy.title}</h3></div></div><p>{copy.description}</p>
    {error && <div className="evidence-quality__error" role="alert"><p>{error.message}</p></div>}
    {quality.trustVerification && <div className={`evidence-trust evidence-trust--${quality.trustVerification.status.toLowerCase()}`}><div><span>검증 신뢰 근거</span><strong>{quality.trustVerification.status === 'VERIFIED' ? '서버가 서명한 검증정보를 확인했습니다' : '서명된 검증정보를 확인하지 못했습니다'}</strong></div>{quality.trustVerification.status === 'VERIFIED' ? <ul>{quality.trustVerification.verifiedScopes.map((scope) => <li key={scope}>{verifiedScopeLabels[scope]}</li>)}</ul> : <p>검증할 수 없는 문서는 자동 보완평가에 사용하지 않습니다.</p>}<small>현재 연결된 발급 서버의 검증정보를 기준으로 확인하며, 실제 금융기관의 발급 사실을 의미하지 않습니다.</small></div>}
    <ul className="evidence-quality__checks">{quality.checks.map((check) => <li key={check.dimension}><div><strong>{dimensionLabels[check.dimension]}</strong><small>{dimensionDescriptions[check.dimension]}</small></div><span className={`evidence-quality__check-status evidence-quality__check-status--${check.status.toLowerCase()}`}>{checkStatusLabels[check.status]}</span></li>)}</ul>
    <CustomerTechnicalDetails><dl><div><dt>전체 상태</dt><dd><code>{quality.status}</code></dd></div><div><dt>다음 처리</dt><dd><code>{quality.nextAction}</code></dd></div><div><dt>보완평가 사용</dt><dd>{quality.eligibleForReassessment ? '가능' : '불가'}</dd></div><div><dt>담당자 확인</dt><dd>{quality.underwriterRequired ? '필요' : '필요 없음'}</dd></div><div><dt>확인 시점</dt><dd>{formatDate(quality.checkedAt)}</dd></div><div><dt>품질 정책 버전</dt><dd><code>{quality.qualityPolicyVersion}</code></dd></div><div><dt>품질검증 ID</dt><dd><code>{quality.qualityCheckId}</code></dd></div>{quality.trustVerification && <><div><dt>신뢰 채널</dt><dd><code>{quality.trustVerification.channel}</code></dd></div><div><dt>서명 알고리즘</dt><dd><code>{quality.trustVerification.algorithm ?? 'NONE'}</code></dd></div><div><dt>서명 키 ID</dt><dd><code>{quality.trustVerification.keyId ?? 'NONE'}</code></dd></div><div><dt>서명검증 근거</dt><dd><code>{quality.trustVerification.rationaleCode}</code></dd></div></>}{quality.checks.map((check) => <div key={check.dimension}><dt>{dimensionLabels[check.dimension]} 근거</dt><dd><code>{check.rationaleCode}</code></dd></div>)}{quality.rejectionCodes.map((code) => <div key={code}><dt>미통과 코드</dt><dd><code>{code}</code></dd></div>)}{quality.suspicionCodes.map((code) => <div key={code}><dt>이상 징후 코드</dt><dd><code>{code}</code></dd></div>)}</dl></CustomerTechnicalDetails>
    {quality.status === 'REVIEW_REQUIRED' && <div className="evidence-quality__review-link"><div><strong>자동 판단을 중단했습니다</strong><p>제출 자료와 이상 징후를 심사역 화면에서 함께 확인할 수 있습니다.</p></div><Link className="button button--primary" to={underwriterReviewId ? `/admin/reviews/${encodeURIComponent(underwriterReviewId)}` : '/admin/reviews'}>{underwriterReviewId ? '이 건을 심사역 화면에서 확인' : '심사역 검토 목록 보기'}</Link></div>}
    {quality.status === 'REJECTED' && <Link className="button button--primary" to="/evidence?selectNext=1">다음 자료 한 건 확인</Link>}
    {quality.status === 'ACCEPTED' && <SupplementalAssessmentPanel sessionId={sessionId} submissionId={submission.submissionId} qualityCheckId={quality.qualityCheckId} />}
  </section>
}

export default EvidenceQualityPanel
