import { Link } from 'react-router-dom'
import Header from '../components/Header'

function EvidenceQualityPage() {
  return <div className="workspace-shell"><Header /><main className="placeholder-page"><div className="container"><p className="eyebrow">NEXT STEP</p><h1>Evidence 품질 확인</h1><p>증빙 품질 검토 화면은 다음 작업에서 구현됩니다.</p><Link className="button button--primary" to="/evidence">추천 증빙으로 돌아가기</Link></div></main></div>
}
export default EvidenceQualityPage
