import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EnvironmentIndicator from './EnvironmentIndicator'

describe('EnvironmentIndicator', () => {
  it('identifies the browser mock environment', () => {
    render(<EnvironmentIndicator mode="mock" />)

    expect(screen.getByText('Mock · Demo Only')).toBeInTheDocument()
    expect(screen.getByLabelText('실행 환경: 브라우저의 합성 Mock 데이터를 사용하는 Demo 환경')).toBeInTheDocument()
  })

  it('identifies the backend-connected demo environment without implying production', () => {
    render(<EnvironmentIndicator mode="live" />)

    expect(screen.getByText('API · Demo Only')).toBeInTheDocument()
    expect(screen.getByLabelText('실행 환경: 백엔드 API에 연결된 합성 Demo 환경')).toBeInTheDocument()
  })
})
