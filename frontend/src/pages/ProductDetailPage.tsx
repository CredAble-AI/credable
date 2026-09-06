import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { liveAssessmentProvider } from '../api/assessmentClient'
import { liveProductProvider, normalizeProductError } from '../api/productClient'
import CustomerTechnicalDetails from '../components/CustomerTechnicalDetails'
import Header from '../components/Header'
import { selectProvider } from '../config/providerMode'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { mockAssessmentProvider } from '../mocks/assessmentProvider'
import { mockProductProvider } from '../mocks/productProvider'
import type { ApiError } from '../types/api'
import type { AnnualRateRange, MoneyAmount, ProductConditionStatus, ProductView, TermRangeMonths } from '../types/product'
import './ProductDetailPage.css'

const provider = selectProvider(mockProductProvider, liveProductProvider)
const assessmentProvider = selectProvider(mockAssessmentProvider, liveAssessmentProvider)
const statusCopy: Record<ProductConditionStatus, { label: string; icon: string; message: string }> = {
  PERSONALIZED_AVAILABLE: { label: '개인화 조건 조회 완료', icon: '✓', message: '현재 연결된 데이터와 은행 정책을 바탕으로 조회한 조건입니다. 최종 한도와 금리는 은행 심사 후 확정됩니다.' },
  PUBLIC_ONLY: { label: '공개 조건만 확인됨', icon: 'i', message: '은행이 공개한 일반 상품 조건입니다. 고객별 조회 결과가 아닙니다.' },
  INELIGIBLE: { label: '상품별 자격조건 미충족', icon: '–', message: '은행이 확정한 이 상품의 상태입니다. 다른 상품의 상태를 의미하지 않습니다.' },
  INSUFFICIENT_DATA: { label: '추가 확인 필요', icon: '○', message: '현재 확인된 데이터만으로는 이 상품의 조건을 확인할 수 없습니다. 이는 신용이 낮거나 대출 자격이 없다는 의미가 아닙니다.' },
  POLICY_NOT_CONFIGURED: { label: '상품 정책 확인 불가', icon: '!', message: '현재 이 상품의 확인 정책을 구성할 수 없습니다.' },
  QUERY_FAILED: { label: '상품 조건 조회 실패', icon: '!', message: '이 상품의 조건을 현재 조회할 수 없습니다. 확인되지 않은 값으로 대체하지 않습니다.' },
}
const money = (value: MoneyAmount | null) => value ? `${value.amount} ${value.currency}` : '확인되지 않음'
const rate = (value: AnnualRateRange | null) => value ? `연 ${value.minPercent}% ~ ${value.maxPercent}%` : '확인되지 않음'
const term = (value: TermRangeMonths | null) => value ? `${value.minMonths} ~ ${value.maxMonths}개월` : '확인되지 않음'

function DetailContent({ item, onRetry, busy }: { item: ProductView; onRetry: () => void; busy: boolean }) {
  const { product } = item
  const status = product.conditionStatus ? statusCopy[product.conditionStatus] : statusCopy.PUBLIC_ONLY
  return <>
    <header className="detail-heading"><Link to="/products" className="detail-back">← 상품 비교로 돌아가기</Link><div className="detail-heading__badges"><span className={`detail-status detail-status--${(product.conditionStatus ?? 'PUBLIC_ONLY').toLowerCase()}`}><b aria-hidden="true">{status.icon}</b>{status.label}</span></div><h1>{product.productName}</h1><p>은행이 공개한 상품 조건과 현재 확인 상태입니다. 개인별 한도와 금리는 이 서비스가 산출하지 않으며 은행의 정식 심사와 약정 과정에서 확정됩니다.</p></header>
    <section className="detail-notice" aria-labelledby="detail-status-title"><span aria-hidden="true">{status.icon}</span><div><h2 id="detail-status-title">현재 상품 결과 상태</h2><p>{status.message}</p>{product.conditionStatus === 'QUERY_FAILED' && <button type="button" onClick={onRetry} disabled={busy}>{busy ? '다시 조회 중…' : '상품 조건 다시 조회'}</button>}</div></section>
    <div className="detail-grid">
      <section className="detail-card"><p className="detail-card__number">01</p><h2>기본 상품 정보</h2><dl><div><dt>상품명</dt><dd>{product.productName}</dd></div><div><dt>가입 대상·주요 조건</dt><dd>{product.eligibilitySummary}</dd></div><div><dt>신청 안내</dt><dd>{product.applicationReference ?? '은행 심사 후 확인'}</dd></div></dl></section>
      <section className="detail-card"><p className="detail-card__number">02</p><h2>금리 정보</h2><dl><div><dt>은행 공개 금리 범위</dt><dd aria-label={`은행 공개 금리 범위 ${rate(product.publicConditions.annualRateRange)}`}>{rate(product.publicConditions.annualRateRange)}</dd></div><div><dt>공개 조건 기준일</dt><dd>{product.officialSource.effectiveDate}</dd></div><div><dt>개인별 금리</dt><dd>은행 심사에서 확정 · 이 서비스에서 산출하지 않음</dd></div></dl></section>
      <section className="detail-card"><p className="detail-card__number">03</p><h2>한도 정보</h2><dl><div><dt>은행 공개 최대 한도</dt><dd aria-label={`은행 공개 최대 한도 ${money(product.publicConditions.maxAmount)}`}>{money(product.publicConditions.maxAmount)}</dd></div><div><dt>개인별 한도</dt><dd>은행 심사에서 확정 · 이 서비스에서 산출하지 않음</dd></div><div><dt>현재 상태 안내</dt><dd>{status.message}</dd></div></dl></section>
      <section className="detail-card"><p className="detail-card__number">04</p><h2>이용 조건</h2><dl><div><dt>은행 공개 기간</dt><dd>{term(product.publicConditions.termRangeMonths)}</dd></div><div><dt>상환방식</dt><dd>{product.publicConditions.repaymentMethods.join(' · ') || '확인되지 않음'}</dd></div><div><dt>수수료·중도상환·필요 자료</dt><dd>은행 심사 후 확인</dd></div></dl></section>
    </div>
    <section className="detail-source" aria-labelledby="detail-source-title"><div><h2 id="detail-source-title">출처와 기준 정보</h2><p>화면에 표시된 공개 조건의 출처와 기준일을 확인해주세요.</p></div><dl><div><dt>출처</dt><dd>{product.officialSource.sourceName}</dd></div><div><dt>출처 기준일</dt><dd>{product.officialSource.effectiveDate}</dd></div><div><dt>최종 은행 확인</dt><dd>{product.finalApprovalRequired ? '필요' : '확인되지 않음'}</dd></div></dl><CustomerTechnicalDetails><dl><div><dt>상품 버전</dt><dd><code>{product.productVersion}</code></dd></div>{product.conditionReasonCode && <div><dt>상태 코드</dt><dd><code>{product.conditionReasonCode}</code></dd></div>}</dl></CustomerTechnicalDetails></section>
    <section className="detail-actions" aria-label="상품 상세 다음 작업"><div><strong>이 화면 진입은 특정 상품에 대한 권유를 의미하지 않습니다</strong><p>실제 은행 연결 전 안내 사항을 먼저 확인할 수 있습니다.</p></div><div><Link className="button button--secondary" to="/products">다른 상품과 비교</Link><Link className="button button--primary" to={`/products/${encodeURIComponent(product.productId)}/apply`}>신청 연결 안내 확인</Link></div></section>
  </>
}

