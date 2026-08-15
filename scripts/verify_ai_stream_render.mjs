/**
 * Streaming-render probe for the AI teacher answer.
 *
 * Drives the REAL store (`sendMessage` → reader loop → `handleEvent`) and the
 * REAL `SideAIPanel`/`MarkdownRenderer` with a chunked SSE body whose timing
 * matches production (~214 chunks over ~5.3s), then records rendered text
 * length with a MutationObserver.
 *
 * A MutationObserver is used deliberately: low-frequency polling only proves
 * the text changed at some point, which is exactly how a non-streaming render
 * was previously mistaken for a working one. Here every DOM mutation is
 * timestamped, so "one big jump at the end" and "continuous growth" cannot be
 * confused.
 *
 * Usage: node scripts/verify_ai_stream_render.mjs
 * Exits non-zero when rendering is not chunk-driven.
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
  const candidates = [
    process.env.PLAYWRIGHT_MODULE,
    'playwright',
    '/home/ubuntu/verify-mermaid/node_modules/playwright',
    '/tmp/node_modules/playwright',
  ].filter(Boolean)
  for (const candidate of candidates) {
    try {
      return require.resolve(candidate)
    } catch {
      // try the next candidate
    }
  }
  throw new Error('playwright not found. Set PLAYWRIGHT_MODULE to its path.')
}

// Mirrors the reported production shape: 214 chunks across ~5.3 seconds.
const CHUNK_COUNT = 214
const CHUNK_INTERVAL_MS = 25

const harness = `
<!doctype html>
<html><head><meta charset="utf-8" />
<style>
  body { margin:0; font-family:system-ui,-apple-system,"PingFang SC",sans-serif; background:#f8fafc;
         --lz-brand:#6366f1; --lz-brand-strong:#4f46e5; --lz-text:#1e293b; --lz-text-strong:#0f172a;
         --lz-text-secondary:#475569; --lz-text-muted:#94a3b8; --lz-surface-soft:#f1f5f9;
         --lz-success:#16a34a; --lz-success-soft:#f0fdf4; --lz-danger:#dc2626; --lz-danger-soft:#fef2f2; }
</style>
</head><body><div id="app"></div>
<script type="module">
  import { createApp, h, ref } from 'vue'
  import { createPinia } from 'pinia'
  import SideAIPanel from '/src/components/SideAIPanel.vue'
  import { useAITeacherStore } from '/src/stores/aiTeacher'
  import { useCourseStore } from '/src/stores/course'
  import { setLocale } from '/src/shared/i18n'

  const params = new URLSearchParams(location.search)
  const locale = params.get('locale') || 'zh'
  await setLocale(locale)

  const CHUNK_COUNT = ${CHUNK_COUNT}
  const CHUNK_INTERVAL_MS = ${CHUNK_INTERVAL_MS}

  const WORD = locale === 'en'
    ? 'Linear dependence means some non-trivial combination vanishes. '
    : '线性相关表示存在一组不全为零的系数使组合为零。'

  const chunks = Array.from({ length: CHUNK_COUNT }, (_, index) =>
    WORD.slice(index % WORD.length, (index % WORD.length) + 3) || WORD.slice(0, 3))
  const finalAnswer = chunks.join('')

  const encoder = new TextEncoder()
  const sse = (event, data) => encoder.encode(
    'event: ' + event + '\\ndata: ' + JSON.stringify(data) + '\\n\\n')

  // Replace only the network boundary. Everything downstream — the reader
  // loop, handleEvent, the store's reactivity, the components — is real.
  window.__streamDone = false
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const url = String(input?.url || input)
    if (!url.includes('/api/ask_events')) return originalFetch(input, init)
    const body = new ReadableStream({
      async start(controller) {
        controller.enqueue(sse('context', {
          conversation_id: 'conv-probe',
          user_message_id: 'user-probe',
          assistant_message_id: 'assistant-probe',
        }))
        controller.enqueue(sse('sources', { sources: [] }))
        for (const chunk of chunks) {
          await new Promise(resolve => setTimeout(resolve, CHUNK_INTERVAL_MS))
          controller.enqueue(sse('answer', { chunk }))
        }
        controller.enqueue(sse('final_answer', { answer: finalAnswer, message_id: 'assistant-probe' }))
        controller.enqueue(sse('done', { conversation_id: 'conv-probe', message_id: 'assistant-probe' }))
        controller.close()
        window.__streamDone = true
        window.__streamEndedAt = performance.now()
      },
    })
    return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
  }

  const pinia = createPinia()
  const app = createApp({
    setup() {
      return () => h(SideAIPanel, {
        visible: true, quoteText: '', quoteNodeId: 'node-1',
      })
    },
  })
  app.use(pinia)
  app.mount('#app')

  const courseStore = useCourseStore()
  courseStore.currentCourseId = 'course-probe'
  const node = { node_id: 'node-1', node_name: '向量空间', node_level: 2, parent_node_id: 'chapter-1', node_content: '' }
  courseStore.nodes = [node]
  courseStore.currentNode = node

  const aiStore = useAITeacherStore()
  const cold = params.get('cold') === '1'
  if (cold) {
    // Production shape: the store has nothing yet, so sendMessage() triggers
    // load() -> createConversation() before it starts streaming.
    aiStore.courseId = ''
    aiStore.conversations = []
    aiStore.currentConversationId = ''
  } else {
    aiStore.load = async () => {}
    aiStore.courseId = 'course-probe'
    aiStore.conversations = [{
      conversation_id: 'conv-probe', course_id: 'course-probe', title: 'probe',
      revision: 1, retrieval_enabled: false, messages: [],
      created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
    }]
    aiStore.currentConversationId = 'conv-probe'
  }

  // Every DOM mutation under the message list is timestamped. Nothing is
  // sampled, so a single end-of-stream repaint cannot masquerade as streaming.
  window.__samples = []
  const start = performance.now()
  const observer = new MutationObserver(() => {
    const node = document.querySelector('.assistant-answer')
    window.__samples.push({ t: performance.now() - start, len: (node?.textContent || '').length })
  })
  observer.observe(document.getElementById('app'), {
    childList: true, subtree: true, characterData: true,
  })

  window.__expected = { chunkCount: CHUNK_COUNT, finalLength: finalAnswer.length }
  window.__run = async () => {
    await aiStore.sendMessage({ courseId: 'course-probe', question: '什么是线性相关？', nodeId: 'node-1' })
    window.__renderDone = true
  }
  document.documentElement.dataset.ready = '1'
</script></body></html>
`

async function main() {
  await writeFile(path.join(root, 'stream-probe.html'), harness, 'utf-8')
  const server = await createServer({
    root,
    configFile: path.join(root, 'vite.config.ts'),
    server: { port: 5197, strictPort: true },
    logLevel: 'error',
    plugins: [{
      // The store's non-streaming calls must succeed for the real
      // load() / createConversation() / refreshConversation() path to run —
      // that path is where the reactive identity of the conversation is
      // decided, so stubbing it would hide the defect under test.
      name: 'ai-teacher-probe-api',
      configureServer(devServer) {
        devServer.middlewares.use((req, res, next) => {
          const url = req.url || ''
          if (!url.startsWith('/api/')) return next()
          const send = (payload) => {
            res.setHeader('Content-Type', 'application/json')
            res.end(JSON.stringify(payload))
          }
          const conversation = {
            conversation_id: 'conv-probe', course_id: 'course-probe', title: 'probe',
            revision: 1, retrieval_enabled: false, messages: globalThis.__probeMessages || [],
            created_at: '2026-08-12T00:00:00Z', updated_at: '2026-08-12T00:00:00Z',
          }
          if (url.startsWith('/api/ai-teacher/conversations?')) return send({ conversations: [] })
          if (url.startsWith('/api/ai-teacher/conversations/')) return send(conversation)
          if (url === '/api/ai-teacher/conversations') return send(conversation)
          if (url.startsWith('/api/ai-teacher/trigger')) return send({ candidate: null })
          return send({})
        })
      },
    }],
  })
  await server.listen()

  const browser = await chromium.launch()
  const failures = []
  const report = []

  try {
    const cases = []
    for (const locale of ['zh', 'en']) {
      for (const cold of ['0', '1']) cases.push({ locale, cold })
    }
    for (const { locale, cold } of cases) {
      const context = await browser.newContext({ viewport: { width: 1280, height: 900 } })
      const page = await context.newPage()
      await page.goto(
        `http://127.0.0.1:5197/stream-probe.html?locale=${locale}&cold=${cold}`,
        { waitUntil: 'networkidle' },
      )
      await page.waitForFunction(() => document.documentElement.dataset.ready === '1')
      await page.evaluate(() => window.__run())
      await page.waitForFunction(() => window.__renderDone === true, null, { timeout: 60_000 })

      const result = await page.evaluate(() => ({
        samples: window.__samples,
        expected: window.__expected,
        streamEndedAt: window.__streamEndedAt,
      }))

      const growth = []
      let previous = -1
      for (const sample of result.samples) {
        if (sample.len > previous) {
          growth.push(sample)
          previous = sample.len
        }
      }
      const distinct = new Set(growth.map(item => item.len))
      const finalLength = growth.length ? growth[growth.length - 1].len : 0
      // How much of the answer was on screen while the stream was still open?
      const beforeEnd = growth.filter(item => item.t < (result.streamEndedAt ?? Infinity))
      const visibleAtStreamEnd = beforeEnd.length ? beforeEnd[beforeEnd.length - 1].len : 0
      const coverage = finalLength ? visibleAtStreamEnd / finalLength : 0

      const label = `${locale}/${cold === '1' ? 'cold-start' : 'warm'}`
      report.push(
        `${label}: ${distinct.size} distinct lengths, `
        + `${Math.round(coverage * 100)}% rendered before the stream closed, `
        + `final ${finalLength} chars`,
      )

      // A chunk-driven render produces many intermediate lengths. Two values
      // ("empty, then everything") is the exact signature of the defect.
      if (distinct.size < 20) {
        failures.push(
          `${label}: only ${distinct.size} distinct rendered lengths for `
          + `${result.expected.chunkCount} chunks — rendering is not chunk-driven `
          + `(${[...distinct].slice(0, 8).join(', ')}${distinct.size > 8 ? ', …' : ''})`,
        )
      }
      // And most of the answer must be visible before the stream ends, not after.
      if (coverage < 0.6) {
        failures.push(
          `${label}: only ${Math.round(coverage * 100)}% of the answer was rendered `
          + `before the stream closed — the text appears after streaming, not during`,
        )
      }
      if (finalLength !== result.expected.finalLength) {
        failures.push(
          `${label}: final rendered length ${finalLength} != expected `
          + `${result.expected.finalLength}`,
        )
      }
      await context.close()
    }
  } finally {
    await browser.close()
    await server.close()
    await rm(path.join(root, 'stream-probe.html'), { force: true })
  }

  console.log(report.join('\n'))
  if (failures.length) {
    console.error(`\nFAILED (${failures.length}):`)
    for (const failure of failures) console.error(`  - ${failure}`)
    process.exit(1)
  }
  console.log('\nPASS: answer text grows continuously while the stream is open (zh + en).')
}

await main()
