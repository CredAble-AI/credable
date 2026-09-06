import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EnvironmentIndicator from './EnvironmentIndicator'

describe('EnvironmentIndicator', () => {
  it('identifies the browser mock environment', () => {
    render(<EnvironmentIndicator mode="mock" />)

    expect(screen.getByText('시연용 합성 데이터')).toBeInTheDocument()
    expect(screen.getByLabelText('실행 환경: 실제 고객 정보가 아닌 합성 데이터로 동작하는 시연 환경')).toBeInTheDocument()
  })

  it('identifies the backend-connected demo environment without implying production', () => {
    render(<EnvironmentIndicator mode="live" />)

    expect(screen.getByText('시연용 합성 데이터')).toBeInTheDocument()
    expect(screen.getByLabelText('실행 환경: 실제 고객 정보가 아닌 합성 데이터로 동작하는 시연 환경')).toBeInTheDocument()
  })
})
