import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from './App'

const renderRoute = (route: string) => render(
  <MemoryRouter initialEntries={[route]}>
    <App />
  </MemoryRouter>,
)

describe('App routing', () => {
  it('renders the customer journey entry point', () => {
    renderRoute('/')

    expect(screen.getByRole('heading', { level: 1, name: /더 묻지 않고.*최소 증빙만 확인합니다/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Demo 평가 시작' })).toHaveAttribute('href', '/start')
    expect(screen.getByRole('heading', { level: 3, name: '필요한 증빙만 요청' })).toBeInTheDocument()
    expect(screen.getByText(/불확실성이나 이상 징후가 남으면 심사역 검토가 필요함을 안내합니다/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '본문 바로가기' })).toHaveAttribute('href', '#main-content')
    expect(document.querySelector('main')).toHaveAttribute('id', 'main-content')
    expect(document.querySelector('main')).toHaveAttribute('tabindex', '-1')
  })

  it('renders the recovery links for an unknown route', () => {
    renderRoute('/missing-route')

    expect(screen.getByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '새 평가 시작' })).toHaveAttribute('href', '/start')
  })

  it('renders the separate administrator review route', () => {
    renderRoute('/admin/reviews')

    expect(screen.getByRole('heading', { level: 1, name: '심사역 검토 목록' })).toBeInTheDocument()
    expect(screen.getByLabelText('관리자 Demo API Key')).toHaveAttribute('type', 'password')
    expect(screen.getByRole('link', { name: '본문 바로가기' })).toHaveAttribute('href', '#main-content')
    expect(screen.queryByRole('link', { name: 'CredAble 홈' })).not.toBeInTheDocument()
  })

  it('renders a directly-addressable administrator review detail route', () => {
    renderRoute('/admin/reviews/uwr_demo')

    expect(screen.getByRole('heading', { level: 1, name: '심사역 검토 상세' })).toBeInTheDocument()
    expect(screen.getByLabelText('관리자 Demo API Key')).toHaveAttribute('type', 'password')
    expect(document.title).toBe('심사역 검토 상세 | CredAble')
  })

  it('renders a directly-addressable session audit route', () => {
    renderRoute('/admin/sessions/ses_demo/audit')

    expect(screen.getByRole('heading', { level: 1, name: '세션 처리 이력' })).toBeInTheDocument()
    expect(screen.getByLabelText('관리자 Demo API Key')).toHaveAttribute('type', 'password')
    expect(document.title).toBe('세션 처리 이력 | CredAble')
  })

  it('renders a directly-addressable evidence burden route', () => {
    renderRoute('/admin/sessions/ses_demo/evidence-burden')

    expect(screen.getByRole('heading', { level: 1, name: 'Evidence 요청 부담 지표' })).toBeInTheDocument()
    expect(screen.getByLabelText('관리자 Demo API Key')).toHaveAttribute('type', 'password')
    expect(document.title).toBe('Evidence 요청 부담 지표 | CredAble')
  })
})
