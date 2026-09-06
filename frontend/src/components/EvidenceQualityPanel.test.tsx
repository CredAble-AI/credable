import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { evidenceQualityProvider } from '../hooks/useEvidenceQualityState'
import type { EvidenceQualityResponse, EvidenceQualityState } from '../types/evidenceQuality'
import type { EvidenceSubmissionState } from '../types/evidenceSubmission'
import EvidenceQualityPanel from './EvidenceQualityPanel'

vi.mock('../hooks/useEvidenceQualityState', () => ({ evidenceQualityProvider: { get: vi.fn(), check: vi.fn() } }))
vi.mock('./SupplementalAssessmentPanel', () => ({ default: () => <div>보완평가 패널</div> }))

const snapshotHash = 'a'.repeat(64)
const submission: EvidenceSubmissionState = {
  submissionId: 'sub_demo', selectionId: 'evs_demo', evidenceType: 'RECENT_REVENUE', sourceType: 'CUSTOMER_SUBMITTED', submissionMode: 'DEMO_FILE_UPLOAD', status: 'RECEIVED',
  submittedAt: '2026-09-06T01:00:00+09:00', observedAt: '2026-09-01T01:00:00+09:00', submissionSnapshotHash: snapshotHash, dataVersion: 'demo-v1', uploadedFile: null, evidenceConsentId: 'evc_demo', consentScopeVersion: 'demo-scope-v1', demoOnly: true,
}
const checks: EvidenceQualityState['checks'] = [
  ['PROVENANCE', 'DEMO_SOURCE_REFERENCE_PRESENT'], ['FRESHNESS', 'DEMO_FRESHNESS_POLICY_PASSED'], ['AUTHENTICITY', 'DEMO_AUTHENTICITY_PASSED'],
  ['COMPLETENESS', 'DEMO_REQUIRED_FIELDS_PRESENT'], ['CONSISTENCY', 'DEMO_TOTALS_CONSISTENT'], ['MANIPULATION_RISK', 'DEMO_MANIPULATION_CHECK_PASSED'],
].map(([dimension, rationaleCode]) => ({ dimension, status: 'PASSED', rationaleCode })) as EvidenceQualityState['checks']
const quality = (status: EvidenceQualityState['status'] = 'ACCEPTED'): EvidenceQualityState => {
  const resultChecks = status === 'ACCEPTED' ? checks : checks.map((check) => check.dimension === 'AUTHENTICITY' ? { ...check, status: status === 'REVIEW_REQUIRED' ? 'FAILED' as const : 'NOT_VERIFIED' as const, rationaleCode: 'DEMO_AUTHENTICITY_FAILED' } : check)
  return {
    qualityCheckId: 'evq_demo', submissionId: submission.submissionId, evidenceType: submission.evidenceType, status, checks: resultChecks,
    rejectionCodes: status === 'ACCEPTED' ? [] : ['DEMO_AUTHENTICITY_FAILED'], suspicionCodes: status === 'REVIEW_REQUIRED' ? ['DEMO_AUTHENTICITY_FAILED'] : [],
    eligibleForReassessment: status === 'ACCEPTED', nextAction: status === 'ACCEPTED' ? 'RUN_REASSESSMENT' : status === 'REJECTED' ? 'EXCLUDE_EVIDENCE' : 'UNDERWRITER_REVIEW',
    underwriterRequired: status === 'REVIEW_REQUIRED', checkedAt: '2026-09-06T02:00:00+09:00', submissionSnapshotHash: snapshotHash, dataVersion: 'demo-v1', qualityPolicyVersion: 'demo-quality-v1', demoOnly: true,
    trustVerification: { status: 'VERIFIED', channel: 'SERVER_SIGNED_MANIFEST', verifiedScopes: ['DOCUMENT_INTEGRITY', 'MANIFEST_BINDING', 'DEMO_ISSUER_IDENTITY'], algorithm: 'RS256', keyId: 'demo-key-v1', rationaleCode: 'DEMO_SIGNED_MANIFEST_VERIFIED' },
  }
}
const response = (result: EvidenceQualityState | null): EvidenceQualityResponse => ({ sessionId: 'ses_demo', quality: result })
const renderPanel = () => render(<MemoryRouter><EvidenceQualityPanel sessionId="ses_demo" submission={submission} /></MemoryRouter>)

describe('EvidenceQualityPanel', () => {
  beforeEach(() => {
    vi.mocked(evidenceQualityProvider.get).mockReset().mockResolvedValue(response(null))
    vi.mocked(evidenceQualityProvider.check).mockReset().mockResolvedValue(response(quality()))
  })

  it('runs no check automatically and displays every server check after confirmation', async () => {
    renderPanel()

    const button = await screen.findByRole('button', { name: '자료 품질 확인' })
    expect(evidenceQualityProvider.check).not.toHaveBeenCalled()
    fireEvent.click(button)

    await waitFor(() => expect(evidenceQualityProvider.check).toHaveBeenCalledWith('ses_demo', 'sub_demo', expect.any(AbortSignal)))
    expect(await screen.findByRole('heading', { name: '자료 확인을 완료했습니다' })).toBeInTheDocument()
    expect(screen.getAllByText('확인 완료')).toHaveLength(6)
    expect(screen.getByText('서버가 서명한 Demo 검증정보를 확인했습니다')).toBeInTheDocument()
    expect(screen.getByText('Demo 발급 서버')).toBeInTheDocument()
    expect(screen.getByText('SERVER_SIGNED_MANIFEST')).toBeInTheDocument()
    expect(screen.getByText('RUN_REASSESSMENT')).toBeInTheDocument()
    expect(screen.getByText('보완평가 패널')).toBeInTheDocument()
  })

  it('shows server suspicion and underwriter routing without recalculating them', async () => {
    vi.mocked(evidenceQualityProvider.get).mockResolvedValue(response(quality('REVIEW_REQUIRED')))
    renderPanel()

    expect(await screen.findByRole('heading', { name: '담당자 확인이 필요합니다' })).toBeInTheDocument()
    expect(screen.getAllByText('DEMO_AUTHENTICITY_FAILED')).toHaveLength(3)
    expect(screen.getByText('UNDERWRITER_REVIEW')).toBeInTheDocument()
    expect(screen.getByText('필요')).toBeInTheDocument()
  })

  it('offers the server-driven next selection path for rejected Evidence', async () => {
    vi.mocked(evidenceQualityProvider.get).mockResolvedValue(response(quality('REJECTED')))
    renderPanel()

    const link = await screen.findByRole('link', { name: '다음 자료 한 건 확인' })
    expect(link).toHaveAttribute('href', '/evidence?selectNext=1')
    expect(screen.queryByText('보완평가 패널')).not.toBeInTheDocument()
  })

  it('rejects a quality response for another submission snapshot', async () => {
    vi.mocked(evidenceQualityProvider.get).mockResolvedValue(response({ ...quality(), submissionSnapshotHash: 'b'.repeat(64) }))
    renderPanel()

    expect(await screen.findByRole('alert')).toHaveTextContent('현재 제출한 Evidence와 일치하는 품질검증 결과를 확인할 수 없습니다.')
  })
})
