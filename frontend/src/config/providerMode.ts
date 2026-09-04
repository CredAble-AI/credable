export type ProviderMode = 'mock' | 'live'

const resolveMode = (): ProviderMode => (import.meta.env.VITE_API_MODE === 'live' ? 'live' : 'mock')

/** VITE_API_MODE=live switches API providers to the live backend; any other value (including unset) falls back to mock. */
export const providerMode: ProviderMode = resolveMode()
export const isMockMode = providerMode === 'mock'

export const selectProvider = <T,>(mock: T, live: T): T => (providerMode === 'live' ? live : mock)
