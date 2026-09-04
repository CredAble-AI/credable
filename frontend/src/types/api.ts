export interface ApiError {
  code: string
  message: string
  requestId?: string
  retryable: boolean
}
