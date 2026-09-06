import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { assessmentExplanationProvider } from '../hooks/useAssessmentExplanationState'
import type { AssessmentExplanationResponse, AssessmentExplanationState } from '../types/assessmentExplanation'
import AssessmentExplanationPanel from './AssessmentExplanationPanel'

vi.mock('../hooks/useAssessmentExplanationState', () => ({ assessmentExplanationProvider: { get: vi.fn(), generate: vi.fn() } }))

const explanation: AssessmentExplanationState = {
  explanationId: 'exp_demo', targetType: 'BASELINE_ASSESSMENT', targetAssessmentId: 'asm_demo', headline: '정책 경계에 불확실성이 남아 있습니다',
  sections: [{ messageCode: 'POLICY_PATH_AMBIGUOUS', title: '정책 경계에 불확실성이 남아 있습니다', text: '현재 평가 범위가 둘 이상의 정책 경로에 걸쳐 최소 증빙 확인이 필요합니다.', sourceReferenceIds: ['pbc_demo'] }],
  cautionText: '이 설명은 대출 승인·부결, 금리 또는 한도를 의미하지 않습니다.', sourceReferences: [{ sourceType: 'POLICY_BOUNDARY', sourceId: 'pbc_demo', dataVersion: 'demo-v1', modelVersion: null, policyVersion: 'demo-policy-v1' }],
  inputSnapshotHash: 'a'.repeat(64), renderingMode: 'DEMO_TEMPLATE', fallbackApplied: false, fallbackReasonCode: null, providerVersion: 'demo-provider-v1', modelVersion: null, promptVersion: 'demo-prompt-v1', explanationPolicyVersion: 'demo-explanation-policy-v1', dataVersion: 'demo-v1', generatedAt: '2026-09-06T08:00:00+09:00', demoOnly: true,
}
const response = (value: AssessmentExplanationState | null): AssessmentExplanationResponse => ({ sessionId: 'ses_demo', explanation: value })

describe('AssessmentExplanationPanel', () => {
  beforeEach(() => {
    vi.mocked(assessmentExplanationProvider.get).mockReset().mockResolvedValue(response(null))
    vi.mocked(assessmentExplanationProvider.generate).mockReset().mockResolvedValue(response(explanation))
  })

  it('recovers with GET and waits for explicit generation', async () => {
    render(<AssessmentExplanationPanel sessionId="ses_demo" />)

    expect(await screen.findByRole('button', { name: '평가 결과 설명 생성' })).toBeInTheDocument()
    expect(assessmentExplanationProvider.get).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal))
    expect(assessmentExplanationProvider.generate).not.toHaveBeenCalled()
  })

  it('renders only the server response after explicit generation', async () => {
    render(<AssessmentExplanationPanel sessionId="ses_demo" />)
    fireEvent.click(await screen.findByRole('button', { name: '평가 결과 설명 생성' }))

    await waitFor(() => expect(assessmentExplanationProvider.generate).toHaveBeenCalledWith('ses_demo', expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { level: 3, name: explanation.headline })).toBeInTheDocument()
    expect(screen.getByText('Demo 템플릿')).toBeInTheDocument()
    expect(screen.getByText(explanation.sections[0].text)).toBeInTheDocument()
    expect(screen.getByText(explanation.cautionText)).toBeInTheDocument()
  })

  it('clearly marks a server fallback instead of presenting it as AI output', async () => {
    vi.mocked(assessmentExplanationProvider.get).mockResolvedValue(response({ ...explanation, renderingMode: 'RULE_FALLBACK', fallbackApplied: true, fallbackReasonCode: 'EXPLANATION_PROVIDER_ERROR', providerVersion: 'rule-fallback-v1' }))
    render(<AssessmentExplanationPanel sessionId="ses_demo" />)

    expect(await screen.findByText('규칙 기반 설명')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('EXPLANATION_PROVIDER_ERROR')
  })

  it('rejects a response from another session', async () => {
    vi.mocked(assessmentExplanationProvider.get).mockResolvedValue({ ...response(explanation), sessionId: 'ses_other' })
    render(<AssessmentExplanationPanel sessionId="ses_demo" />)

    expect(await screen.findByRole('alert')).toHaveTextContent('현재 세션의 평가 결과 설명을 확인할 수 없습니다.')
    expect(screen.getByRole('button', { name: '설명 상태 다시 확인' })).toBeInTheDocument()
  })
})