function ProductDetailPage() {
  const { productId = '' } = useParams(); const navigate = useNavigate()
  const { session, loading: sessionLoading } = useCustomerSession()
  const [product, setProduct] = useState<ProductView | null>(null); const [error, setError] = useState<ApiError | null>(null); const [loading, setLoading] = useState(true)
  const controllerRef = useRef<AbortController | null>(null); const sequenceRef = useRef(0); const busyRef = useRef(false)
  useEffect(() => { if (!sessionLoading && !session) navigate('/start', { replace: true }) }, [navigate, session, sessionLoading])
  const load = useCallback(async (refresh = false) => {
    if (!session || busyRef.current) return
    busyRef.current = true; controllerRef.current?.abort(); const controller = new AbortController(); controllerRef.current = controller; const sequence = ++sequenceRef.current
    setLoading(true); setError(null)
    try {
      const request = { sessionId: session.sessionId, profileType: session.selectedProfileType }
      const assessment = await assessmentProvider.get(request, controller.signal)
      if (assessment.assessment.status !== 'COMPLETED') { navigate('/assessment', { replace: true }); return }
      const result = await (refresh ? provider.refresh(request, controller.signal) : provider.get(request, controller.signal))
      if (result.sessionId !== session.sessionId) throw { code: 'PRODUCT_SESSION_MISMATCH', message: '현재 세션의 상품 결과를 확인할 수 없습니다.', retryable: false } satisfies ApiError
      if (!result.canViewProducts) { navigate('/products', { replace: true }); return }
      if (sequence === sequenceRef.current) setProduct(result.products.find((item) => item.product.productId === productId) ?? null)
    } catch (caught) { if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeProductError(caught)) }
    finally { if (sequence === sequenceRef.current) setLoading(false); busyRef.current = false }
  }, [navigate, productId, session])
  useEffect(() => { if (session) queueMicrotask(() => void load()); return () => { sequenceRef.current += 1; controllerRef.current?.abort() } }, [load, session])
  if (sessionLoading || !session) return null
  return <div className="workspace-shell customer-flow"><Header /><main id="main-content" tabIndex={-1} className="product-detail-page"><div className="container product-detail-page__inner"><nav className="detail-steps" aria-label="진행 단계"><span>시작</span><span>동의</span><span>데이터 연결</span><span>기존 평가</span><strong>상품 비교</strong><em aria-current="page">상품 상세</em></nav><div className="detail-live" role="status" aria-live="polite">{loading ? '선택한 상품의 현재 조건을 확인하고 있습니다.' : error ? '상품 상세를 확인하지 못했습니다.' : product ? '상품 상세 조건을 확인했습니다.' : '현재 세션에서 상품을 찾을 수 없습니다.'}</div>{error && <section className="detail-error" role="alert"><div><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small></div>{error.retryable && <button type="button" onClick={() => void load()}>다시 확인</button>}</section>}{loading && !product && <div className="detail-skeleton" aria-hidden="true"><span /><span /></div>}{!loading && !error && !product && <section className="detail-empty"><h1>상품을 찾을 수 없습니다</h1><p>현재 세션에 포함되지 않은 상품이거나 잘못된 상품 ID입니다.</p><Link className="button button--primary" to="/products">상품 비교로 돌아가기</Link></section>}{product && <DetailContent item={product} onRetry={() => void load(true)} busy={loading} />}</div></main></div>
}
export default ProductDetailPage
