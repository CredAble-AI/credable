import { Link } from 'react-router-dom'
import Header from '../components/Header'
import './NotFoundPage.css'

function NotFoundPage() {
  return <div className="workspace-shell customer-flow"><Header /><main className="not-found-page"><section aria-labelledby="not-found-title"><span aria-hidden="true">404</span><h1 id="not-found-title">페이지를 찾을 수 없습니다</h1><p>요청한 화면이 없거나 새로운 서비스 흐름으로 변경되었습니다.</p><div><Link className="button button--secondary" to="/">서비스 소개로 이동</Link><Link className="button button--primary" to="/start">새 평가 시작</Link></div></section></main></div>
}

export default NotFoundPage
