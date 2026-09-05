/**
 * End-to-end streaming-render probe against the REAL backend and REAL model.
 *
 * Nothing is faked: the page talks to 127.0.0.1:8000 through Vite's proxy,
 * `/api/ask_events` streams from the actual provider, and the real
 * SideAIPanel/MarkdownRenderer render it. A MutationObserver timestamps every
 * DOM change, so "text appears all at once at the end" cannot be mistaken for
 * streaming — which is exactly the mistake a low-frequency poll makes.
 *
 * Requires the backend on :8000 and a seeded course.
 * Usage: node scripts/verify_ai_stream_render_e2e.mjs [courseId] [nodeId]
 */
import { writeFile, rm } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..', 'frontend')
const require = createRequire(path.join(root, 'package.json'))

const { createServer } = require('vite')
const { chromium } = require(resolvePlaywright())

function resolvePlaywright() {
  for (const candidate of [
    process.env.PLAYWRIGHT_MODULE,
    'playwright',
    '/home/ubuntu/verify-mermaid/node_modules/playwright',
    '/tmp/node_modules/playwright',
  ].filter(Boolean)) {
    try { return require.resolve(candidate) } catch { /* next */ }
  }
  throw new Error('playwright not found. Set PLAYWRIGHT_MODULE to its path.')
}

const COURSE_ID = process.argv[2] || 'stream-probe-course'
const NODE_ID = process.argv[3] || 'node-1'

const harness = `
<!doctype html>
<html><head><meta charset="utf-8" />
<style>
  body { margin:0; font-family:system-ui,-apple-system,"PingFang SC",sans-serif; background:#f8fafc;
         --lz-brand:#6366f1; --lz-brand-strong:#4f46e5; --lz-text:#1e293b; --lz-text-strong:#0f172a;
         --lz-text-secondary:#475569; --lz-text-muted:#94a3b8; --lz-surface-soft:#f1f5f9;
         --lz-success:#16a34a; --lz-success-soft:#f0fdf4; --lz-danger:#dc2626; --lz-danger-soft:#fef2f2; }
  #app { max-width:520px; }
</style>
</head><body><div id="app"></div>
<script type="module">
  import { createApp, h } from 'vue'
  import { createPinia } from 'pinia'
  import SideAIPanel from '/src/components/SideAIPanel.vue'
  import { useAITeacherStore } from '/src/stores/aiTeacher'
  import { useCourseStore } from '/src/stores/course'
  import { setLocale } from '/src/shared/i18n'

  const params = new URLSearchParams(location.search)
  await setLocale(params.get('locale') || 'zh')
  const courseId = params.get('courseId')
  const nodeId = params.get('nodeId')

  const pinia = createPinia()
  const app = createApp({
    setup: () => () => h(SideAIPanel, { visible: true, quoteText: '', quoteNodeId: nodeId }),
  })
  app.use(pinia)
  app.mount('#app')

  const courseStore = useCourseStore()
  courseStore.currentCourseId = courseId
  const node = { node_id: nodeId, node_name: '1.1 线性相关的定义', node_level: 2,
                 parent_node_id: 'chapter-1', node_content: '' }
  courseStore.nodes = [node]
  courseStore.currentNode = node

  const aiStore = useAITeacherStore()

  // Timestamp every DOM mutation; no sampling anywhere.
  window.__samples = []
  const start = performance.now()
  new MutationObserver(() => {
    const el = document.querySelector('.assistant-answer')
    window.__samples.push({ t: performance.now() - start, len: (el?.textContent || '').length })
  }).observe(document.getElementById('app'), { childList: true, subtree: true, characterData: true })

  // Independently record when each SSE answer chunk arrives, so the render
  // timeline can be compared against the transport timeline.
  window.__chunkTimes = []
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = String(input?.url || input)
    const response = await originalFetch(input, init)
    if (!url.includes('/api/ask_events') || !response.body) return response
    const decoder = new TextDecoder()
    const observed = new TransformStream({
      transform(value, controller) {
        const text = decoder.decode(value, { stream: true })
        for (const line of text.split('\\n')) {
          if (line.startsWith('data:') && line.includes('"chunk"')) {
            window.__chunkTimes.push(performance.now() - start)
          }
        }
        controller.enqueue(value)
      },
    })
    return new Response(response.body.pipeThrough(observed), {
      status: response.status, headers: response.headers,
    })
  }

  window.__run = async (question) => {
    await aiStore.sendMessage({ courseId, question, nodeId, entrypoint: 'global' })
    window.__renderDone = true
  }
  document.documentElement.dataset.ready = '1'
</script></body></html>
`

