import { describe, expect, it } from 'vitest'
import { withMinimumDuration } from './pacedRequest'

describe('withMinimumDuration', () => {
  it('keeps the loading state visible for the configured minimum', async () => {
    const started = Date.now()

    const result = await withMinimumDuration(Promise.resolve('done'), 60)

    expect(result).toBe('done')
    expect(Date.now() - started).toBeGreaterThanOrEqual(55)
  })

  it('does not delay a failure', async () => {
    const started = Date.now()

    await expect(withMinimumDuration(Promise.reject(new Error('nope')), 2_000)).rejects.toThrow('nope')

    expect(Date.now() - started).toBeLessThan(500)
  })

  it('never changes what the server returned', async () => {
    const payload = { status: 'ACCEPTED' }

    await expect(withMinimumDuration(Promise.resolve(payload), 0)).resolves.toBe(payload)
  })
})
