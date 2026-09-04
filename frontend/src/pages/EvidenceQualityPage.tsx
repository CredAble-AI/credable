import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import { normalizeEvidenceQualityError } from '../api/evidenceQualityClient'
import { mockEligibilityProvider } from '../mocks/eligibilityProvider'
import { mockEvidenceQualityProvider } from '../mocks/evidenceQualityProvider'
import type { ApiError, EvidenceQualityItem, EvidenceQualityResponse, SecondLookCase } from '../types/case'
import './EvidenceQualityPage.css'

const statusCopy = {
  PASS: { label: 'PASS', summary: '품질 기준을 충족한 Evidence입니다.', use: '위험 분석에 사용' },
  FAIL: { label: 'FAIL', summary: 'Evidence가 부족하거나 보완이 필요합니다. 신용이 나쁘다는 의미가 아닙니다.', use: '보완 후 사용 가능' },
  SUSPICIOUS: { label: 'SUSPICIOUS', summary: '위험 분석에 사용하지 않습니다. 자동 부결이 아니라 심사역 확인이 필요합니다.', use: '위험 분석에서 제외' },
} as const
const gradeCopy: Record<string, string> = { GOOD: '사용 가능한 Evidence가 확인되었습니다.', INSUFFICIENT: 'Evidence 보완이 필요합니다.', REVIEW_REQUIRED: '심사역 확인이 필요한 Evidence입니다.' }
const sourceCopy = { PUBLIC: '공공 데이터', MOCK: 'Mock 자료', BANK: '은행 보유', PARTNER: '제휴 제공' } as const
const consistencyCopy = { OK: '정상', CHECK: '확인 필요', FAIL: '불일치 확인 필요' } as const
const anomalyCopy: Record<string, string> = { INSUFFICIENT_COVERAGE: '필요한 기간 또는 범위가 충분하지 않습니다.', SUDDEN_SALES_SPIKE: '매출의 급격한 변화에 대한 확인이 필요합니다.', DUPLICATE_TRANSACTION_PATTERN: '중복 거래 패턴 여부를 확인해야 합니다.', SOURCE_VERIFICATION_REQUIRED: 'Evidence 출처 확인이 필요합니다.' }
const formatDate = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))

function EvidenceQualityPage() {
  const navigate = useNavigate()
  const caseId = sessionStorage.getItem('credable.caseId')
  const evidenceSubmitted = sessionStorage.getItem('credable.evidenceSubmitted') === 'true'
  const [result, setResult] = useState<EvidenceQualityResponse | null>(null)
  const [caseSummary, setCaseSummary] = useState<SecondLookCase | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [requestVersion, setRequestVersion] = useState(0)
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)

  const loadQuality = useCallback(async () => {
    if (!caseId || controllerRef.current) return
    const sequence = ++sequenceRef.current
    const controller = new AbortController()
    controllerRef.current = controller
    setError(null)
    try {
      const [nextCase, eligibility] = await Promise.all([mockEligibilityProvider.getCase(caseId, controller.signal), mockEligibilityProvider.check({ caseId }, controller.signal)])
      if (eligibility.classification === 'HARD_DECLINE') { navigate('/eligibility', { replace: true }); return }
      if (!evidenceSubmitted) { navigate('/evidence', { replace: true }); return }
      const nextResult = await mockEvidenceQualityProvider.check({ caseId, submissionState: 'DEMO_SUBMITTED' }, controller.signal)
      if (!controller.signal.aborted && sequence === sequenceRef.current) { setCaseSummary(nextCase); setResult(nextResult) }
    } catch (caughtError) {
      if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeEvidenceQualityError(caughtError))
    } finally {
      if (sequence === sequenceRef.current) controllerRef.current = null
    }
  }, [caseId, evidenceSubmitted, navigate])

  useEffect(() => {
    if (!caseId) { navigate('/case', { replace: true }); return }
    queueMicrotask(() => { if (!controllerRef.current) void loadQuality() })
    return () => { sequenceRef.current += 1; controllerRef.current?.abort(); controllerRef.current = null }
  }, [caseId, loadQuality, navigate, requestVersion])

  if (!caseId) return null
  return <div className="workspace-shell"><Header /><main className="quality-page"><div className="container quality-layout">
    <header className="quality-flow" aria-label="Second-Look 진행 단계"><ol><li>Case</li><li>Eligibility</li><li>Evidence</li><li aria-current="step">Quality</li></ol><span>Mock mode · Demo Only</span></header>
    {caseSummary && <section className="quality-case" aria-labelledby="quality-case-title"><div><p className="section-kicker">CASE SUMMARY</p><h1 id="quality-case-title">{caseSummary.applicant.businessName}</h1></div><dl><div><dt>기존 결정</dt><dd>{caseSummary.currentDecision === 'HELD' ? '보류' : '거절'}</dd></div><div><dt>기준시점</dt><dd>{formatDate(caseSummary.featureCutoffAt)}</dd></div><div><dt>환경</dt><dd>Demo Only</dd></div></dl></section>}
    {!result && !error && <section className="quality-state" role="status" aria-live="polite"><div className="quality-spinner" aria-hidden="true"><span /></div><h1>증빙의 품질과 사용 가능성을 확인하고 있습니다</h1><p>출처, 최신성, 커버리지, 정합성과 기준시점을 확인하는 중입니다.</p></section>}
    {error && <section className="quality-state quality-state--error" role="alert"><span className="error-mark" aria-hidden="true">!</span><h1>Evidence 품질을 확인하지 못했습니다</h1><p>{error.message}</p><small>오류 코드: {error.code}{error.requestId ? ` · 요청 ID: ${error.requestId}` : ''}</small><div className="result-actions">{error.retryable && <button className="button button--primary" type="button" onClick={() => setRequestVersion((value) => value + 1)}>다시 확인하기</button>}<Link className="button button--secondary" to="/evidence">Evidence로 돌아가기</Link></div></section>}
    {result && result.items.length === 0 && <section className="quality-state"><h1>품질을 확인할 Evidence가 없습니다</h1><p>임의 Evidence를 생성하지 않습니다. 추천 증빙을 다시 확인해주세요.</p><Link className="button button--primary" to="/evidence">Evidence로 돌아가기</Link></section>}
    {result && result.items.length > 0 && <QualityResult result={result} />}
  </div></main></div>
}

