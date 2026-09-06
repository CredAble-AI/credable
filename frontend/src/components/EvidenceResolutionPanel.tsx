import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { normalizeEvidenceResolutionError } from '../api/evidenceResolutionClient'
import { evidenceResolutionProvider } from '../hooks/useEvidenceResolutionState'
import type { ApiError } from '../types/api'
import type { EvidenceResolutionContext, EvidenceResolutionResponse, EvidenceResolutionState, EvidenceResolutionStatus } from '../types/evidenceResolution'

interface EvidenceResolutionPanelProps extends EvidenceResolutionContext { sessionId: string }
type Phase = 'loading' | 'resolving' | 'idle'

const statusCopy: Record<EvidenceResolutionStatus, { title: string; description: string }> = {
  RESOLVED: { title: '추가 Evidence 수집을 종료했습니다', description: '서버가 하나의 Demo 처리 경로로 안정됐다고 판단해 추가 자료를 요청하지 않습니다.' },
  MORE_EVIDENCE_REQUIRED: { title: '추가 Evidence 한 건이 필요합니다', description: '서버 판단상 정책 경계가 남아 있어 다음 최소 Evidence 한 건을 확인할 수 있습니다.' },
  HUMAN_REVIEW: { title: '심사역 검토로 전환했습니다', description: '서버가 자동 수집을 중단하고 심사역 확인이 필요한 상태로 전환했습니다.' },
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
      const response = resolve
        ? await evidenceResolutionProvider.resolve(sessionId, context, controller.signal)
        : await evidenceResolutionProvider.get(sessionId, controller.signal)
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

  if (phase === 'loading' && !resolution) return <section className="evidence-resolution evidence-resolution--loading" aria-label="Evidence 수집 판단 확인"><span /><span /></section>

  if (!resolution) return <section className="evidence-resolution" aria-labelledby="resolution-title"><div className="evidence-resolution__heading"><div><span>COLLECTION DECISION</span><h5 id="resolution-title">추가 Evidence가 필요한지 확인합니다</h5></div><strong>판단 전</strong></div><p>서버가 보완평가 이후의 정책 경계를 확인해 수집 종료, 추가 요청 또는 심사역 이관을 결정합니다.</p>{error && <div className="evidence-resolution__error" role="alert"><p>{error.message}</p><small>{error.code}{error.requestId ? ` · 요청 ID ${error.requestId}` : ''}</small></div>}<button className="button button--secondary" type="button" disabled={phase === 'resolving'} onClick={() => void request(true)}>{phase === 'resolving' ? '백엔드에서 판단 중…' : '다음 단계 확인'}</button></section>

  const copy = statusCopy[resolution.status]
  return <section className={`evidence-resolution evidence-resolution--${resolution.status.toLowerCase()}`} aria-labelledby="resolution-title">
    <div className="evidence-resolution__heading"><div><span>COLLECTION DECISION</span><h5 id="resolution-title">{copy.title}</h5></div><strong>{resolution.status}</strong></div>
    <p>{copy.description}</p>
    <div className="evidence-resolution__action"><span>서버 다음 행동</span><strong>{resolution.nextAction}</strong>{resolution.nextAction === 'REQUEST_NEXT_EVIDENCE' && <Link className="button button--primary" to="/evidence?selectNext=1">다음 Evidence 한 건 확인</Link>}</div>
    {(resolution.possibleRoutes.length > 0 || resolution.crossedBoundaryCodes.length > 0) && <div className="evidence-resolution__codes">{resolution.possibleRoutes.length > 0 && <div><span>가능한 Demo 경로</span>{resolution.possibleRoutes.map((code) => <code key={code}>{code}</code>)}</div>}{resolution.crossedBoundaryCodes.length > 0 && <div><span>남은 정책 경계</span>{resolution.crossedBoundaryCodes.map((code) => <code key={code}>{code}</code>)}</div>}</div>}
    <dl className="evidence-resolution__metadata"><div><dt>수집 중단</dt><dd>{resolution.stopEvidenceCollection ? '중단' : '계속'}</dd></div><div><dt>심사역 확인</dt><dd>{resolution.underwriterRequired ? '필요' : '서버 응답상 필요 없음'}</dd></div><div><dt>판단 사유</dt><dd><code>{resolution.reasonCode}</code></dd></div><div><dt>판단 시점</dt><dd>{formatDate(resolution.resolvedAt)}</dd></div><div><dt>판단 ID</dt><dd><code>{resolution.resolutionId}</code></dd></div><div><dt>보정 버전</dt><dd><code>{resolution.calibrationVersion ?? '제공되지 않음'}</code></dd></div><div><dt>경계 정책 버전</dt><dd><code>{resolution.boundaryPolicyVersion}</code></dd></div></dl>
  </section>
}

export default EvidenceResolutionPanel
