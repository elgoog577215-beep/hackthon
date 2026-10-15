type Result = { svg: string; error?: never } | { svg?: never; error: unknown }
type Job = { source: string; hosts: Set<HTMLElement> }

/** Give cached Mermaid output independent SVG, marker and CSS identities. */
export function identifyMermaidSvg(svg: string, prefix: string): string {
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  const ids = new Map<string, string>()
  doc.querySelectorAll('[id]').forEach((el, index) => ids.set(el.id, `${prefix}-${index}`))
  const selectors = (value: string) => value.replace(/#([\w:.-]+)/g, (match, id: string) => {
    if (ids.has(id)) return `#${ids.get(id)}`
    // CSS may append a class or pseudo selector directly after an ID.
    for (const [oldId, newId] of ids) {
      if (id.startsWith(`${oldId}.`) || id.startsWith(`${oldId}:`)) return `#${newId}${id.slice(oldId.length)}`
    }
    return match
  })
  const urlReferences = (value: string) => value.replace(/url\(\s*(['"]?)#([\w:.-]+)\1\s*\)/g,
    (match, quote: string, id: string) => ids.has(id) ? `url(${quote}#${ids.get(id)}${quote})` : match)
  doc.querySelectorAll('*').forEach(el => {
    for (const attr of Array.from(el.attributes)) {
      if (attr.name === 'id') el.setAttribute('id', ids.get(attr.value) || attr.value)
      else if (attr.name === 'aria-labelledby' || attr.name === 'aria-describedby') {
        el.setAttribute(attr.name, attr.value.split(/\s+/).map(id => ids.get(id) || id).join(' '))
      } else if (attr.localName === 'href' && attr.value.startsWith('#') && ids.has(attr.value.slice(1))) {
        el.setAttribute(attr.name, `#${ids.get(attr.value.slice(1))}`)
      } else if (attr.value.includes('url(')) el.setAttribute(attr.name, urlReferences(attr.value))
    }
    if (el.tagName.toLowerCase() === 'style') {
      // Mermaid emits CSS rule selectors followed by declaration blocks.
      // A hexadecimal color can equal a user-defined Gantt task ID (e.g. fff),
      // so only selectors and explicit url(#...) references are rewritten.
      el.textContent = urlReferences(el.textContent || '').replace(/(^|[{}])([^{}]+)(?=\{)/g,
        (_match, separator: string, selector: string) => separator + selectors(selector))
    }
  })
  return new XMLSerializer().serializeToString(doc.documentElement)
}

/** One active Mermaid job per renderer; removed hosts never receive late work. */
export function createMarkdownMermaidQueue(
  prefix: string,
  renderSvg: (id: string, source: string) => Promise<string>,
  display: (host: HTMLElement, result: Result) => void,
) {
  const current = new Map<HTMLElement, string>()
  const jobs = new Map<string, Job>()
  const waiting: Job[] = []
  const cache = new Map<string, Result>()
  let running = false, disposed = false, identity = 0, cacheSize = 0
  const weight = (source: string, result: Result) => source.length + (result.svg?.length || 0)

  function deliver(host: HTMLElement, source: string, result: Result) {
    if (disposed || current.get(host) !== source) return
    display(host, result.svg !== undefined
      ? { svg: identifyMermaidSvg(result.svg, `${prefix}-svg-${++identity}`) }
      : result)
  }

  async function drain() {
    if (running || disposed) return
    running = true
    try {
      while (waiting.length && !disposed) {
        const job = waiting.shift()!
        if (!job.hosts.size) { jobs.delete(job.source); continue }
        let result: Result
        try { result = { svg: await renderSvg(`${prefix}-render-${++identity}`, job.source) } }
        catch (error) { result = { error } }
        jobs.delete(job.source)
        if (disposed) break
        // A failed import/network request may recover. Keep the fallback on
        // its current host without caching that failure for a future host.
        const size = weight(job.source, result)
        if (result.svg !== undefined && size <= 1_000_000) {
          cache.set(job.source, result)
          cacheSize += size
          while (cache.size > 16 || cacheSize > 1_000_000) {
            const first = cache.keys().next().value!
            cacheSize -= weight(first, cache.get(first)!)
            cache.delete(first)
          }
        }
        for (const host of job.hosts) deliver(host, job.source, result)
      }
    } finally { running = false }
  }

  function forget(host: HTMLElement) {
    const source = current.get(host)
    if (source !== undefined) {
      const job = jobs.get(source)
      job?.hosts.delete(host)
      if (job && !job.hosts.size) {
        const queued = waiting.indexOf(job)
        if (queued >= 0) { waiting.splice(queued, 1); jobs.delete(source) }
      }
    }
    current.delete(host)
  }

  return {
    observe(host: HTMLElement, source: string) {
      if (disposed || current.get(host) === source) return
      forget(host)
      current.set(host, source)
      const cached = cache.get(source)
      if (cached) {
        cache.delete(source); cache.set(source, cached)
        deliver(host, source, cached)
        return
      }
      let job = jobs.get(source)
      if (!job) { job = { source, hosts: new Set() }; jobs.set(source, job); waiting.push(job) }
      job.hosts.add(host)
      void drain()
    },
    forget,
    dispose() { disposed = true; current.clear(); jobs.clear(); waiting.length = 0; cache.clear(); cacheSize = 0 },
  }
}
