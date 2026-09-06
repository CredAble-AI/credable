import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { sessionProvider } from '../hooks/useCustomerSession'
import type { CustomerSession, DemoProfile } from '../types/customerSession'
import CustomerStartPage from './CustomerStartPage'

vi.mock('../hooks/useCustomerSession', () => ({
  sessionProvider: {
    listDemoProfiles: vi.fn(),
    create: vi.fn(),
  },
}))

const profiles: DemoProfile[] = [
  {
    demoProfileId: 'small-business',
    businessBorrowerType: 'SOLE_PROPRIETOR',
    displayName: '개인사업자',
    description: '개업 초기 소상공인을 예시로 한 개인사업자 합성 Demo 사례',
  },
  {
    demoProfileId: 'startup',
    businessBorrowerType: 'CORPORATION',
    displayName: '법인사업자',
    description: '설립 초기 스타트업을 예시로 한 법인사업자 합성 Demo 사례',
  },
]

const corporationSession: CustomerSession = {
  sessionId: 'ses_corporation',
  selectedProfileType: 'startup',
  demoProfile: profiles[1],
  consents: {
    required: { customerIdentity: false, accountSummary: false, creditInformation: false },
    optional: { submittedDocuments: false, otherInstitutions: false, partnerData: false },
  },
  demoOnly: true,
  createdAt: '2026-09-06T00:00:00+09:00',
  updatedAt: '2026-09-06T00:00:00+09:00',
}

const renderPage = () => render(
  <MemoryRouter initialEntries={['/start']}>
    <Routes>
      <Route path="/start" element={<CustomerStartPage />} />
      <Route path="/consent" element={<h1>동의 화면</h1>} />
    </Routes>
  </MemoryRouter>,
)

describe('CustomerStartPage', () => {
  beforeEach(() => {
    vi.mocked(sessionProvider.listDemoProfiles).mockReset().mockResolvedValue(profiles)
    vi.mocked(sessionProvider.create).mockReset().mockResolvedValue(corporationSession)
  })

  it('presents legal business borrower types without exposing presentation-only scenarios', async () => {
    renderPage()

    expect(await screen.findByRole('radio', { name: /개인사업자/ })).toBeInTheDocument()
    expect(screen.getByRole('radio', { name: /법인사업자/ })).toBeInTheDocument()
    expect(screen.getByText(/사업소득과 상환 책임의 주체가 개인/)).toBeInTheDocument()
    expect(screen.getByText(/법인 명의로 사업자금 대출 계약과 평가/)).toBeInTheDocument()
    expect(screen.queryByText(/소상공인/)).not.toBeInTheDocument()
    expect(screen.queryByText(/스타트업/)).not.toBeInTheDocument()
    expect(screen.getByText(/개인 생활자금 대출과 사업자등록 전 예비창업자는 현재 지원하지 않습니다/)).toBeInTheDocument()
  })

  it('creates a session with the selected business borrower type', async () => {
    renderPage()

    fireEvent.click(await screen.findByRole('radio', { name: /법인사업자/ }))
    fireEvent.click(screen.getByRole('button', { name: '계속하기' }))

    await waitFor(() => expect(sessionProvider.create).toHaveBeenCalledWith('CORPORATION', expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '동의 화면' })).toBeInTheDocument()
  })

  it('requires a business borrower type before creating a session', async () => {
    renderPage()

    await screen.findByRole('radio', { name: /개인사업자/ })
    fireEvent.click(screen.getByRole('button', { name: '계속하기' }))

    expect(screen.getByRole('alert')).toHaveTextContent('개인사업자 또는 법인사업자를 선택해주세요.')
    expect(sessionProvider.create).not.toHaveBeenCalled()
  })
})
