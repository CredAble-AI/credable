import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import Header from '../components/Header'
import { customerSessionProvider } from '../mocks/customerSessionProvider'
import { mockProductProvider } from '../mocks/productProvider'
import { mockAssessmentProvider } from '../mocks/assessmentProvider'
import type { ProductView } from '../types/product'
import './ProductComparisonPage.css'

function ProductDetailPage() {
  const { productId = '' } = useParams()
  const navigate = useNavigate()
  const [session] = useState(() => customerSessionProvider.get())
  const [product, setProduct] = useState<ProductView | null>(null)
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    if (!session) { navigate('/start', { replace: true }); return }
    const controller = new AbortController()
    const request = { sessionId: session.sessionId, profileType: session.selectedProfileType }
    void mockAssessmentProvider.get(request, controller.signal).then((assessment) => {
      if (assessment.canProceed !== true) { navigate('/assessment', { replace: true }); return null }
      return mockProductProvider.get(request, controller.signal)
    }).then((result) => { if (result) setProduct(result.products.find((item) => item.product.productId === productId) ?? null) }).catch(() => { if (!controller.signal.aborted) setProduct(null) }).finally(() => { if (!controller.signal.aborted) setLoaded(true) })
    return () => controller.abort()
  }, [navigate, productId, session])
  if (!session) return null
  return <div className="workspace-shell customer-flow"><Header /><main className="products-page"><div className="container"><section className="product-detail-placeholder" aria-labelledby="product-detail-title"><span className="products-badge">Mock mode · Demo Only</span>{!loaded ? <><h1 id="product-detail-title">상품을 확인하고 있습니다</h1><p role="status" aria-live="polite">현재 세션의 상품 정보를 다시 조회합니다.</p></> : product ? <><h1 id="product-detail-title">{product.product.productName}</h1><p>{product.condition.status === 'PERSONALIZED_AVAILABLE' ? '개인화 조회 결과가 있는 상품입니다.' : '공개 조건 또는 조회 상태가 제공된 상품입니다.'}</p><p>상품 상세는 다음 작업에서 구현합니다. 이 선택은 CredAble의 추천이나 대출 신청을 의미하지 않습니다.</p></> : <><h1 id="product-detail-title">상품을 찾을 수 없습니다</h1><p>현재 세션에 포함되지 않은 상품이거나 잘못된 상품 ID입니다.</p></>}<Link className="button button--primary" to="/products">상품 비교로 돌아가기</Link></section></div></main></div>
}
export default ProductDetailPage