function QualityResult({ result }: { result: EvidenceQualityResponse }) {
  return <><section className={`quality-overview grade--${result.overallGrade.toLowerCase()}`} aria-labelledby="quality-title"><span className="quality-overview__icon" aria-hidden="true">◎</span><div><p className="section-kicker">EVIDENCE QUALITY RESULT</p><h1 id="quality-title">Evidence 품질 확인 결과</h1><p>{gradeCopy[result.overallGrade] ?? result.overallGrade}</p></div><div className="grade"><small>Overall grade</small><strong>{result.overallGrade}</strong></div></section><section className="quality-items" aria-labelledby="quality-items-title"><div className="quality-section-heading"><div><p className="section-kicker">VERIFIED BY SERVER</p><h2 id="quality-items-title">Evidence 항목</h2></div><p>상태와 사용 가능 여부는 서버 응답을 그대로 표시합니다.</p></div><div className="quality-list">{result.items.map((item) => <QualityItem item={item} key={item.evidenceId} />)}</div></section><section className="quality-actions"><div><strong>다음 경로는 서버 결과로 확인합니다</strong><p>이 화면의 상태만으로 승인 또는 최종 경로를 확정하지 않습니다.</p></div><div>{result.items.some((item) => item.status === 'FAIL') && <Link className="button button--secondary" to="/evidence">증빙 다시 확인하기</Link>}<Link className="button button--primary" to="/second-look">Second-Look 경로 확인하기</Link></div></section></>
}

function QualityItem({ item }: { item: EvidenceQualityItem }) {
  const copy = statusCopy[item.status]
  return <article className={`quality-item status--${item.status.toLowerCase()}`}><header><div><span className="status-badge"><b aria-hidden="true">{item.status === 'PASS' ? '✓' : item.status === 'FAIL' ? '!' : '?'}</b>{copy.label}</span><h3>{item.displayName ?? item.evidenceType ?? 'Evidence'}</h3></div><strong className="risk-use">{item.usableForRisk ? '위험 분석에 사용' : copy.use}</strong></header><p className="status-guidance">{copy.summary}</p>{!item.pointInTimeValid && <p className="cutoff-warning"><strong>기준시점 제외</strong>심사 이후 생성되어 위험 분석에 사용되지 않습니다.</p>}<dl className="quality-metrics"><div><dt>출처 확인</dt><dd>{item.sourceVerified ? '확인됨' : '확인 필요'}</dd></div><div><dt>최신성</dt><dd>{item.freshnessDays === undefined ? '확인되지 않음' : `${item.freshnessDays}일 전`}</dd></div><div><dt>커버리지</dt><dd>{item.coveragePct === undefined ? '확인되지 않음' : `${item.coveragePct}%`}</dd></div><div><dt>정합성</dt><dd>{consistencyCopy[item.consistency]}</dd></div><div><dt>기준시점</dt><dd>{item.pointInTimeValid ? '유효' : '유효하지 않음'}</dd></div><div><dt>출처 유형</dt><dd>{item.sourceType ? sourceCopy[item.sourceType] : '확인되지 않음'}</dd></div></dl><div className="anomalies"><h4>이상 징후</h4>{item.anomalyFlags.length === 0 ? <p>탐지된 이상 징후 없음</p> : <ul>{item.anomalyFlags.map((flag) => <li key={flag}>{anomalyCopy[flag] ?? flag}</li>)}</ul>}</div>{(item.observedAt || item.retrievedAt || item.featureCutoffAt) && <dl className="quality-dates">{item.observedAt && <div><dt>관측</dt><dd>{formatDate(item.observedAt)}</dd></div>}{item.retrievedAt && <div><dt>조회</dt><dd>{formatDate(item.retrievedAt)}</dd></div>}{item.featureCutoffAt && <div><dt>기준시점</dt><dd>{formatDate(item.featureCutoffAt)}</dd></div>}</dl>}</article>
}
export default EvidenceQualityPage
