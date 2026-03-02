export function debounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  return function (this: unknown, ...args: Parameters<T>) {
    if (timeoutId) {
      clearTimeout(timeoutId)
    }

    timeoutId = setTimeout(() => {
      fn.apply(this, args)
      timeoutId = null
    }, delay)
  }
}

export function throttle<T extends (...args: unknown[]) => unknown>(
  fn: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle = false

  return function (this: unknown, ...args: Parameters<T>) {
    if (!inThrottle) {
      fn.apply(this, args)
      inThrottle = true
      setTimeout(() => {
        inThrottle = false
      }, limit)
    }
  }
}

export function debounceAsync<T extends (...args: unknown[]) => Promise<unknown>>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => Promise<ReturnType<T>> {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  let latestResolve: ((value: unknown) => void) | null = null
  let latestReject: ((reason?: unknown) => void) | null = null

  return function (this: unknown, ...args: Parameters<T>): Promise<ReturnType<T>> {
    return new Promise((resolve, reject) => {
      if (timeoutId) {
        clearTimeout(timeoutId)
      }

      latestResolve = resolve as (value: unknown) => void
      latestReject = reject

      timeoutId = setTimeout(async () => {
        try {
          const result = await fn.apply(this, args)
          if (latestResolve) {
            latestResolve(result)
          }
        } catch (error) {
          if (latestReject) {
            latestReject(error)
          }
        }
        timeoutId = null
        latestResolve = null
        latestReject = null
      }, delay)
    }) as Promise<ReturnType<T>>
  }
}

export function throttleAsync<T extends (...args: unknown[]) => Promise<unknown>>(
  fn: T,
  limit: number
): (...args: Parameters<T>) => Promise<ReturnType<T>> {
  let lastRun = 0
  let pending: { resolve: (value: unknown) => void; reject: (reason?: unknown) => void; args: Parameters<T> } | null = null
  let timeoutId: ReturnType<typeof setTimeout> | null = null

  const run = async () => {
    if (!pending) return

    const { resolve, reject, args } = pending
    pending = null

    try {
      const result = await fn(...args)
      resolve(result)
    } catch (error) {
      reject(error)
    }

    lastRun = Date.now()
  }

  return function (this: unknown, ...args: Parameters<T>): Promise<ReturnType<T>> {
    return new Promise((resolve, reject) => {
      const now = Date.now()
      const timeSinceLastRun = now - lastRun

      pending = { resolve: resolve as (value: unknown) => void, reject, args }

      if (timeSinceLastRun >= limit) {
        run()
      } else if (!timeoutId) {
        timeoutId = setTimeout(() => {
          timeoutId = null
          run()
        }, limit - timeSinceLastRun)
      }
    }) as Promise<ReturnType<T>>
  }
}

export function leadingDebounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout> | null = null
  let called = false

  return function (this: unknown, ...args: Parameters<T>) {
    if (!called) {
      fn.apply(this, args)
      called = true
    }

    if (timeoutId) {
      clearTimeout(timeoutId)
    }

    timeoutId = setTimeout(() => {
      called = false
      timeoutId = null
    }, delay)
  }
}
