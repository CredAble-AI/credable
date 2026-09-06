import { providerMode, type ProviderMode } from '../config/providerMode'

const environmentCopy: Record<ProviderMode, { label: string; description: string }> = {
  mock: {
    label: '시연용 합성 데이터',
    description: '실제 고객 정보가 아닌 합성 데이터로 동작하는 시연 환경',
  },
  live: {
    label: '시연용 합성 데이터',
    description: '실제 고객 정보가 아닌 합성 데이터로 동작하는 시연 환경',
  },
}

interface EnvironmentIndicatorProps {
  mode?: ProviderMode
}

function EnvironmentIndicator({ mode = providerMode }: EnvironmentIndicatorProps) {
  const copy = environmentCopy[mode]

  return (
    <span
      className={`environment-indicator environment-indicator--${mode}`}
      aria-label={`실행 환경: ${copy.description}`}
      title={copy.description}
    >
      <i aria-hidden="true" />
      <span className="environment-indicator__full">{copy.label}</span>
      <span className="environment-indicator__compact" aria-hidden="true">시연</span>
    </span>
  )
}

export default EnvironmentIndicator
