import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { evidenceResolutionProvider } from '../hooks/useEvidenceResolutionState'
import type { EvidenceResolutionResponse, EvidenceResolutionState } from '../types/evidenceResolution'
import EvidenceResolutionPanel from './EvidenceResolutionPanel'

vi.mock('../hooks/useEvidenceResolutionState', () => ({ evidenceResolutionProvider: { get: vi.fn(), resolve: vi.fn() } }))

const resolved: EvidenceResolutionState = {
  resolutionId: 'res_demo', comparisonId: 'acp_demo', supplementalAssessmentId: 'sam_demo', status: 'RESOLVED', nextAction: 'SHOW_UPDATED_RESULTS', stopEvidenceCollection: true, underwriterRequired: false,
  reasonCode: 'PATH_STABLE', possibleRoutes: ['DEMO_PATH_1'], crossedBoundaryCodes: [], resolvedAt: '2026-09-06T05:00:00+09:00', calibrationVersion: 'demo-calibration-v1', boundaryPolicyVersion: 'demo-policy-v1', demoOnly: true,
}
const response = (value: EvidenceResolutionState | null): EvidenceResolutionResponse => ({ sessionId: 'ses_demo', resolution: value })
const renderPanel = () => render(<MemoryRouter><EvidenceResolutionPanel sessionId="ses_demo" comparisonId="acp_demo" supplementalAssessmentId="sam_demo" /></MemoryRouter>)

describe('EvidenceResolutionPanel', () => {
  beforeEach(() => {
    vi.mocked(evidenceResolutionProvider.get).mockReset().mockResolvedValue(response(null))
    vi.mocked(evidenceResolutionProvider.resolve).mockReset().mockResolvedValue(response(resolved))
  })

  it('does not resolve automatically and displays the server terminal state after confirmation', async () => {
    renderPanel()

    const button = await screen.findByRole('button', { name: '다음 단계 확인' })
    expect(evidenceResolutionProvider.resolve).not.toHaveBeenCalled()
    fireEvent.click(button)

    await waitFor(() => expect(evidenceResolutionProvider.resolve).toHaveBeenCalledWith('ses_demo', { comparisonId: 'acp_demo', supplementalAssessmentId: 'sam_demo' }, expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '추가 자료 확인을 마쳤습니다' })).toBeInTheDocument()
    expect(screen.getByText('결과 범위가 충분히 확인되어 더 이상 자료를 요청하지 않습니다.')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '자사 상품 조건 확인' })).toHaveAttribute('href', '/products')
    expect(screen.queryByRole('link', { name: '다음 자료 한 건 확인' })).not.toBeInTheDocument()
  })

  it('offers the next Evidence action only when the server requests it', async () => {
    vi.mocked(evidenceResolutionProvider.get).mockResolvedValue(response({ ...resolved, status: 'MORE_EVIDENCE_REQUIRED', nextAction: 'REQUEST_NEXT_EVIDENCE', stopEvidenceCollection: false, reasonCode: 'POLICY_BOUNDARY_STILL_AMBIGUOUS', possibleRoutes: ['DEMO_PATH_1', 'DEMO_PATH_2'], crossedBoundaryCodes: ['DEMO_BOUNDARY_1_2'] }))
    renderPanel()

    expect(await screen.findByRole('heading', { name: '자료 한 건을 더 확인할 수 있습니다' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '다음 자료 한 건 확인' })).toHaveAttribute('href', '/evidence?selectNext=1')
    expect(screen.getByText('결과 범위를 더 명확히 하기 위해 다음으로 필요한 자료 한 건을 안내합니다.')).toBeInTheDocument()
  })

  it('shows human review without offering another Evidence request', async () => {
    vi.mocked(evidenceResolutionProvider.get).mockResolvedValue(response({ ...resolved, status: 'HUMAN_REVIEW', nextAction: 'UNDERWRITER_REVIEW', underwriterRequired: true, reasonCode: 'UNCERTAINTY_COMPARISON_NOT_RELIABLE', possibleRoutes: [] }))
    renderPanel()

    expect(await screen.findByRole('heading', { name: '담당자 확인으로 전환했습니다' })).toBeInTheDocument()
    expect(screen.getByText('자동 확인을 중단하고 담당자가 직접 살펴보는 단계로 전환했습니다.')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '다음 자료 한 건 확인' })).not.toBeInTheDocument()
  })

  it('ignores a resolution from a previous comparison', async () => {
    vi.mocked(evidenceResolutionProvider.get).mockResolvedValue(response({ ...resolved, comparisonId: 'acp_previous' }))
    renderPanel()

    expect(await screen.findByRole('button', { name: '다음 단계 확인' })).toBeInTheDocument()
    expect(screen.queryByText('res_demo')).not.toBeInTheDocument()
  })
})
