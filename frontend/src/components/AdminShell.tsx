import { Link, Outlet } from 'react-router-dom'
import { isMockMode } from '../config/providerMode'
import { useAdminAuth } from '../hooks/useAdminAuth'
import '../pages/AdminReviewListPage.css'
import AdminAuthProvider from './AdminAuthProvider'

function AdminFrame() {
  const { apiKey, clear } = useAdminAuth()
  return <div className="admin-shell"><header className="admin-header"><Link to="/admin/reviews" className="admin-brand"><span>CredAble</span> Admin</Link><div>{isMockMode && <span className="admin-mode">Mock · Demo Only</span>}<Link to="/">고객 화면</Link>{apiKey && <button type="button" onClick={clear}>관리자 키 지우기</button>}</div></header><Outlet /></div>
}

function AdminShell() {
  return <AdminAuthProvider><AdminFrame /></AdminAuthProvider>
}

export default AdminShell
