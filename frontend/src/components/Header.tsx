function Header() {
  return (
    <header className="header">
      <div className="container header__inner">
        <a className="wordmark" href="#intro" aria-label="CredAble 홈">
          <img src="/brand/credable-mark-3d.png" width="36" height="36" alt="" />
          <span>Cred<strong>Able</strong></span>
        </a>
        <nav aria-label="주요 메뉴">
          <a href="#principles">서비스 소개</a>
          <a href="#process">작동 방식</a>
        </nav>
        <a className="button button--small" href="#process">데모 시작</a>
      </div>
    </header>
  )
}
export default Header
