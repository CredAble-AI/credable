import { useEffect, useRef } from 'react'
import { useLocation } from 'react-router-dom'

const resolvePageName = (pathname: string) => {
  if (pathname === '/') return '서비스 소개'
  if (pathname === '/start') return '사업자 유형 선택'
  if (pathname === '/consent') return '데이터 이용 동의'
  if (pathname === '/data-connection') return '데이터 연결'
  if (pathname === '/assessment') return '기준평가'
  if (pathname === '/evidence') return '최소 증빙'
  if (pathname === '/products') return '상품 조건 비교'
  if (pathname === '/admin/reviews') return '심사역 검토 목록'
  if (/^\/admin\/reviews\/[^/]+$/.test(pathname)) return '심사역 검토 상세'
  if (/^\/products\/[^/]+\/apply$/.test(pathname)) return '은행 신청 연결 안내'
  if (/^\/products\/[^/]+$/.test(pathname)) return '상품 상세'
  return '페이지를 찾을 수 없습니다'
}

function RouteAnnouncement() {
  const { pathname } = useLocation()
  const previousPathRef = useRef<string | null>(null)
  const pageName = resolvePageName(pathname)

  useEffect(() => {
    document.title = `${pageName} | CredAble`

    if (previousPathRef.current !== null && previousPathRef.current !== pathname) {
      document.getElementById('main-content')?.focus({ preventScroll: true })
    }
    previousPathRef.current = pathname
  }, [pageName, pathname])

  return (
    <p className="sr-only" role="status" aria-atomic="true">{`${pageName} 화면으로 이동했습니다.`}</p>
  )
}

export default RouteAnnouncement
