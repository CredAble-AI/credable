import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { normalizeEvidenceResolutionError } from '../api/evidenceResolutionClient'
import { evidenceResolutionProvider } from '../hooks/useEvidenceResolutionState'
import type { ApiError } from '../types/api'
import type { EvidenceResolutionContext, EvidenceResolutionResponse, EvidenceResolutionState, EvidenceResolutionStatus } from '../types/evidenceResolution'
import AssessmentExplanationPanel from './AssessmentExplanationPanel'
import AssessmentReviewPanel from './AssessmentReviewPanel'
import CustomerTechnicalDetails from './CustomerTechnicalDetails'
import { withMinimumDuration } from '../utils/pacedRequest'

interface EvidenceResolutionPanelProps extends EvidenceResolutionContext { sessionId: string }
type Phase = 'loading' | 'resolving' | 'idle'

const statusCopy: Record<EvidenceResolutionStatus, { title: string; description: string }> = {
  RESOLVED: { title: '추가 자료 확인을 마쳤습니다', description: '결과 범위가 충분히 확인되어 더 이상 자료를 요청하지 않습니다.' },
  MORE_EVIDENCE_REQUIRED: { title: '자료 한 건을 더 확인할 수 있습니다', description: '결과 범위를 더 명확히 하기 위해 다음으로 필요한 자료 한 건을 안내합니다.' },
  HUMAN_REVIEW: { title: '담당자 확인으로 전환했습니다', description: '자동 확인을 중단하고 담당자가 직접 살펴보는 단계로 전환했습니다.' },
}
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function EvidenceResolutionPanel({ sessionId, comparisonId, supplementalAssessmentId }: EvidenceResolutionPanelProps) {
  const [resolution, setResolution] = useState<EvidenceResolutionState | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [error, setError] = useState<ApiError | null>(null)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)
  const context = useMemo(() => ({ comparisonId, supplementalAssessmentId }), [comparisonId, supplementalAssessmentId])

  const acceptResponse = useCallback((response: EvidenceResolutionResponse, required: boolean) => {
    if (response.sessionId !== sessionId) throw { code: 'EVIDENCE_RESOLUTION_CONTEXT_MISMATCH', message: '현재 세션의 Evidence 수집 판단을 확인할 수 없습니다.', retryable: true } satisfies ApiError
    const result = response.resolution
    if (!result) {
      if (required) throw { code: 'EVIDENCE_RESOLUTION_RESULT_MISSING', message: '서버가 Evidence 수집 판단을 반환하지 않았습니다.', retryable: true } satisfies ApiError
      return null
    }
    if (result.comparisonId !== comparisonId || result.supplementalAssessmentId !== supplementalAssessmentId) {
      if (required) throw { code: 'EVIDENCE_RESOLUTION_CONTEXT_MISMATCH', message: '현재 평가 비교와 일치하는 수집 판단을 확인할 수 없습니다.', retryable: true } satisfies ApiError
      return null
    }
    return result
  }, [comparisonId, sessionId, supplementalAssessmentId])

  const request = useCallback(async (resolve: boolean) => {
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setPhase(resolve ? 'resolving' : 'loading'); setError(null)
    try {
      let response = resolve
        ? await withMinimumDuration(evidenceResolutionProvider.resolve(sessionId, context, controller.signal))
        : await evidenceResolutionProvider.get(sessionId, controller.signal)
      if (!resolve && !acceptResponse(response, false)) {
        if (sequence === sequenceRef.current) setPhase('resolving')
        response = await withMinimumDuration(evidenceResolutionProvider.resolve(sessionId, context, controller.signal))
        resolve = true
      }
      const result = acceptResponse(response, resolve)
      if (sequence === sequenceRef.current) setResolution(result)
    } catch (caught) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeEvidenceResolutionError(caught))
    } finally {
      if (sequence === sequenceRef.current) setPhase('idle')
    }
  }, [acceptResponse, context, sessionId])

  useEffect(() => {
    queueMicrotask(() => void request(false))
    return () => { sequenceRef.current += 1; controllerRef.current?.abort() }
  }, [request])

  if (phase !== 'idle' && !resolution) return <section className="evidence-resolution evidence-resolution--loading" aria-label="다음 단계 확인 중"><span /><span /><p>결과가 충분히 명확해졌는지 확인하고 있습니다.</p></section>

  if (!resolution) return <section className="evidence-resolution" aria-labelledby="resolution-title"><div className="evidence-resolution__heading"><div><span>다음 단계</span><h5 id="resolution-title">다음 단계를 확인하지 못했습니다</h5></div><strong>재시도 필요</strong></div><p>현재 결과는 그대로 보존되며 추가 자료 요청이나 담당자 확인은 아직 시작되지 않았습니다.</p>{error && <div className="evidence-resolution__error" role="alert"><p>{error.message}</p></div>}<button className="button button--secondary" type="button" disabled={phase === 'resolving'} onClick={() => void request(true)}>{phase === 'resolving' ? '다음 단계를 확인하는 중…' : '다음 단계 다시 확인'}</button></section>

  const copy = statusCopy[resolution.status]
  return <><section className={`evidence-resolution evidence-resolution--${resolution.status.toLowerCase()}`} aria-labelledby="resolution-title">
    <div className="evidence-resolution__heading"><div><span>다음 단계</span><h5 id="resolution-title">{copy.title}</h5></div></div>
    <p>{copy.description}</p>
    <div className="evidence-resolution__action"><span>이어서 할 일</span>{resolution.nextAction === 'SHOW_UPDATED_RESULTS' && <Link className="button button--primary" to="/products">자사 상품 조건 확인</Link>}{resolution.nextAction === 'REQUEST_NEXT_EVIDENCE' && <Link className="button button--primary" to="/evidence?selectNext=1">다음 자료 한 건 확인</Link>}{resolution.status === 'HUMAN_REVIEW' && <Link className="button button--primary" to="/admin/reviews">담당자 확인 현황 보기</Link>}</div>
    <CustomerTechnicalDetails><dl><div><dt>처리 상태</dt><dd><code>{resolution.status}</code></dd></div><div><dt>다음 처리</dt><dd><code>{resolution.nextAction}</code></dd></div><div><dt>자료 수집</dt><dd>{resolution.stopEvidenceCollection ? '종료' : '계속'}</dd></div><div><dt>담당자 확인</dt><dd>{resolution.underwriterRequired ? '필요' : '필요 없음'}</dd></div><div><dt>판단 사유</dt><dd><code>{resolution.reasonCode}</code></dd></div><div><dt>판단 시점</dt><dd>{formatDate(resolution.resolvedAt)}</dd></div><div><dt>판단 ID</dt><dd><code>{resolution.resolutionId}</code></dd></div><div><dt>보정 버전</dt><dd><code>{resolution.calibrationVersion ?? '제공되지 않음'}</code></dd></div><div><dt>경계 정책 버전</dt><dd><code>{resolution.boundaryPolicyVersion}</code></dd></div>{resolution.possibleRoutes.map((code) => <div key={code}><dt>가능 경로</dt><dd><code>{code}</code></dd></div>)}{resolution.crossedBoundaryCodes.map((code) => <div key={code}><dt>남은 정책 경계</dt><dd><code>{code}</code></dd></div>)}</dl></CustomerTechnicalDetails>
  </section><AssessmentExplanationPanel key={resolution.resolutionId} sessionId={sessionId} /><AssessmentReviewPanel sessionId={sessionId} /></>
}

export default EvidenceResolutionPanel
