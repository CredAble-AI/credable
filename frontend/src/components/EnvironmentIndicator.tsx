import { providerMode, type ProviderMode } from '../config/providerMode'

const environmentCopy: Record<ProviderMode, { label: string; description: string }> = {
  mock: {
    label: 'Mock · Demo Only',
    description: '브라우저의 합성 Mock 데이터를 사용하는 Demo 환경',
  },
  live: {
    label: 'API · Demo Only',
    description: '백엔드 API에 연결된 합성 Demo 환경',
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
      <span className="environment-indicator__compact" aria-hidden="true">{mode === 'mock' ? 'Mock' : 'API'}</span>
    </span>
  )
}

export default EnvironmentIndicator
