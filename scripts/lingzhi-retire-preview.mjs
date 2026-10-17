import { createServer } from 'node:http'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

export function redirectTarget(value) {
  const url = new URL(value)
  if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname)
      || url.username || url.password || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('The replacement must be a local frontend origin')
  }
  return url.origin
}

export function retiredPreviewHandler(target) {
  const origin = redirectTarget(target)
  return (req, res) => {
    const incoming = new URL(req.url, 'http://127.0.0.1')
    res.setHeader('Cache-Control', 'no-store')
    // Old pages must reload before using the real course. Never forward their
    // API calls or writes from an isolated snapshot into the main repository.
    if (!['GET', 'HEAD'].includes(req.method) || /^\/(?:api|ws|health)(?:\/|$)/.test(incoming.pathname)
        || /\.(?:js|css|map|json|png|svg|webp|woff2?)$/i.test(incoming.pathname)) {
      res.statusCode = 410
      res.setHeader('Content-Type', 'application/json; charset=utf-8')
      res.end(JSON.stringify({ error: 'preview_retired', reload_url: origin + incoming.pathname + incoming.search }))
      return
    }
    res.statusCode = 307
    res.setHeader('Location', origin + incoming.pathname + incoming.search)
    res.end()
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    const port = Number(process.argv[2]), target = redirectTarget(process.argv[3])
    if (!Number.isInteger(port) || port < 1024 || port > 65535 || port === Number(new URL(target).port)) {
      throw new Error('Use a separate local port for the retired preview')
    }
    const health = await fetch(`${target}/health`, { signal: AbortSignal.timeout(5000), redirect: 'error' })
    if (!health.ok || (await health.json()).status !== 'ok') throw new Error('Replacement frontend is unavailable')
    createServer(retiredPreviewHandler(target)).listen(port, '127.0.0.1', () => {
      console.log(`Preview ${port} retired; browser navigation now opens ${target}`)
    })
  } catch (error) {
    console.error(error.message)
    process.exitCode = 1
  }
}
