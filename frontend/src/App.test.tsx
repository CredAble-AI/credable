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
  })

  it('renders the recovery links for an unknown route', () => {
    renderRoute('/missing-route')

    expect(screen.getByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '새 평가 시작' })).toHaveAttribute('href', '/start')
  })
})
