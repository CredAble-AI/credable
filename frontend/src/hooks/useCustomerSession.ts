import { useEffect, useRef, useState } from 'react'
import { liveCustomerSessionProvider } from '../api/sessionClient'
import { selectProvider } from '../config/providerMode'
import { mockCustomerSessionProvider } from '../mocks/customerSessionProvider'
import type { CustomerSession } from '../types/customerSession'

export const sessionProvider = selectProvider(mockCustomerSessionProvider, liveCustomerSessionProvider)

/** Loads the current session from the provider (mock: localStorage snapshot; live: GET session + consents). */
export const useCustomerSession = (): { session: CustomerSession | null; loading: boolean } => {
  const [session, setSession] = useState<CustomerSession | null>(null)
  const [loading, setLoading] = useState(true)
  const sequenceRef = useRef(0)

  useEffect(() => {
    const controller = new AbortController()
    const sequence = ++sequenceRef.current
    sessionProvider.get(controller.signal)
      .then((result) => { if (sequence === sequenceRef.current) setSession(result) })
      .catch(() => { if (!controller.signal.aborted && sequence === sequenceRef.current) setSession(null) })
      .finally(() => { if (sequence === sequenceRef.current) setLoading(false) })
    return () => { sequenceRef.current += 1; controller.abort() }
  }, [])

  return { session, loading }
}
