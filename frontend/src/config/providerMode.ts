export type ProviderMode = 'mock' | 'live'

const resolveMode = (): ProviderMode => {
  const configured = import.meta.env.VITE_API_MODE
  if (configured === 'mock' || configured === 'live') return configured
  return import.meta.env.MODE === 'test' ? 'mock' : 'live'
}

/** The customer app uses the real backend by default. Tests use mock unless VITE_API_MODE explicitly overrides it. */
export const providerMode: ProviderMode = resolveMode()
export const isMockMode = providerMode === 'mock'

export const selectProvider = <T,>(mock: T, live: T): T => (providerMode === 'live' ? live : mock)
