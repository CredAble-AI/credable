import { fireEvent, render, screen } from '@testing-library/react'
import { Link, MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import RouteAnnouncement from './RouteAnnouncement'

describe('RouteAnnouncement', () => {
  it('sets a route-specific document title and accessible announcement', () => {
    render(
      <MemoryRouter initialEntries={['/evidence']}>
        <RouteAnnouncement />
      </MemoryRouter>,
    )

    expect(document.title).toBe('최소 증빙 | CredAble')
    expect(screen.getByRole('status')).toHaveTextContent('최소 증빙 화면으로 이동했습니다.')
  })

  it('moves focus to the main content after an in-app route change', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <RouteAnnouncement />
        <Link to="/assessment">기준평가로 이동</Link>
        <main id="main-content" tabIndex={-1}>현재 화면 본문</main>
      </MemoryRouter>,
    )

    const main = screen.getByRole('main')
    expect(main).not.toHaveFocus()

    fireEvent.click(screen.getByRole('link', { name: '기준평가로 이동' }))

    expect(document.title).toBe('기준평가 | CredAble')
    expect(screen.getByRole('status')).toHaveTextContent('기준평가 화면으로 이동했습니다.')
    expect(main).toHaveFocus()
  })

  it('names nested product routes without exposing the product identifier', () => {
    render(
      <MemoryRouter initialEntries={['/products/demo-secret-id/apply']}>
        <RouteAnnouncement />
      </MemoryRouter>,
    )

    expect(document.title).toBe('은행 신청 연결 안내 | CredAble')
    expect(document.title).not.toContain('demo-secret-id')
  })
})