async function main() {
  await writeFile(path.join(root, 'stream-e2e-probe.html'), harness, 'utf-8')
  const server = await createServer({
    root,
    configFile: path.join(root, 'vite.config.ts'),
    server: { port: 5196, strictPort: true },
    logLevel: 'error',
  })
  await server.listen()

  const browser = await chromium.launch()
  const failures = []
  const report = []

  try {
    for (const [locale, question] of [
      ['zh', '请详细解释什么是线性相关，并举一个具体例子。'],
      ['en', 'Please explain in detail what linear dependence means, with an example.'],
    ]) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
      const page = await context.newPage()
      await page.goto(
        `http://127.0.0.1:5196/stream-e2e-probe.html`
        + `?locale=${locale}&courseId=${COURSE_ID}&nodeId=${NODE_ID}`,
        { waitUntil: 'networkidle' },
      )
      await page.waitForFunction(() => document.documentElement.dataset.ready === '1')
      const running = page.evaluate(q => window.__run(q), question)
      // Capture the screen while the stream is still open: partial text on
      // screen is the visible proof that rendering is not deferred to the end.
      await page.waitForFunction(
        () => (document.querySelector('.assistant-answer')?.textContent || '').length > 60,
        null, { timeout: 120_000 },
      ).catch(() => {})
      await page.screenshot({
        path: path.join(root, '..', `design-qa-ai-stream-midflight-${locale}.png`),
        clip: await page.locator('.assistant-message-column').boundingBox().catch(() => null)
          || { x: 0, y: 0, width: 520, height: 400 },
      }).catch(() => {})
      await running
      await page.waitForFunction(() => window.__renderDone === true, null, { timeout: 180_000 })

      const data = await page.evaluate(() => ({
        samples: window.__samples, chunkTimes: window.__chunkTimes,
      }))

      const growth = []
      let previous = -1
      for (const sample of data.samples) {
        if (sample.len > previous) { growth.push(sample); previous = sample.len }
      }
      const distinct = new Set(growth.map(item => item.len))
      const finalLength = growth.length ? growth[growth.length - 1].len : 0
      const chunkCount = data.chunkTimes.length
      const lastChunkAt = chunkCount ? data.chunkTimes[chunkCount - 1] : 0
      const firstChunkAt = chunkCount ? data.chunkTimes[0] : 0
      const renderedDuringStream = growth.filter(item => item.t <= lastChunkAt + 50)
      const visibleDuringStream = renderedDuringStream.length
        ? renderedDuringStream[renderedDuringStream.length - 1].len : 0
      const coverage = finalLength ? visibleDuringStream / finalLength : 0

      report.push(
        `${locale}: ${chunkCount} chunks over ${Math.round(lastChunkAt - firstChunkAt)}ms | `
        + `${distinct.size} distinct rendered lengths | `
        + `${Math.round(coverage * 100)}% on screen before the last chunk | `
        + `final ${finalLength} chars`,
      )
      // Perceived smoothness: how long the text sat frozen between repaints,
      // and how big a jump each repaint made. A large max gap is what a person
      // reports as "it appeared all at once".
      const gaps = []
      for (let i = 1; i < growth.length; i += 1) gaps.push(growth[i].t - growth[i - 1].t)
      const jumps = []
      for (let i = 1; i < growth.length; i += 1) jumps.push(growth[i].len - growth[i - 1].len)
      const maxGap = gaps.length ? Math.max(...gaps) : 0
      const maxJump = jumps.length ? Math.max(...jumps) : 0
      report.push(
        `  first lengths: ${[...distinct].slice(0, 10).join(', ')}`
        + `${distinct.size > 10 ? ' …' : ''}`,
      )
      report.push(
        `  repaint gap: max ${Math.round(maxGap)}ms | biggest single jump ${maxJump} chars `
        + `| ${chunkCount} chunks coalesced into ${growth.length} repaints`,
      )
      // The honest question is not "was the screen ever still" — the provider
      // itself pauses — but "once a chunk arrived, how long until it showed".
      // For each chunk, find the first repaint at or after it.
      const latencies = []
      let cursor = 0
      for (const chunkAt of data.chunkTimes) {
        while (cursor < growth.length && growth[cursor].t < chunkAt) cursor += 1
        if (cursor < growth.length) latencies.push(growth[cursor].t - chunkAt)
      }
      latencies.sort((a, b) => a - b)
      const p50 = latencies.length ? latencies[Math.floor(latencies.length * 0.5)] : 0
      const p95 = latencies.length ? latencies[Math.floor(latencies.length * 0.95)] : 0
      report.push(
        `  chunk -> paint latency: p50 ${Math.round(p50)}ms, p95 ${Math.round(p95)}ms `
        + `| longest still-frame ${Math.round(maxGap)}ms (includes provider idle)`,
      )

      // A chunk-driven renderer paints within a frame or two of each chunk.
      //
      // Thresholds come from measuring both implementations against the real
      // model on this machine:
      //   150ms timer throttle : p50 84/74ms, p95 220/156ms  (the defect)
      //   rAF-aligned render   : p50 19/18ms, p95 122/115ms  (the fix)
      // p50 separates the two cleanly, so it carries the gate; p95 is kept as
      // a looser ceiling against outright stalls.
      if (p50 > 45) {
        failures.push(
          `${locale}: p50 chunk-to-paint latency ${Math.round(p50)}ms — the typical chunk `
          + `waits more than a couple of frames before it is shown`,
        )
      }
      if (p95 > 400) {
        failures.push(
          `${locale}: p95 chunk-to-paint latency ${Math.round(p95)}ms — arriving text `
          + `waits too long before it is shown`,
        )
      }
      if (chunkCount < 5) {
        failures.push(
          `${locale}: only ${chunkCount} answer chunks arrived — a transport problem, `
          + `not a render problem`,
        )
      }
      if (distinct.size < 10) {
        failures.push(
          `${locale}: only ${distinct.size} distinct rendered lengths for ${chunkCount} chunks `
          + `(${[...distinct].join(', ')}) — the answer is NOT rendered chunk by chunk`,
        )
      }
      if (coverage < 0.6) {
        failures.push(
          `${locale}: only ${Math.round(coverage * 100)}% of the answer was on screen before `
          + `the final chunk — text appears after streaming ends`,
        )
      }
      await context.close()
    }
  } finally {
    await browser.close()
    await server.close()
    await rm(path.join(root, 'stream-e2e-probe.html'), { force: true })
  }

  console.log(report.join('\n'))
  if (failures.length) {
    console.error(`\nFAILED (${failures.length}):`)
    for (const failure of failures) console.error(`  - ${failure}`)
    process.exit(1)
  }
  console.log('\nPASS: real backend + real model, answer grows continuously while streaming (zh + en).')
}

await main()
