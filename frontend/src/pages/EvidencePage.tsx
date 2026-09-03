import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import { normalizeEvidenceError } from '../api/evidenceClient'
import { mockEligibilityProvider } from '../mocks/eligibilityProvider'
import { mockEvidenceProvider } from '../mocks/evidenceProvider'
import type { ApiError, EligibilityResult, EvidenceAvailability, EvidenceRecommendation, SecondLookCase } from '../types/case'
import './EvidencePage.css'

const evidenceNames: Record<string, { name: string; period: string }> = {
  RECENT_SALES_DEPOSIT: { name: '최근 3개월 매출 입금 내역', period: '최근 3개월' }, TAX_FILING: { name: '최근 부가세 신고 자료', period: '최근 신고기간' }, CARD_POS_SALES: { name: '카드·POS 매출 자료', period: '최근 3개월' }, SIX_MONTH_SALES_DEPOSIT: { name: '최근 6개월 매출 입금 내역', period: '최근 6개월' }, OTHER_BANK_ACCOUNT: { name: '타행 매출계좌 내역', period: '최근 6개월' }, SOURCE_VERIFICATION: { name: '원본 매출 입금 내역 재확인', period: '제출 자료 대상기간' }, TAX_CROSS_CHECK: { name: '세금 신고 자료 교차검증', period: '최근 신고기간' }, CARD_POS_LEDGER: { name: '카드·POS 정산 원장', period: '검토 대상기간' },
}
const availabilityLabels: Record<EvidenceAvailability, string> = { BANK_INTERNAL: '은행 보유', CUSTOMER_UPLOAD: '고객 제출', CONSENT_REQUIRED: '동의 및 연결 필요', PARTNER_REQUIRED: '제휴 연결 필요' }
const basedOnLabels: Record<EvidenceRecommendation['basedOn'][number], string> = { APPLICATION: '신청정보', DECLINE_REASON: '거절사유', BANK_ACCOUNT: '은행 보유 계좌', CURRENT_EVIDENCE: '현재 증빙' }
const sourceLabels: Record<EvidenceRecommendation['conditionalSources'][number], string> = { OPEN_BANKING: 'Open Banking', CARD_POS: '카드·POS', DELIVERY_SETTLEMENT: '배달 정산' }
const rationaleLabels: Record<string, string> = { RECENT_PERFORMANCE_MISSING: '신청 시점에 반영되지 않은 최근 실적을 확인합니다.', SHORT_FINANCIAL_HISTORY: '짧은 금융이력을 추가 Evidence로 보완합니다.', EVIDENCE_COVERAGE_GAP: '필수 Evidence의 기간과 커버리지를 보완합니다.', SOURCE_CONSISTENCY_CHECK: '제출 자료의 출처와 정합성을 확인합니다.', DUPLICATE_CHECK: '중복 여부를 원본 자료와 교차 확인합니다.' }

