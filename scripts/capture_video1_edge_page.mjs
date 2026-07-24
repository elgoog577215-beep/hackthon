import { mkdir, writeFile } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require('/Users/yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')

const cdpEndpoint = process.env.EDGE_CDP_URL ?? 'http://127.0.0.1:9224'
const outputDir = process.env.VIDEO1_FRAME_DIR
const frameRate = Number(process.env.VIDEO1_FRAME_RATE ?? 15)
const durationSeconds = Number(process.env.VIDEO1_DURATION ?? 70)
if (!outputDir) throw new Error('缺少 VIDEO1_FRAME_DIR')

await mkdir(outputDir, { recursive: true })
const browser = await chromium.connectOverCDP(cdpEndpoint)
const page = browser.contexts()[0].pages().find(item => item.url().includes('demo-ai-literacy-update-v1'))
if (!page) throw new Error(`未在 ${cdpEndpoint} 找到视频一页面`)

await page.waitForFunction(() => document.documentElement.dataset.video1Capture === 'started', null, { timeout: 30_000 })
const session = await page.context().newCDPSession(page)
let latestFrame = null
session.on('Page.screencastFrame', event => {
  latestFrame = Buffer.from(event.data, 'base64')
  void session.send('Page.screencastFrameAck', { sessionId: event.sessionId })
})
await session.send('Page.startScreencast', {
  format: 'jpeg',
  quality: 82,
  maxWidth: 1920,
  maxHeight: 1080,
  everyNthFrame: 1,
})
for (let attempt = 0; attempt < 100 && !latestFrame; attempt += 1) {
  await new Promise(resolve => setTimeout(resolve, 20))
}
if (!latestFrame) throw new Error('Edge screencast 没有返回首帧')

const totalFrames = Math.round(frameRate * durationSeconds)
const startedAt = performance.now()
for (let index = 0; index < totalFrames; index += 1) {
  const targetAt = startedAt + index * (1000 / frameRate)
  const wait = targetAt - performance.now()
  if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait))
  await writeFile(path.join(outputDir, `frame-${String(index).padStart(5, '0')}.jpg`), latestFrame)
}

await session.send('Page.stopScreencast')
console.log(JSON.stringify({ outputDir, frameRate, totalFrames, elapsed: (performance.now() - startedAt) / 1000 }))
await browser.close()
