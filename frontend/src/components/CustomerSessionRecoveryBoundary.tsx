import { Component } from 'react'
import { Link, Outlet } from 'react-router-dom'
import { CustomerSessionRecoveryError } from '../hooks/useCustomerSession'
import type { ApiError } from '../types/api'
import Header from './Header'
import './CustomerSessionRecoveryBoundary.css'

interface State {
  error: ApiError | null
  retryKey: number
}

class CustomerSessionRecoveryBoundary extends Component<Record<string, never>, State> {
  state: State = { error: null, retryKey: 0 }

  static getDerivedStateFromError(caught: unknown) {
    if (caught instanceof CustomerSessionRecoveryError) return { error: caught.apiError }
    throw caught
  }

  retry = () => this.setState(({ retryKey }) => ({ error: null, retryKey: retryKey + 1 }))

  render() {
    const { error, retryKey } = this.state
    if (!error) return <Outlet key={retryKey} />

    return <div className="workspace-shell customer-flow"><Header /><main id="main-content" tabIndex={-1} className="session-recovery-page"><section className="session-recovery-card" role="alert"><span aria-hidden="true">!</span><p className="flow-kicker">SESSION RECOVERY</p><h1>진행 중인 세션을 불러오지 못했습니다</h1><p>저장된 세션은 유지했습니다. 네트워크 연결을 확인한 뒤 다시 시도해주세요.</p><small>오류 코드: {error.code}{error.requestId ? ` · Request ID: ${error.requestId}` : ''}</small><div>{error.retryable && <button className="button button--primary" type="button" onClick={this.retry}>다시 시도</button>}<Link className="button button--secondary" to="/start">새 평가 시작</Link></div></section></main></div>
  }
}

export default CustomerSessionRecoveryBoundary