function EvidencePage() {
  const navigate = useNavigate()
  const caseId = sessionStorage.getItem('credable.caseId')
  const [recommendation, setRecommendation] = useState<EvidenceRecommendation | null>(null)
  const [caseSummary, setCaseSummary] = useState<SecondLookCase | null>(null)
  const [eligibility, setEligibility] = useState<EligibilityResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isRecomputing, setIsRecomputing] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [isReadyForQuality, setIsReadyForQuality] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const sequenceRef = useRef(0)
  const controllerRef = useRef<AbortController | null>(null)

  const loadRecommendation = useCallback(async (recomputeReason?: string) => {
    if (!caseId || controllerRef.current) return
    const sequence = ++sequenceRef.current
    const controller = new AbortController()
    controllerRef.current = controller
    setError(null)
    if (recomputeReason) setIsRecomputing(true)
    else setIsLoading(true)
    try {
      const [nextCase, nextEligibility] = await Promise.all([mockEligibilityProvider.getCase(caseId, controller.signal), mockEligibilityProvider.check({ caseId }, controller.signal)])
      if (nextEligibility.classification === 'HARD_DECLINE') { navigate('/eligibility', { replace: true }); return }
      const next = await mockEvidenceProvider.getRequirements({ caseId, recomputeReason }, controller.signal)
      if (!controller.signal.aborted && sequence === sequenceRef.current) {
        setCaseSummary(nextCase)
        setEligibility(nextEligibility)
        setRecommendation(next)
        if (recomputeReason) { setIsReadyForQuality(true); setAnnouncement('추천이 최신 정보로 다시 계산되었습니다') }
      }
    } catch (caughtError) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeEvidenceError(caughtError))
    } finally {
      if (sequence === sequenceRef.current) { controllerRef.current = null; setIsLoading(false); setIsRecomputing(false) }
    }
  }, [caseId, navigate])

  useEffect(() => {
    if (!caseId) { navigate('/case', { replace: true }); return }
    queueMicrotask(() => { if (!controllerRef.current) void loadRecommendation() })
    return () => { sequenceRef.current += 1; controllerRef.current?.abort(); controllerRef.current = null }
  }, [caseId, loadRecommendation, navigate])

  const submitDemoEvidence = () => {
    if (isRecomputing || !recommendation) return
    setSubmitted(true)
    setIsReadyForQuality(false)
    setAnnouncement('민감한 원문 파일 없이 데모 증빙 제출 상태가 처리되었습니다')
    void loadRecommendation('DEMO_EVIDENCE_SUBMITTED')
  }

  if (!caseId) return null
  const recommended = recommendation ? evidenceNames[recommendation.recommendedEvidenceType] : null
  const recommendedCandidate = recommendation?.candidates.find((candidate) => candidate.evidenceType === recommendation.recommendedEvidenceType)

  return <div className="workspace-shell"><Header /><main className="evidence-page"><div className="container evidence-layout">
    <header className="workflow-heading"><div className="demo-badge"><span aria-hidden="true" />Mock mode · Demo Only</div><p className="step-kicker">Second-Look workflow</p><div className="current-step"><span>현재 단계</span><strong>Evidence</strong></div></header>
    <section className="evidence-summary" aria-labelledby="evidence-summary-title"><div><p className="section-kicker">CASE &amp; ELIGIBILITY</p><h1 id="evidence-summary-title">추천 증빙 확인</h1></div>{caseSummary && eligibility ? <dl><div><dt>기존 결정</dt><dd>{caseSummary.currentDecision === 'HELD' ? '보류' : '거절'}</dd></div><div><dt>신청 상품</dt><dd>{caseSummary.application.productType}</dd></div><div><dt>Eligibility</dt><dd>{eligibility.classification === 'SECOND_LOOK_ELIGIBLE' ? 'Second-Look 진입 가능' : '추가 정보 확인 필요'}</dd></div></dl> : <p>Eligibility 결과를 바탕으로 서버가 정한 증빙 순서를 그대로 안내합니다.</p>}</section>
    {isLoading && !recommendation && <section className="evidence-state" role="status"><div className="loading-orbit" aria-hidden="true"><span /></div><h1>필요한 Evidence를 확인하고 있습니다</h1><p>Case와 현재 증빙을 기준으로 서버 추천을 불러오는 중입니다.</p></section>}
    {error && !recommendation && <section className="evidence-state evidence-state--error" role="alert"><span className="error-mark" aria-hidden="true">!</span><h1>추천 가능한 증빙을 확인하지 못했습니다</h1><p>{error.message}</p><small>오류 코드: {error.code}{error.requestId ? ` · 요청 ID: ${error.requestId}` : ''}</small><div className="result-actions">{error.retryable && <button className="button button--primary" type="button" onClick={() => void loadRecommendation()}>다시 확인하기</button>}<Link className="button button--secondary" to="/eligibility">Eligibility로 돌아가기</Link></div></section>}
    {recommendation && recommendation.candidates.length === 0 && <section className="evidence-state" role="alert"><h1>추천 가능한 증빙을 확인하지 못했습니다</h1><p>임의의 후보를 만들지 않습니다. 잠시 후 다시 확인해주세요.</p><button className="button button--primary" type="button" onClick={() => void loadRecommendation()}>다시 확인하기</button></section>}
    {recommendation && recommendation.candidates.length > 0 && recommended && <>
      <section className={`recommendation-hero${isRecomputing ? ' recommendation-hero--updating' : ''}`} aria-labelledby="recommendation-title"><div className="recommendation-icon" aria-hidden="true">↗</div><div className="recommendation-copy"><p className="section-kicker">지금 가장 필요한 증빙</p><h1 id="recommendation-title">{recommended.name}</h1><ul className="rationale-list">{recommendation.rationaleCodes.map((code) => <li key={code}>{rationaleLabels[code] ?? code}</li>)}</ul><dl><div><dt>필요 기간</dt><dd>{recommended.period}</dd></div><div><dt>출처</dt><dd>{recommendedCandidate ? availabilityLabels[recommendedCandidate.availability] : '출처 정보 없음'}</dd></div></dl></div><span className="demo-seal">Demo Only</span>{isRecomputing && <p className="updating-label" role="status">이전 추천을 유지하며 최신 정보로 다시 계산 중입니다…</p>}</section>
      <section className="evidence-section" aria-labelledby="candidate-title"><div className="section-heading"><div><p className="section-kicker">ORDERED BY SERVER</p><h2 id="candidate-title">Evidence 후보</h2></div><p>표시 순서는 서버 응답과 동일합니다.</p></div><ol className="candidate-list">{recommendation.candidates.map((candidate, index) => <li key={`${candidate.evidenceType}-${index}`}><span className="candidate-rank">{index + 1}</span><div><strong>{evidenceNames[candidate.evidenceType]?.name ?? candidate.evidenceType}</strong><small>{evidenceNames[candidate.evidenceType]?.period ?? '필요 기간 확인'}</small></div><span className={`availability availability--${candidate.availability.toLowerCase()}`}>{availabilityLabels[candidate.availability]}</span></li>)}</ol></section>
      <div className="evidence-columns"><section className="evidence-section"><p className="section-kicker">OPTIONAL SOURCES</p><h2>선택적 정밀화 데이터</h2><p className="section-description">외부 연결 없이도 은행 보유 데이터로 기본 진행할 수 있습니다.</p><ul className="source-list">{recommendation.conditionalSources.map((source) => <li key={source}><span>{sourceLabels[source]}</span><small>현재 데모에서는 미연동</small></li>)}</ul></section><section className="evidence-section"><p className="section-kicker">RECOMMENDATION BASIS</p><h2>추천 근거</h2><ul className="basis-list">{recommendation.basedOn.map((basis) => <li key={basis}>{basedOnLabels[basis]}</li>)}</ul><dl className="governance"><div><dt>재계산 시각</dt><dd>{new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(recommendation.recalculatedAt))}</dd></div><div><dt>정책 설정</dt><dd>{recommendation.policyVersion ?? 'Demo configuration'}</dd></div></dl></section></div>
      <section className="evidence-cta"><div><strong>{submitted ? '데모 증빙 제출 완료' : '원문 금융문서는 업로드하지 않습니다'}</strong><p>{submitted ? '최신 추천을 확인한 뒤 품질 검토 단계로 이동하세요.' : '버튼을 누르면 데모 제출 상태만 처리하고 추천을 한 번 재계산합니다.'}</p></div>{isReadyForQuality ? <Link className="button button--primary" to="/evidence-quality">증빙 품질 확인하기</Link> : <button className="button button--primary" type="button" disabled={isRecomputing || submitted} onClick={submitDemoEvidence}>{isRecomputing ? '추천 재계산 중…' : submitted ? '재계산 결과 확인 필요' : '추천 증빙으로 계속하기'}</button>}</section>
    </>}
    {error && recommendation && <div className="inline-error" role="alert"><div><strong>최신 추천으로 갱신하지 못했습니다</strong><small>{error.message}{error.requestId ? ` · 요청 ID: ${error.requestId}` : ''}</small></div>{error.retryable && <button type="button" onClick={() => void loadRecommendation('DEMO_EVIDENCE_SUBMITTED')}>다시 계산</button>}</div>}
    <p className="sr-only" aria-live="polite">{announcement}</p>
  </div></main></div>
}
export default EvidencePage
