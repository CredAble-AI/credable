export type CustomerFlowStep = 'start' | 'consent' | 'data-connection' | 'assessment' | 'evidence' | 'products'

/**
 * One canonical step list for the customer flow so every screen shows the same
 * progress. Evidence and other loan paths are optional: the server decides
 * whether evidence is requested at all, and comparing other products is a
 * separate action rather than the end of the assessment.
 */
const steps: { key: CustomerFlowStep; label: string; optional?: true }[] = [
  { key: 'start', label: '시작' },
  { key: 'consent', label: '동의' },
  { key: 'data-connection', label: '데이터 연결' },
  { key: 'assessment', label: '기존 평가' },
  { key: 'evidence', label: '추가 자료', optional: true },
  { key: 'products', label: '다른 대출 경로', optional: true },
]

interface CustomerFlowStepsProps {
  current: CustomerFlowStep
  /** Each screen keeps its own layout styling for this nav. */
  className: string
}

function CustomerFlowSteps({ current, className }: CustomerFlowStepsProps) {
  return (
    <nav className={className} aria-label="진행 단계">
      {steps.map((step) => {
        const label = step.optional ? `${step.label} (필요 시)` : step.label
        return step.key === current
          ? <strong key={step.key} aria-current="step">{label}</strong>
          : <span key={step.key}>{label}</span>
      })}
    </nav>
  )
}

export default CustomerFlowSteps
