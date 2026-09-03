import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Header from '../components/Header'
import { normalizeEligibilityError } from '../api/eligibilityClient'
import { mockEligibilityProvider } from '../mocks/eligibilityProvider'
import type { ApiError, EligibilityClass, EligibilityResult, SecondLookCase } from '../types/case'
import './EligibilityPage.css'

const provider = mockEligibilityProvider

const resultCopy: Record<EligibilityClass, { eyebrow: string; title: string; description: string; cta: string }> = {
  SECOND_LOOK_ELIGIBLE: { eyebrow: 'SECOND-LOOK AVAILABLE', title: '추가 증빙으로 다시 검토할 수 있습니다', description: '현재 결과는 승인이 아니라 Second-Look 절차에 진입할 수 있다는 의미입니다.', cta: '필요한 증빙 확인하기' },
  DATA_QUALITY_ISSUE: { eyebrow: 'MORE INFORMATION NEEDED', title: '판단을 위해 확인할 정보가 더 필요합니다', description: '데이터가 부족하다는 사실은 신용이 나쁘거나 위험도가 높아졌다는 의미가 아닙니다.', cta: '보완할 증빙 확인하기' },
  HARD_DECLINE: { eyebrow: 'SECOND-LOOK LIMITED', title: '현재 Case는 Second-Look 대상이 아닙니다', description: '정책 또는 컴플라이언스 제한에 따라 기존 결정이 유지됩니다.', cta: '' },
}

function StatusIcon({ classification }: { classification: EligibilityClass }) {
  if (classification === 'HARD_DECLINE') return <span className="result-icon" aria-hidden="true">—</span>
  if (classification === 'DATA_QUALITY_ISSUE') return <span className="result-icon" aria-hidden="true">!</span>
  return <span className="result-icon" aria-hidden="true">✓</span>
}

function EligibilityPage() {
  const navigate = useNavigate()
  const caseId = sessionStorage.getItem('credable.caseId')
  const [caseSummary, setCaseSummary] = useState<SecondLookCase | null>(null)
  const [result, setResult] = useState<EligibilityResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [requestVersion, setRequestVersion] = useState(0)
  const requestingRef = useRef(false)

  const loadEligibility = useCallback(async (signal: AbortSignal) => {
    if (!caseId || requestingRef.current) return
    requestingRef.current = true
    setError(null)
    setResult(null)
    try {
      const [nextCase, nextResult] = await Promise.all([provider.getCase(caseId, signal), provider.check({ caseId }, signal)])
      if (signal.aborted) return
      setCaseSummary(nextCase)
      setResult(nextResult)
    } catch (caughtError) {
      if (!signal.aborted) setError(normalizeEligibilityError(caughtError))
    } finally {
      requestingRef.current = false
    }
  }, [caseId])

  useEffect(() => {
    if (!caseId) { navigate('/case', { replace: true }); return }
    const controller = new AbortController()
    queueMicrotask(() => { if (!controller.signal.aborted) void loadEligibility(controller.signal) })
    return () => controller.abort()
  }, [caseId, loadEligibility, navigate, requestVersion])

  const retry = () => { if (!requestingRef.current) setRequestVersion((version) => version + 1) }

  if (!caseId) return null

  return (
    <div className="workspace-shell">
      <Header />
      <main className="eligibility-page">
        <div className="container eligibility-layout">
          <header className="workflow-heading"><div className="demo-badge"><span aria-hidden="true" />Mock mode · Demo Only</div><p className="step-kicker">Second-Look workflow</p><div className="current-step"><span>현재 단계</span><strong>Eligibility</strong></div></header>
          {caseSummary && <section className="case-summary" aria-labelledby="case-summary-title"><div><p className="section-kicker">CASE SUMMARY</p><h1 id="case-summary-title">검토 Case</h1></div><dl><div><dt>기존 결정</dt><dd><span className={`decision decision--${caseSummary.currentDecision.toLowerCase()}`}>{caseSummary.currentDecision === 'HELD' ? '보류' : '거절'}</span></dd></div><div><dt>신청 상품</dt><dd>{caseSummary.application.productType}</dd></div><div><dt>신청일</dt><dd>{new Intl.DateTimeFormat('ko-KR').format(new Date(caseSummary.applicationDate))}</dd></div><div><dt>Reason</dt><dd>{caseSummary.declineReasonCodes.join(' · ')}</dd></div></dl></section>}
          {!result && !error && <section className="eligibility-loading" role="status" aria-live="polite"><div className="loading-orbit" aria-hidden="true"><span /></div><h1>재심사 진입 가능성을 확인하고 있습니다</h1><p>서버에서 Case와 정책 기준을 확인하는 중입니다.</p><div className="loading-lines" aria-hidden="true"><span /><span /><span /></div></section>}
          {error && <section className="eligibility-error" role="alert"><span className="error-mark" aria-hidden="true">!</span><p className="section-kicker">CHECK INTERRUPTED</p><h1>결과를 확인하지 못했습니다</h1><p>{error.message}</p><small>오류 코드: {error.code}{error.requestId ? ` · 요청 ID: ${error.requestId}` : ''}</small><div className="result-actions">{error.retryable && <button className="button button--primary" type="button" onClick={retry}>다시 확인하기</button>}<Link className="button button--secondary" to="/case">Case 선택으로 돌아가기</Link></div></section>}
          {result && <ResultPanel result={result} />}
        </div>
      </main>
    </div>
  )
}

function ResultPanel({ result }: { result: EligibilityResult }) {
  const copy = resultCopy[result.classification]
  const isHardDecline = result.classification === 'HARD_DECLINE'
  return <section className={`eligibility-result result--${result.classification.toLowerCase()}`} aria-labelledby="result-title"><StatusIcon classification={result.classification} /><p className="section-kicker">{copy.eyebrow}</p><h1 id="result-title">{copy.title}</h1><p className="result-description">{copy.description}</p><div className="reason-panel"><h2>확인된 이유</h2><ul>{result.reasons.map((reason) => <li key={reason}><span aria-hidden="true">✓</span>{reason}</li>)}</ul>{result.classification === 'DATA_QUALITY_ISSUE' && <p className="quality-note"><strong>No Data ≠ Bad Credit</strong>부족한 정보는 자동 감점되지 않습니다.</p>}{result.hardStops.length > 0 && <div className="hard-stop-list"><h2>제한 사유</h2><ul>{result.hardStops.map((stop) => <li key={stop}>{stop}</li>)}</ul></div>}</div><div className="result-actions">{isHardDecline ? <><Link className="button button--primary" to="/case">다른 Case 살펴보기</Link><p className="contact-note">일반 문의는 담당 금융기관의 상담 채널을 이용해주세요.</p></> : <Link className="button button--primary" to="/evidence">{copy.cta}</Link>}</div></section>
}

export default EligibilityPage
