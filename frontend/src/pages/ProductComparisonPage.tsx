import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { normalizeProductError } from '../api/productClient'
import Header from '../components/Header'
import { findDemoProfile } from '../data/demoProfiles'
import { customerSessionProvider } from '../mocks/customerSessionProvider'
import { mockAssessmentProvider } from '../mocks/assessmentProvider'
import { mockProductProvider } from '../mocks/productProvider'
import type { ApiError } from '../types/case'
import type { AnnualRateRange, MoneyAmount, ProductComparisonResult, ProductConditionStatus, ProductSortDirection, ProductSortField, ProductView, TermRangeMonths } from '../types/product'
import './ProductComparisonPage.css'

const provider = mockProductProvider
const statusCopy: Record<ProductConditionStatus, { label: string; icon: string; note: string }> = {
  PERSONALIZED_AVAILABLE: { label: '개인화 조건 조회 완료', icon: '✓', note: '연결 데이터와 은행 정책을 바탕으로 조회된 Demo 조건입니다. 최종 조건은 은행 심사 후 확정됩니다.' },
  PUBLIC_ONLY: { label: '공개 조건만 확인됨', icon: 'i', note: '은행이 공개한 상품 조건이며 개인별 조회 결과가 아닙니다.' },
  INSUFFICIENT_DATA: { label: '데이터 부족으로 산출 불가', icon: '○', note: '확인할 데이터가 부족해 개인화 조건을 산출하지 않았습니다. 이는 신용이나 대출 자격이 없다는 의미가 아닙니다.' },
  INELIGIBLE: { label: '자격조건 미충족', icon: '–', note: '은행이 확정한 상품별 상태이며 프론트엔드가 자격조건을 계산하지 않습니다.' },
  POLICY_NOT_CONFIGURED: { label: '상품 정책 확인 불가', icon: '!', note: '현재 환경에 개인화 조회 정책이 구성되지 않았습니다.' },
  QUERY_FAILED: { label: '상품 조건 조회 불가', icon: '!', note: '이 상품의 조건을 현재 조회할 수 없습니다. 다른 상품 결과는 계속 확인할 수 있습니다.' },
}
const formatMoney = (value: MoneyAmount | null) => value ? `${value.amount} ${value.currency}` : '산출 불가'
const formatRate = (value: AnnualRateRange | null) => value ? `연 ${value.minPercent}% ~ ${value.maxPercent}%` : '산출 불가'
const formatTerm = (value: TermRangeMonths | null) => value ? `${value.minMonths} ~ ${value.maxMonths}개월` : '확인되지 않음'
const formatDate = (value: string | null) => value ? new Intl.DateTimeFormat('ko-KR', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '확인되지 않음'

function ProductCard({ item }: { item: ProductView }) {
  const { product, condition } = item
  const copy = statusCopy[condition.status]
  const personalized = condition.status === 'PERSONALIZED_AVAILABLE'
  return <article className={`product-card product-card--${condition.status.toLowerCase()}`}>
    <header><span className="product-status"><b aria-hidden="true">{copy.icon}</b>{copy.label}</span><span className="demo-chip">Demo</span><h2>{product.productName}</h2><p>{product.eligibilitySummary}</p></header>
    <section aria-labelledby={`${product.productId}-public`}><h3 id={`${product.productId}-public`}>은행 공개 상품 조건</h3><dl><div><dt>공개 최대 한도</dt><dd>{formatMoney(product.publicMaxAmount)}</dd></div><div><dt>공개 금리 범위</dt><dd>{formatRate(product.annualRateRange)}</dd></div><div><dt>기간</dt><dd>{formatTerm(product.termRangeMonths)}</dd></div><div><dt>상환방식</dt><dd>{product.repaymentMethods.join(' · ') || '확인되지 않음'}</dd></div></dl></section>
    <section className="personalized-panel" aria-labelledby={`${product.productId}-personal`}><h3 id={`${product.productId}-personal`}>개인화 조회 조건</h3>{personalized ? <dl><div><dt>조회 한도</dt><dd>{formatMoney(condition.personalizedMaxAmount)}</dd></div><div><dt>조회 금리</dt><dd>{formatRate(condition.personalizedAnnualRateRange)}</dd></div><div><dt>조회 기간</dt><dd>{formatTerm(condition.personalizedTermRangeMonths)}</dd></div></dl> : <p className="condition-note">{copy.note}</p>}</section>
    <p className="product-note">{personalized ? copy.note : '공개 조건과 개인화 조회 결과를 구분해 확인해주세요.'}</p>
    <dl className="product-meta"><div><dt>조건 기준일</dt><dd>{product.officialSource.effectiveDate}</dd></div><div><dt>출처</dt><dd>{product.officialSource.sourceName}</dd></div><div><dt>정책 버전</dt><dd>{condition.policyVersion ?? '제공되지 않음'}</dd></div>{condition.reasonCode && <div><dt>상태 코드</dt><dd>{condition.reasonCode}</dd></div>}</dl>
    <Link className="product-detail-link" to={`/products/${encodeURIComponent(product.productId)}`}>{product.productName} 상세 보기</Link>
  </article>
}

function ProductComparisonPage() {
  const navigate = useNavigate()
  const [session] = useState(() => customerSessionProvider.get())
  const [result, setResult] = useState<ProductComparisonResult | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [sortField, setSortField] = useState<ProductSortField>('ORIGINAL')
  const [direction, setDirection] = useState<ProductSortDirection>('NONE')
  const controllerRef = useRef<AbortController | null>(null)
  const sequenceRef = useRef(0)
  const busyRef = useRef(false)
  const requiredComplete = session ? Object.values(session.consents.required).every(Boolean) : false

  useEffect(() => { if (!session) navigate('/start', { replace: true }); else if (!requiredComplete) navigate('/consent', { replace: true }) }, [navigate, requiredComplete, session])
  const load = useCallback(async (refresh = false) => {
    if (!session || !requiredComplete || busyRef.current) return
    busyRef.current = true
    controllerRef.current?.abort()
    const controller = new AbortController(); controllerRef.current = controller
    const sequence = ++sequenceRef.current
    setLoading(true); setError(null)
    try {
      const request = { sessionId: session.sessionId, profileType: session.selectedProfileType }
      const assessment = await mockAssessmentProvider.get(request, controller.signal)
      if (assessment.assessment.status === 'NOT_RUN') { navigate('/assessment', { replace: true }); return }
      const next = await (refresh ? provider.refresh(request, controller.signal) : provider.get(request, controller.signal))
      if (next.sessionId !== session.sessionId) throw { code: 'PRODUCT_SESSION_MISMATCH', message: '현재 세션의 상품 결과를 확인할 수 없습니다.', retryable: true } satisfies ApiError
      if (sequence === sequenceRef.current) { setResult(next); setSortField(next.defaultSort.field); setDirection(next.defaultSort.direction) }
    } catch (caught) { if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeProductError(caught)) }
    finally { if (sequence === sequenceRef.current) setLoading(false); busyRef.current = false }
  }, [navigate, requiredComplete, session])
  useEffect(() => { if (session && requiredComplete) queueMicrotask(() => void load()); return () => { sequenceRef.current += 1; controllerRef.current?.abort() } }, [load, requiredComplete, session])

  const option = result?.availableSortOptions.find((item) => item.field === sortField)
  const products = useMemo(() => {
    if (!result || sortField === 'ORIGINAL' || direction === 'NONE') return result?.products ?? []
    return result.products.map((item, index) => ({ item, index })).sort((left, right) => {
      const a = left.item.sortValues?.[sortField]; const b = right.item.sortValues?.[sortField]
      if (a == null && b == null) return left.index - right.index
      if (a == null) return 1
      if (b == null) return -1
      return (direction === 'ASC' ? a - b : b - a) || left.index - right.index
    }).map(({ item }) => item)
  }, [direction, result, sortField])
  const changeField = (field: ProductSortField) => { setSortField(field); setDirection(result?.availableSortOptions.find((item) => item.field === field)?.directions[0] ?? 'NONE') }
  if (!session || !requiredComplete) return null
  return <div className="workspace-shell customer-flow"><Header /><main className="products-page"><div className="container products-page__inner">
    <nav className="product-steps" aria-label="진행 단계"><span>시작</span><span>동의</span><span>데이터 연결</span><span>보완 평가</span><strong aria-current="step">상품 비교</strong></nav>
    <header className="products-heading"><div><span className="products-badge">Mock mode · Demo Only</span><p className="flow-kicker">OWN-BANK PRODUCT COMPARISON</p><h1>자사 대출상품 조건을 비교합니다</h1><p>현재 확인 가능한 상품 조건을 같은 기준으로 보여드립니다. 특정 상품을 권하거나 자동으로 선택하지 않으며, 정렬 기준과 상품은 고객이 직접 선택합니다.</p></div><aside><span>현재 Demo 프로필</span><strong>{findDemoProfile(session.selectedProfileType)?.name}</strong><small>합성 상품·조건이며 실제 승인 결과가 아닙니다.</small></aside></header>
    <div className="products-live" role="status" aria-live="polite">{loading ? '자사 상품 조건을 확인하고 있습니다.' : error ? '상품 조건을 확인하지 못했습니다.' : result?.canViewProducts ? `${products.length}개 상품 조건을 확인했습니다.` : '상품 비교를 진행할 수 없는 상태입니다.'}</div>
    {error && <section className="products-error" role="alert"><div><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div>{error.retryable && <button type="button" onClick={() => void load()}>다시 확인</button>}</section>}
    {loading && !result && <div className="product-skeletons" aria-hidden="true"><span /><span /><span /></div>}
    {result && !result.canViewProducts && <section className="products-blocked"><span aria-hidden="true">i</span><div><h2>현재 상품 비교를 진행할 수 없습니다</h2><p>{result.cannotProceedReason}</p><Link className="button button--primary" to="/assessment">보완 평가로 돌아가기</Link></div></section>}
    {result?.canViewProducts && <><section className="sort-panel" aria-labelledby="sort-title"><div><h2 id="sort-title">표시 순서 정렬</h2><p>조건을 평가하거나 순위를 매기지 않고 표시 순서만 바꿉니다.</p></div><div className="sort-controls"><label>정렬 기준<select value={sortField} onChange={(event) => changeField(event.target.value as ProductSortField)}>{result.availableSortOptions.map((item) => <option value={item.field} key={item.field}>{item.label}</option>)}</select></label><label>정렬 방향<select value={direction} onChange={(event) => setDirection(event.target.value as ProductSortDirection)} disabled={sortField === 'ORIGINAL'}>{option?.directions.map((item) => <option value={item} key={item}>{item === 'ASC' ? '오름차순' : item === 'DESC' ? '내림차순' : '원본 순서'}</option>)}</select></label></div><p className="current-sort" aria-live="polite">현재 정렬: {option?.label ?? '기본 순서'}{direction !== 'NONE' ? ` · ${direction === 'ASC' ? '오름차순' : '내림차순'}` : ''} · 값 없음은 마지막</p></section>{result.queryStatus === 'PARTIAL' && <p className="partial-notice">일부 상품 조건을 조회하지 못했습니다. 확인된 상품 결과는 그대로 유지합니다.</p>}<section className="product-grid" aria-label="자사 대출상품 비교 결과">{products.map((item) => <ProductCard item={item} key={item.product.productId} />)}</section><footer className="products-meta"><span>결과 기준시점 {formatDate(result.resultAt)}</span><span>출처 {result.sourceName ?? 'Backend product APIs'}</span><span>카탈로그 {result.catalogVersion ?? '확인되지 않음'}</span><button type="button" onClick={() => void load(true)} disabled={loading}>전체 조건 다시 확인</button></footer></>}
  </div></main></div>
}
export default ProductComparisonPage
