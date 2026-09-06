import { useEffect, useRef, useState } from 'react'
import { liveCustomerSessionProvider, normalizeSessionError } from '../api/sessionClient'
import { selectProvider } from '../config/providerMode'
import { mockCustomerSessionProvider } from '../mocks/customerSessionProvider'
import type { ApiError } from '../types/api'
import type { CustomerSession } from '../types/customerSession'

export const sessionProvider = selectProvider(mockCustomerSessionProvider, liveCustomerSessionProvider)

export class CustomerSessionRecoveryError extends Error {
  readonly apiError: ApiError

  constructor(apiError: ApiError) {
    super(apiError.message)
    this.name = 'CustomerSessionRecoveryError'
    this.apiError = apiError
  }
}

/** Loads the current session from the provider (mock: localStorage snapshot; live: GET session + consents). */
export const useCustomerSession = (): { session: CustomerSession | null; loading: boolean } => {
  const [session, setSession] = useState<CustomerSession | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<ApiError | null>(null)
  const sequenceRef = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    const sequence = ++sequenceRef.current
    sessionProvider.get(controller.signal)
      .then((result) => { if (sequence === sequenceRef.current) setSession(result) })
      .catch((caught) => {
        if (!controller.signal.aborted && sequence === sequenceRef.current) setError(normalizeSessionError(caught))
      })
      .finally(() => { if (sequence === sequenceRef.current) setLoading(false) })
    return () => { sequenceRef.current += 1; controller.abort() }
  }, [])

  if (error) throw new CustomerSessionRecoveryError(error)
  return { session, loading }
}
