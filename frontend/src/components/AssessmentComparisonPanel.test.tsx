import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { assessmentComparisonProvider } from '../hooks/useAssessmentComparisonState'
import type { AssessmentComparisonResponse, AssessmentComparisonState } from '../types/assessmentComparison'
import AssessmentComparisonPanel from './AssessmentComparisonPanel'

vi.mock('../hooks/useAssessmentComparisonState', () => ({ assessmentComparisonProvider: { get: vi.fn(), compare: vi.fn() } }))
vi.mock('./EvidenceResolutionPanel', () => ({ default: () => <div>Evidence 수집 판단 패널</div> }))

const comparison: AssessmentComparisonState = {
  comparisonId: 'acp_demo', baselineAssessmentId: 'asm_demo', supplementalAssessmentId: 'sam_demo', qualityCheckId: 'evq_demo', basis: 'GRADE_SET', uncertaintyChange: 'NARROWED',
  beforeUncertainty: { pointEstimate: null, lowerBound: null, upperBound: null, gradeSet: ['DEMO_GRADE_B', 'DEMO_GRADE_C'], calibrationMode: 'RULE_TABLE', calibrationVersion: 'demo-calibration-v1', demoOnly: true },
  afterUncertainty: { pointEstimate: null, lowerBound: null, upperBound: null, gradeSet: ['DEMO_GRADE_B'], calibrationMode: 'RULE_TABLE', calibrationVersion: 'demo-calibration-v1', demoOnly: true },
  rationaleCodes: ['GRADE_SET_PROPER_SUBSET'], baselineModelVersion: 'demo-baseline-v1', supplementalModelVersion: 'demo-supplemental-v1', comparedAt: '2026-09-06T04:00:00+09:00', demoOnly: true,
}
const response = (value: AssessmentComparisonState | null): AssessmentComparisonResponse => ({ sessionId: 'ses_demo', comparison: value })
const renderPanel = () => render(<AssessmentComparisonPanel sessionId="ses_demo" baselineAssessmentId="asm_demo" supplementalAssessmentId="sam_demo" qualityCheckId="evq_demo" />)

describe('AssessmentComparisonPanel', () => {
  beforeEach(() => {
    vi.mocked(assessmentComparisonProvider.get).mockReset().mockResolvedValue(response(null))
    vi.mocked(assessmentComparisonProvider.compare).mockReset().mockResolvedValue(response(comparison))
  })

  it('does not compare automatically and displays the server comparison after confirmation', async () => {
    renderPanel()

    const button = await screen.findByRole('button', { name: '평가 전후 비교' })
    expect(assessmentComparisonProvider.compare).not.toHaveBeenCalled()
    fireEvent.click(button)

    await waitFor(() => expect(assessmentComparisonProvider.compare).toHaveBeenCalledWith('ses_demo', { baselineAssessmentId: 'asm_demo', supplementalAssessmentId: 'sam_demo', qualityCheckId: 'evq_demo' }, expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '가능한 결과 범위가 줄었습니다' })).toBeInTheDocument()
    expect(screen.getByText('DEMO_GRADE_B · DEMO_GRADE_C')).toBeInTheDocument()
    expect(screen.getByText('GRADE_SET_PROPER_SUBSET')).toBeInTheDocument()
    expect(screen.getByText(/승인 가능성 상승/)).toBeInTheDocument()
    expect(screen.getByText('Evidence 수집 판단 패널')).toBeInTheDocument()
  })

  it('ignores a comparison from a previous supplemental assessment', async () => {
    vi.mocked(assessmentComparisonProvider.get).mockResolvedValue(response({ ...comparison, supplementalAssessmentId: 'sam_previous' }))
    renderPanel()

    expect(await screen.findByRole('button', { name: '평가 전후 비교' })).toBeInTheDocument()
    expect(screen.queryByText('acp_demo')).not.toBeInTheDocument()
  })

  it('shows a non-comparable server result without inventing before and after values', async () => {
    vi.mocked(assessmentComparisonProvider.get).mockResolvedValue(response({ ...comparison, basis: 'NOT_COMPARABLE', uncertaintyChange: 'NOT_COMPARABLE', beforeUncertainty: null, afterUncertainty: null, rationaleCodes: ['CALIBRATION_VERSION_MISMATCH'] }))
    renderPanel()

    expect(await screen.findByRole('heading', { name: '동일 기준으로 비교할 수 없습니다' })).toBeInTheDocument()
    expect(screen.getAllByText('비교 가능한 범위 없음')).toHaveLength(2)
    expect(screen.getByText('CALIBRATION_VERSION_MISMATCH')).toBeInTheDocument()
  })

  it('rejects a newly created comparison returned for another assessment lineage', async () => {
    vi.mocked(assessmentComparisonProvider.compare).mockResolvedValue(response({ ...comparison, qualityCheckId: 'evq_other' }))
    renderPanel()

    fireEvent.click(await screen.findByRole('button', { name: '평가 전후 비교' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('현재 평가 이력과 일치하는 비교 결과를 확인할 수 없습니다.')
  })
})
