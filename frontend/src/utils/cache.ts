interface CacheItem<T> {
  data: T
  timestamp: number
  ttl: number
}

class RequestCache {
  private cache: Map<string, CacheItem<unknown>> = new Map()
  private defaultTTL: number = 5 * 60 * 1000

  set<T>(key: string, data: T, ttl: number = this.defaultTTL): void {
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      ttl
    })
  }

  get<T>(key: string): T | null {
    const item = this.cache.get(key)
    if (!item) return null

    if (Date.now() - item.timestamp > item.ttl) {
      this.cache.delete(key)
      return null
    }

    return item.data as T
  }

  has(key: string): boolean {
    return this.get(key) !== null
  }

  delete(key: string): boolean {
    return this.cache.delete(key)
  }

  clear(): void {
    this.cache.clear()
  }

  clearPattern(pattern: RegExp): void {
    for (const key of this.cache.keys()) {
      if (pattern.test(key)) {
        this.cache.delete(key)
      }
    }
  }

  invalidateCourse(courseId: string): void {
    this.clearPattern(new RegExp(`/courses/${courseId}`))
  }

  getStats(): { size: number; keys: string[] } {
    return {
      size: this.cache.size,
      keys: Array.from(this.cache.keys())
    }
  }
}

export const requestCache = new RequestCache()

export function createCachedRequest<T>(
  keyFn: (...args: unknown[]) => string,
  fetcher: (...args: unknown[]) => Promise<T>,
  ttl?: number
): (...args: unknown[]) => Promise<T> {
  return async (...args: unknown[]) => {
    const key = keyFn(...args)
    const cached = requestCache.get<T>(key)
    if (cached !== null) {
      return cached
    }

    const data = await fetcher(...args)
    requestCache.set(key, data, ttl)
    return data
  }
}

export default requestCache
