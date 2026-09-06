import { Link, Outlet } from 'react-router-dom'
import { isMockMode } from '../config/providerMode'
import '../pages/AdminReviewListPage.css'

function AdminShell() {
  return <div className="admin-shell"><a className="skip-link" href="#main-content">본문 바로가기</a><header className="admin-header"><Link to="/admin/reviews" className="admin-brand"><span>CredAble</span> Admin</Link><div><span className="admin-mode">{isMockMode ? 'Mock' : 'Live'} · 합성 Demo 전용</span><Link to="/">고객 화면</Link></div></header><Outlet /></div>
}

export default AdminShell
