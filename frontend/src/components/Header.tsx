import { Link } from 'react-router-dom'

function Header() {
  return (
    <header className="header">
      <a className="skip-link" href="#main-content">본문 바로가기</a>
      <div className="container header__inner">
        <Link className="wordmark" to="/" aria-label="CredAble 홈">
          <img src="/brand/credable-mark-3d.png" width="36" height="36" alt="" />
          <span>Cred<strong>Able</strong></span>
        </Link>
        <nav aria-label="주요 메뉴">
          <a href="/#principles">서비스 소개</a>
          <a href="/#process">작동 방식</a>
        </nav>
        <Link className="button button--small" to="/start">조회 시작</Link>
      </div>
    </header>
  )
}
export default Header
