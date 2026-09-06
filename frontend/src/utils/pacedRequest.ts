import { minimumActionMs } from '../config/actionPacing'

/** Keeps a server action's loading state visible for at least `ms`. */
export const withMinimumDuration = async <T>(
  work: Promise<T>,
  ms: number = minimumActionMs,
): Promise<T> => {
  if (ms <= 0) return work
  const [result] = await Promise.all([
    work,
    new Promise((resolve) => setTimeout(resolve, ms)),
  ])
  return result
}
