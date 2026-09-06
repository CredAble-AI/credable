import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { liveAssessmentProvider } from '../api/assessmentClient'
import { liveProductProvider, normalizeProductError } from '../api/productClient'
import Header from '../components/Header'
import { selectProvider } from '../config/providerMode'
import { useCustomerSession } from '../hooks/useCustomerSession'
import { mockAssessmentProvider } from '../mocks/assessmentProvider'
import { mockProductProvider } from '../mocks/productProvider'
import type { ApiError } from '../types/api'
import type { ProductView } from '../types/product'
import './ApplicationHandoffPage.css'

const assessmentProvider = selectProvider(mockAssessmentProvider, liveAssessmentProvider)
const productProvider = selectProvider(mockProductProvider, liveProductProvider)

const safeHttpsUrl = (value: string | null) => {
  if (!value) return null
  try { const url = new URL(value); return url.protocol === 'https:' ? url.href : null } catch { return null }
}
const formatDateTime = (value: string) => new Intl.DateTimeFormat('ko-KR', { dateStyle: 'long', timeStyle: 'short' }).format(new Date(value))

function ApplicationHandoffPage() {
  const { productId = '' } = useParams(); const navigate = useNavigate()
  const { session, loading: sessionLoading } = useCustomerSession(); const [product, setProduct] = useState<ProductView | null>(null)
  const [loading, setLoading] = useState(true); const [error, setError] = useState<ApiError | null>(null); const [leaving, setLeaving] = useState(false)
  const controllerRef = useRef<AbortController | null>(null); const sequenceRef = useRef(0); const busyRef = useRef(false)
  useEffect(() => { if (!sessionLoading && !session) navigate('/start', { replace: true }) }, [navigate, session, sessionLoading])
  const load = useCallback(async () => {
    if (!session || busyRef.current) return
    busyRef.current = true; controllerRef.current?.abort(); const controller = new AbortController(); controllerRef.current = controller; const sequence = ++sequenceRef.current; setLoading(true); setError(null)
    try {
      const request = { sessionId: session.sessionId, profileType: session.selectedProfileType }
      const assessment = await assessmentProvider.get(request, controller.signal)
      if (assessment.assessment.status !== 'COMPLETED') { navigate('/assessment', { replace: true }); return }
      const result = await productProvider.get(request, controller.signal)
      if (result.sessionId !== session.sessionId) throw { code: 'PRODUCT_SESSION_MISMATCH', message: '현재 세션의 상품 결과를 확인할 수 없습니다.', retryable: false } satisfies ApiError
      if (sequence === sequenceRef.current) setProduct(result.products.find((item) => item.product.productId === productId) ?? null)
    } catch (caught) { if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeProductError(caught)) }
    finally { if (sequence === sequenceRef.current) setLoading(false); busyRef.current = false }
  }, [navigate, productId, session])
  useEffect(() => { if (session) queueMicrotask(() => void load()); return () => { sequenceRef.current += 1; controllerRef.current?.abort() } }, [load, session])
  if (sessionLoading || !session) return null
  const externalUrl = product?.applicationLinkAvailable ? safeHttpsUrl(product.applicationUrl) : null
  const continueToBank = () => { if (!externalUrl || leaving) return; setLeaving(true); window.location.assign(externalUrl) }
  return <div className="workspace-shell customer-flow"><Header /><main id="main-content" tabIndex={-1} className="handoff-page"><div className="container handoff-page__inner"><Link className="handoff-back" to={product ? `/products/${encodeURIComponent(product.product.productId)}` : '/products'}>← 상품 상세로 돌아가기</Link><div className="handoff-live" role="status" aria-live="polite">{loading ? '신청 연결 정보를 확인하고 있습니다.' : error ? '신청 연결 정보를 확인하지 못했습니다.' : '신청 연결 안내를 확인했습니다.'}</div>{error && <section className="handoff-error" role="alert"><strong>{error.message}</strong><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small>{error.retryable && <button type="button" onClick={() => void load()}>다시 확인</button>}</section>}{!loading && !error && !product && <section className="handoff-card"><span aria-hidden="true">i</span><h1>상품을 찾을 수 없습니다</h1><p>현재 세션의 상품인지 다시 확인해주세요.</p><Link className="button button--primary" to="/products">상품 비교로 돌아가기</Link></section>}{product && <section className="handoff-card" aria-labelledby="handoff-title"><span aria-hidden="true">→</span><p className="handoff-kicker">은행 신청 연결 안내</p><h1 id="handoff-title">{product.product.productName}</h1><p>은행 신청 절차로 이동하기 전 확인 단계입니다. 현재 확인한 조건은 실제 심사 결과나 최종 약정 조건이 아닙니다.</p><p className="handoff-basis">{product.product.personalizedConditions ? `개인화 조회 기준시점: ${formatDateTime(product.product.personalizedConditions.queriedAt)}` : `공개 조건 기준일: ${product.product.officialSource.effectiveDate}`}</p><ul><li>계속하면 CredAble을 벗어나 은행의 별도 절차로 이동할 수 있습니다.</li><li>개인정보, 원시 금융정보와 세션 식별자를 URL에 추가하지 않습니다.</li><li>외부 이동 자체를 신청 처리 결과로 기록하지 않습니다.</li></ul>{externalUrl ? <div className="handoff-availability"><strong>은행 신청 연결을 사용할 수 있습니다</strong><p>고객이 계속하기를 선택한 경우에만 HTTPS 주소로 이동합니다.</p></div> : <div className="handoff-availability handoff-availability--unavailable"><strong>연결 방식 준비 중</strong><p>현재는 실제 은행 신청 연결을 제공하지 않습니다.</p></div>}<div className="handoff-actions"><Link className="button button--secondary" to={`/products/${encodeURIComponent(product.product.productId)}`}>상품 상세로 돌아가기</Link><button className="button button--primary" type="button" onClick={continueToBank} disabled={!externalUrl || leaving}>{leaving ? '이동 준비 중…' : '계속하기'}</button></div></section>}</div></main></div>
}
export default ApplicationHandoffPage
