/**
 * 轻量生产服务器（替代 nginx）
 * 功能：托管 dist/ 静态文件 + 反向代理 /api → 后端
 * 用法：node serve-prod.cjs
 */
const http = require('http')
const fs = require('fs')
const path = require('path')
const url = require('url')

const PORT = Number.parseInt(process.env.PORT || '5173', 10)
const HOST = process.env.HOST || '0.0.0.0'
const BACKEND = process.env.BACKEND_URL || 'http://127.0.0.1:8000'
const LINGZHI_BACKEND = process.env.LINGZHI_BACKEND_URL || 'http://127.0.0.1:7860'
const DIST = path.join(__dirname, 'dist')

if (!Number.isInteger(PORT) || PORT < 1 || PORT > 65535) {
  throw new Error(`Invalid PORT: ${process.env.PORT}`)
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.eot': 'application/vnd.ms-fontobject',
}

function serveStatic(req, res) {
  let filePath = path.join(DIST, url.parse(req.url).pathname)
  if (filePath.endsWith('/')) filePath = path.join(filePath, 'index.html')

  fs.stat(filePath, (err, stat) => {
    if (err || !stat.isFile()) {
      // SPA fallback
      fs.readFile(path.join(DIST, 'index.html'), (e, data) => {
        if (e) { res.writeHead(500); res.end('Server Error'); return }
        res.writeHead(200, {
          'Content-Type': 'text/html; charset=utf-8',
          'Cache-Control': 'no-cache, no-store, must-revalidate',
        })
        res.end(data)
      })
      return
    }

    const ext = path.extname(filePath)
    const mime = MIME[ext] || 'application/octet-stream'
    const isAsset = req.url.startsWith('/assets/')
    res.writeHead(200, {
      'Content-Type': mime,
      'Cache-Control': isAsset ? 'public, max-age=2592000, immutable' : 'no-cache',
    })
    fs.createReadStream(filePath).pipe(res)
  })
}

function proxyRequest(req, res, targetBase, stripPrefix) {
  const targetUrl = new URL(req.url.replace(stripPrefix, '') || '/', targetBase)
  const opts = {
    hostname: targetUrl.hostname,
    port: targetUrl.port,
    path: targetUrl.pathname + targetUrl.search,
    method: req.method,
    headers: { ...req.headers, host: targetUrl.host },
  }

  const proxyReq = http.request(opts, (proxyRes) => {
    // SSE support: disable buffering
    res.writeHead(proxyRes.statusCode, proxyRes.headers)
    proxyRes.pipe(res)
  })

  proxyReq.on('error', (e) => {
    console.error('[proxy error]', e.message)
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' })
    }
    res.end(JSON.stringify({ error: 'Backend unavailable' }))
  })

  req.pipe(proxyReq)
}

const server = http.createServer((req, res) => {
  if (req.url === '/lingzhi') {
    res.writeHead(308, { Location: '/lingzhi/' })
    res.end()
  } else if (req.url.startsWith('/lingzhi/')) {
    proxyRequest(req, res, LINGZHI_BACKEND, '/lingzhi')
  } else if (req.url.startsWith('/api/')) {
    proxyRequest(req, res, BACKEND, '/api')
  } else if (req.url.startsWith('/static/')) {
    proxyRequest(req, res, BACKEND, '')
  } else {
    serveStatic(req, res)
  }
})

function proxyUpgrade(req, socket, head, targetBase, stripPrefix) {
  const targetUrl = new URL(req.url.replace(stripPrefix, '') || '/', targetBase)
  const proxyReq = http.request({
    hostname: targetUrl.hostname,
    port: targetUrl.port,
    path: targetUrl.pathname + targetUrl.search,
    method: req.method,
    headers: { ...req.headers, host: targetUrl.host },
  })

  proxyReq.on('upgrade', (proxyRes, proxySocket, proxyHead) => {
    const headers = Object.entries(proxyRes.headers)
      .flatMap(([name, value]) => Array.isArray(value)
        ? value.map((item) => `${name}: ${item}`)
        : [`${name}: ${value}`])
      .join('\r\n')
    socket.write(`HTTP/1.1 ${proxyRes.statusCode} ${proxyRes.statusMessage}\r\n${headers}\r\n\r\n`)
    if (proxyHead.length) socket.write(proxyHead)
    if (head.length) proxySocket.write(head)
    proxySocket.pipe(socket).pipe(proxySocket)
  })

  proxyReq.on('error', (error) => {
    console.error('[websocket proxy error]', error.message)
    socket.destroy()
  })

  proxyReq.end()
}

server.on('upgrade', (req, socket, head) => {
  if (req.url.startsWith('/lingzhi/ws')) {
    proxyUpgrade(req, socket, head, LINGZHI_BACKEND, '/lingzhi')
    return
  }
  socket.destroy()
})

server.listen(PORT, HOST, () => {
  console.log(`[serve-prod] 前端已启动: http://${HOST}:${PORT}`)
  console.log(`[serve-prod] API 代理: /api/* → ${BACKEND}`)
  console.log(`[serve-prod] 灵知代理: /lingzhi/* → ${LINGZHI_BACKEND}`)
})
