import { useMemo, useState, type ReactNode } from 'react'
import { AdminAuthContext, type AdminAuthState } from '../hooks/useAdminAuth'

function AdminAuthProvider({ children }: { children: ReactNode }) {
  const [apiKey, setApiKey] = useState<string | null>(null)
  const value = useMemo<AdminAuthState>(() => ({ apiKey, connect: setApiKey, clear: () => setApiKey(null) }), [apiKey])
  return <AdminAuthContext.Provider value={value}>{children}</AdminAuthContext.Provider>
}

export default AdminAuthProvider
