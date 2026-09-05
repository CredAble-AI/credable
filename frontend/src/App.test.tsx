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

    expect(screen.getByRole('heading', { level: 1, name: /대출 조건을 한눈에 비교합니다/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '평가·상품조건 조회 시작' })).toHaveAttribute('href', '/start')
  })

  it('renders the recovery links for an unknown route', () => {
    renderRoute('/missing-route')

    expect(screen.getByRole('heading', { level: 1, name: '페이지를 찾을 수 없습니다' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '새 평가 시작' })).toHaveAttribute('href', '/start')
  })
})
