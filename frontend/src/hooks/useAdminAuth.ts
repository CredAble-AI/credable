import { createContext, useContext } from 'react'

export interface AdminAuthState {
  apiKey: string | null
  connect(apiKey: string): void
  clear(): void
}

export const AdminAuthContext = createContext<AdminAuthState | null>(null)

export function useAdminAuth() {
  const value = useContext(AdminAuthContext)
  if (!value) throw new Error('useAdminAuth must be used within AdminAuthProvider')
  return value
}
