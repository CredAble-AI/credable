import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import App from './App'

describe('administrator journey integration', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('processes a demo review and follows its session oversight routes without an access key', async () => {
    render(<MemoryRouter initialEntries={['/admin/reviews']}><App /></MemoryRouter>)

    expect(screen.getByRole('heading', { level: 1, name: '심사역 검토 목록' })).toBeInTheDocument()
    expect(localStorage).toHaveLength(0)

    const pendingReviewHeading = await screen.findByRole('heading', { level: 2, name: 'uwr_demo_assessment' })
    const pendingReviewCard = pendingReviewHeading.closest('article') as HTMLElement
    expect(within(pendingReviewCard).getByText('접수 대기')).toBeInTheDocument()
    expect(localStorage).toHaveLength(0)
    fireEvent.click(within(pendingReviewCard).getByRole('link', { name: '상세 확인' }))

    expect(await screen.findByText('접수 대기 상태입니다.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '검토 접수' }))
    const resultSelect = await screen.findByLabelText('처리 결과')
    fireEvent.change(resultSelect, { target: { value: 'ASSESSMENT_CONFIRMED' } })
    fireEvent.click(screen.getByRole('button', { name: '선택한 결과로 검토 완료' }))

    expect(await screen.findByText(/이 검토 요청은/)).toHaveTextContent('평가 확인')
    expect(screen.queryByRole('button', { name: '선택한 결과로 검토 완료' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '세션 처리 이력 보기' }))

    expect(await screen.findByRole('heading', { level: 1, name: '세션 처리 이력' })).toBeInTheDocument()
    expect(await screen.findByRole('heading', { level: 2, name: '심사역 검토 시작' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '조회 중인 세션' })).toHaveTextContent('ses_demo_sole')
    fireEvent.click(screen.getByRole('link', { name: 'Evidence 부담 지표' }))

    expect(await screen.findByRole('heading', { level: 1, name: 'Evidence 요청 부담 지표' })).toBeInTheDocument()
    expect(await screen.findByText('정책 임계치가 적용되지 않은 사실 지표입니다')).toBeInTheDocument()
    expect(screen.getByText('처리 경로 확정')).toBeInTheDocument()
    expect(screen.getByText('수집 종료')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: '세션 처리 이력' }))

    expect(await screen.findByRole('heading', { level: 1, name: '세션 처리 이력' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('link', { name: /검토 목록/ }))
    const completedReviewHeading = await screen.findByRole('heading', { level: 2, name: 'uwr_demo_assessment' })
    expect(within(completedReviewHeading.closest('article') as HTMLElement).getByText('처리 완료')).toBeInTheDocument()

    expect(localStorage).toHaveLength(0)
  })
})
