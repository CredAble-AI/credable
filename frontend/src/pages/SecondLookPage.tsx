import { Link } from 'react-router-dom'
import Header from '../components/Header'

function SecondLookPage() {
  return <div className="workspace-shell"><Header /><main className="placeholder-page"><div className="container"><p className="eyebrow">NEXT STEP</p><h1>Second-Look 경로 확인</h1><p>서버가 판단한 다음 경로를 보여주는 화면은 다음 작업에서 구현됩니다.</p><Link className="button button--primary" to="/evidence-quality">품질 결과로 돌아가기</Link></div></main></div>
}
export default SecondLookPage
