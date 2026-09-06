import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { supplementalAssessmentProvider } from '../hooks/useSupplementalAssessmentState'
import type { SupplementalAssessmentResponse, SupplementalAssessmentState } from '../types/supplementalAssessment'
import SupplementalAssessmentPanel from './SupplementalAssessmentPanel'

vi.mock('../hooks/useSupplementalAssessmentState', () => ({ supplementalAssessmentProvider: { get: vi.fn(), run: vi.fn() } }))
vi.mock('./AssessmentComparisonPanel', () => ({ default: () => <div>평가 전후 비교 패널</div> }))

const completed: SupplementalAssessmentState = {
  supplementalAssessmentId: 'sam_demo', baselineAssessmentId: 'asm_demo', qualityCheckId: 'evq_demo', submissionId: 'sub_demo', status: 'COMPLETED',
  calculatedAt: '2026-09-06T03:00:00+09:00', inputSnapshotId: 'sas_demo', modelVersion: 'demo-supplemental-v1', reasonCode: null, acceptedEvidenceCount: 1, demoOnly: true,
  uncertainty: { pointEstimate: null, lowerBound: null, upperBound: null, gradeSet: ['DEMO_GRADE_B'], calibrationMode: 'RULE_TABLE', calibrationVersion: 'demo-calibration-v1', demoOnly: true },
}
const response = (supplementalAssessment: SupplementalAssessmentState | null): SupplementalAssessmentResponse => ({ sessionId: 'ses_demo', supplementalAssessment })
const renderPanel = () => render(<SupplementalAssessmentPanel sessionId="ses_demo" submissionId="sub_demo" qualityCheckId="evq_demo" />)

describe('SupplementalAssessmentPanel', () => {
  beforeEach(() => {
    vi.mocked(supplementalAssessmentProvider.get).mockReset().mockResolvedValue(response(null))
    vi.mocked(supplementalAssessmentProvider.run).mockReset().mockResolvedValue(response(completed))
  })

  it('automatically runs when the current submission has no result', async () => {
    renderPanel()

    await waitFor(() => expect(supplementalAssessmentProvider.run).toHaveBeenCalledWith('ses_demo', 'sub_demo', expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '보완평가를 완료했습니다' })).toBeInTheDocument()
    expect(screen.getByText('평가 구간 B')).toBeInTheDocument()
    expect(screen.queryByText('모델 추정값')).not.toBeInTheDocument()
    expect(screen.getByText('품질을 확인한 자료를 반영한 결과입니다. 기존 평가와 나란히 비교할 수 있습니다.')).toBeInTheDocument()
    expect(screen.getByText('평가 전후 비교 패널')).toBeInTheDocument()
    expect(screen.queryByText('심사역 재확인 패널')).not.toBeInTheDocument()
  })

  it('ignores a previous iteration result and automatically runs the current assessment', async () => {
    vi.mocked(supplementalAssessmentProvider.get).mockResolvedValue(response({ ...completed, submissionId: 'sub_previous', qualityCheckId: 'evq_previous' }))
    renderPanel()

    await waitFor(() => expect(supplementalAssessmentProvider.run).toHaveBeenCalledWith('ses_demo', 'sub_demo', expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '보완평가를 완료했습니다' })).toBeInTheDocument()
  })

  it('shows an incomplete server status without inventing uncertainty', async () => {
    vi.mocked(supplementalAssessmentProvider.get).mockResolvedValue(response({ ...completed, status: 'INSUFFICIENT_DATA', modelVersion: null, reasonCode: 'EVIDENCE_AFTER_FEATURE_CUTOFF', uncertainty: null }))
    renderPanel()

    expect(await screen.findByText('현재 보완평가를 완료하지 못했습니다.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '보완평가 결과를 확인해주세요' })).toBeInTheDocument()
    expect(screen.queryByText('현재 확인 가능한 평가 범위')).not.toBeInTheDocument()
  })

  it('rejects a result from another quality check', async () => {
    vi.mocked(supplementalAssessmentProvider.get).mockResolvedValue(response({ ...completed, qualityCheckId: 'evq_other' }))
    renderPanel()

    expect(await screen.findByRole('alert')).toHaveTextContent('현재 품질검증과 일치하는 보완평가 결과를 확인할 수 없습니다.')
  })
})
