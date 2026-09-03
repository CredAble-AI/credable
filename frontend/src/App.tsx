import { useEffect, useRef } from 'react'
import { Link, Route, Routes } from 'react-router-dom'
import './App.css'
import Header from './components/Header'
import CaseStartPage from './pages/CaseStartPage'
import EligibilityPage from './pages/EligibilityPage'
import EvidencePage from './pages/EvidencePage'
import EvidenceQualityPage from './pages/EvidenceQualityPage'

const principles = [
  { number: '01', title: 'No Data ≠ Bad Credit', body: '데이터가 없다는 이유만으로 위험을 더 높게 판단하지 않습니다.' },
  { number: '02', title: '검증된 Evidence만 사용', body: '기준시점과 품질을 확인한 추가 증빙만 심사에 활용합니다.' },
  { number: '03', title: '최종 판단은 Underwriter', body: 'AI는 확정된 결과를 설명하고, 결정은 심사역이 내립니다.' },
]

const steps = [
  ['01', '거절 사유 확인', '현재 결정과 보완이 필요한 지점을 명확히 확인합니다.'],
  ['02', '필요한 증빙 추천', '서버에서 정한 기준에 따라 필요한 추가 자료를 안내합니다.'],
  ['03', '품질 검증', '제출된 증빙의 유효성과 기준시점을 확인합니다.'],
  ['04', '재심사 경로 안내', '확정된 결과를 바탕으로 다음 검토 경로를 설명합니다.'],
]

function BrandScene() {
  const sceneRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const scene = sceneRef.current
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)')
    const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)')
    if (!scene || reduceMotion.matches) return

    let targetX = 0
    let targetY = 0
    let currentX = 0
    let currentY = 0
    let scrollOffset = 0
    let frame = 0

    const render = () => {
      currentX += (targetX - currentX) * 0.06
      currentY += (targetY - currentY) * 0.06
      scene.style.setProperty('--tilt-x', `${currentY.toFixed(2)}deg`)
      scene.style.setProperty('--tilt-y', `${currentX.toFixed(2)}deg`)
      scene.style.setProperty('--parallax', `${scrollOffset.toFixed(1)}px`)
      scene.style.setProperty('--glow-parallax', `${(scrollOffset * 0.45).toFixed(1)}px`)
      frame = requestAnimationFrame(render)
    }
    const handlePointer = (event: PointerEvent) => {
      const bounds = scene.getBoundingClientRect()
      targetX = ((event.clientX - bounds.left) / bounds.width - 0.5) * 8
      targetY = -((event.clientY - bounds.top) / bounds.height - 0.5) * 8
    }
    const resetPointer = () => { targetX = 0; targetY = 0 }
    const handleScroll = () => { scrollOffset = Math.min(window.scrollY * 0.08, 38) }

    if (finePointer.matches) {
      scene.addEventListener('pointermove', handlePointer)
      scene.addEventListener('pointerleave', resetPointer)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    handleScroll()
    frame = requestAnimationFrame(render)
    return () => {
      cancelAnimationFrame(frame)
      scene.removeEventListener('pointermove', handlePointer)
      scene.removeEventListener('pointerleave', resetPointer)
      window.removeEventListener('scroll', handleScroll)
    }
  }, [])

  return (
    <div className="brand-scene" ref={sceneRef}>
      <div className="brand-glow" aria-hidden="true" />
      <div className="orbit orbit-one" aria-hidden="true" />
      <div className="orbit orbit-two" aria-hidden="true" />
      <div className="orbit orbit-three" aria-hidden="true" />
      <div className="brand-object">
        <img src="/brand/credable-mark-3d.png" width="1280" height="1280" alt="CredAble 3D 로고" />
      </div>
      <div className="brand-reflection" aria-hidden="true" />
      <div className="evidence-chip chip-one"><span aria-hidden="true">✓</span><div><small>Evidence</small><strong>Verified</strong></div></div>
      <div className="evidence-chip chip-two"><span aria-hidden="true">✓</span><div><small>Quality</small><strong>PASS</strong></div></div>
      <div className="evidence-chip chip-three"><span aria-hidden="true">→</span><div><small>Next step</small><strong>Underwriter review</strong></div></div>
    </div>
  )
}

function LandingPage() {
  return (
    <div className="site-shell">
      <Header />
      <main>
        <section className="hero" id="intro"><div className="container hero__grid">
          <div className="hero__content"><p className="eyebrow">AI Credit Second-Look</p><h1>거절 뒤에 남은<br />사업의 증거를<br /><span>다시 봅니다</span></h1><p className="hero__description">CredAble은 추가 증빙을 바탕으로 거절·보류된 대출 건의 재심사 가능성을 검토하도록 돕습니다.</p><div className="hero__actions"><Link className="button button--primary" to="/case">Second-Look 시작하기</Link><a className="button button--secondary" href="#process">작동 방식 보기</a></div><p className="demo-note"><span aria-hidden="true">ⓘ</span> Demo Only · 최종 판단은 심사역이 수행합니다</p></div>
          <BrandScene />
        </div></section>
        <section className="principles" id="principles" aria-labelledby="principles-title"><div className="container"><p className="section-label">OUR PRINCIPLES</p><h2 id="principles-title">빠른 답보다<br />바른 기준을 먼저 봅니다</h2><div className="principle-grid">{principles.map((item) => <article className="principle-card" key={item.number}><span>{item.number}</span><h3>{item.title}</h3><p>{item.body}</p></article>)}</div></div></section>
        <section className="process" id="process" aria-labelledby="process-title"><div className="container process__heading"><p className="section-label">HOW IT WORKS</p><h2 id="process-title">두 번째 승인이 아니라,<br /><span>두 번째 심사 기회</span></h2><p>확인부터 안내까지, 모든 단계는 검증 가능한 근거를 중심으로 이어집니다.</p></div><div className="container step-grid">{steps.map(([number, title, body]) => <article className="step-card" key={number}><span className="step-number">{number}</span><h3>{title}</h3><p>{body}</p></article>)}</div></section>
      </main>
      <footer><div className="container footer__inner"><strong>CredAble</strong><span>Demo Only · Second-Look for better review</span></div></footer>
    </div>
  )
}

function App() {
  return <Routes><Route path="/" element={<LandingPage />} /><Route path="/case" element={<CaseStartPage />} /><Route path="/eligibility" element={<EligibilityPage />} /><Route path="/evidence" element={<EvidencePage />} /><Route path="/evidence-quality" element={<EvidenceQualityPage />} /></Routes>
}
export default App
