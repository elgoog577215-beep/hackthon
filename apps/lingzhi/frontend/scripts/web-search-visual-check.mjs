import { chromium } from 'playwright'
import { createServer } from 'vite'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { writeFileSync, rmSync } from 'node:fs'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')

// 真实来源：取自 2026-08-06 真实 SearXNG 检索结果，含超长 URL 用于验收折行。
const SUMMARY = {
  enabled: true,
  status: 'ready',
  degraded: false,
  message_code: 'web_search_ready',
  queries: ['线性代数 特征值 特征向量', '线性代数 讲义'],
  sources: [
    {
      source_id: 'src_mit',
      url: 'https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/resources/lecture-21-eigenvalues-and-eigenvectors/',
      title: 'Lecture 21: Eigenvalues and eigenvectors | Linear Algebra | Mathematics | MIT OpenCourseWare',
      domain: 'ocw.mit.edu',
      credibility: 'high',
      retrieved_at: '2026-08-06T16:35:48.169515+00:00',
    },
    {
      source_id: 'src_doi',
      url: 'https://doi.org/10.26549/jxffcxysj.v2i6.2354',
      title: '矩阵的特征值与特征向量的应用研究',
      domain: 'doi.org',
      credibility: 'high',
      retrieved_at: '2026-08-06T16:36:12.881204+00:00',
    },
  ],
  rejected: [
    { url: 'https://baike.baidu.com/item/%E7%BA%BF%E6%80%A7%E4%BB%A3%E6%95%B0/1198569', reason: 'low_relevance' },
    { url: 'https://www.zhihu.com/question/20084968', reason: 'low_relevance' },
    { url: 'https://blog.csdn.net/jiahao1186/article/details/155123456', reason: 'unsafe_url' },
  ],
}

const HARNESS_JS = `
import { createApp, h } from 'vue'
import { createPinia, setActivePinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import CourseTaskCenter from '@/components/CourseTaskCenter.vue'
import { setLocale } from '@/shared/i18n'
import { useGenerationStore } from '@/stores/generation'
import { useCourseStore } from '@/stores/course'
const SUMMARY = ${JSON.stringify(SUMMARY)}
const params = new URLSearchParams(location.search)
const pinia = createPinia(); setActivePinia(pinia)
const router = createRouter({ history: createMemoryHistory(), routes: [
  { path: '/', component: { render: () => null } },
  { path: '/courses', name: 'course-library', component: { render: () => null } },
  { path: '/course/:courseId/learn', name: 'learning', component: { render: () => null } },
]})
await setLocale(params.get('lang') || 'zh')
await router.push('/courses'); await router.isReady()
const gen = useGenerationStore()
gen.fetchGlobalTasks = async () => {}
gen.startGlobalMonitor = () => {}
gen.globalTasks = [{
  id: 'task-1', course_id: 'course-1', course_name: '线性代数', status: 'running',
  progress: 20, current_phase: 'material_processing', message: '正在处理参考资料',
  phase_detail: { web_search: SUMMARY },
}]
const courses = useCourseStore()
courses.fetchCourseList = async () => {}
courses.courseList = [{ course_id: 'course-1', course_name: '线性代数', node_count: 4 }]
createApp({ render: () => h(CourseTaskCenter, { modelValue: true, courseId: 'course-1' }) })
  .use(pinia).use(router).mount('#app')
window.__READY__ = true
`

const HARNESS = `
<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>body{margin:0;font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}</style>
</head><body><div id="app"></div>
<script type="module" src="/src/__visual-harness.js"></script>
</body></html>`

// harness 需要经 vite 转换裸模块说明符，因此临时落到 src/ 下，结束时清理。
const harnessPath = resolve(root, 'src/__visual-harness.js')
writeFileSync(harnessPath, HARNESS_JS)
process.on('exit', () => { try { rmSync(harnessPath) } catch {} })

const server = await createServer({
  root,
  server: { port: 5321, strictPort: true },
  plugins: [{
    name: 'harness',
    configureServer(s) {
      s.middlewares.use((req, res, next) => {
        if ((req.url || '').split('?')[0] === '/harness') {
          res.setHeader('Content-Type', 'text/html'); res.end(HARNESS); return
        }
        next()
      })
    },
  }],
})
await server.listen()

const browser = await chromium.launch()
const findings = []

for (const [lang, viewport, label] of [
  ['zh', { width: 1440, height: 900 }, 'zh-desktop'],
  ['en', { width: 1440, height: 900 }, 'en-desktop'],
  ['zh', { width: 390, height: 844 }, 'zh-mobile'],
  ['en', { width: 390, height: 844 }, 'en-mobile'],
]) {
  const page = await browser.newPage({ viewport })
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()) })
  await page.goto(`http://127.0.0.1:5321/harness?lang=${lang}`, { waitUntil: 'networkidle' })
  try {
    await page.waitForSelector('[data-testid="web-search-summary"]', { timeout: 15000 })
  } catch (e) {
    console.error('=== DEBUG', label, '===')
    console.error('errors:', errors.slice(0, 6))
    console.error('body:', (await page.locator('body').textContent() || '').slice(0, 400))
    throw e
  }

  const panel = page.locator('[data-testid="web-search-summary"]')
  await panel.scrollIntoViewIfNeeded()

  // 长 URL 折行：检查来源区是否横向溢出容器
  const overflow = await panel.evaluate(el => {
    const out = []
    for (const li of el.querySelectorAll('.web-search-summary__sources li, .web-search-summary__rejected li')) {
      if (li.scrollWidth > li.clientWidth + 1) out.push(li.textContent.trim().slice(0, 60))
    }
    const panelOverflow = el.scrollWidth > el.clientWidth + 1
    return { items: out, panelOverflow, panelW: el.clientWidth, panelScrollW: el.scrollWidth }
  })

  // details 折叠区：默认收起，点开后内容可见
  const det = panel.locator('.web-search-summary__rejected')
  const closedVisible = await det.locator('ul').isVisible()
  await det.locator('summary').click()
  const openVisible = await det.locator('ul').isVisible()
  const detOverflow = await det.evaluate(el => el.scrollWidth > el.clientWidth + 1)

  // 剔除按钮真实点击
  const btn = panel.locator('[data-testid="web-source-toggle-src_mit"]')
  const beforeText = (await btn.textContent()).trim()
  await btn.click()
  const afterText = (await btn.textContent()).trim()
  const pending = await panel.locator('.web-search-summary__pending').textContent()
  const li0 = await panel.locator('.web-search-summary__sources li').first().getAttribute('data-excluded')
  const li1 = await panel.locator('.web-search-summary__sources li').nth(1).getAttribute('data-excluded')

  const text = await panel.textContent()
  const cjk = /[一-鿿]/
  // 英文界面：界面自身文案不应有中文（来源标题来自网页，允许中文）
  const uiChinese = lang === 'en'
    ? [await panel.locator('.web-search-summary__hint').textContent(),
       await panel.locator('.web-search-summary__pending').textContent(),
       beforeText, afterText].filter(t => cjk.test(t || ''))
    : []

  await panel.locator('.web-search-summary__rejected').scrollIntoViewIfNeeded()
  await page.screenshot({ path: `/tmp/shots/${label}.png`, fullPage: false })
  findings.push({ label, overflow, closedVisible, openVisible, detOverflow,
                  beforeText, afterText, pending: (pending||'').trim(), li0, li1,
                  uiChinese, rawKeys: (text||'').includes('courseGeneration.'), errors })
  await page.close()
}

await browser.close(); await server.close()
console.log(JSON.stringify(findings, null, 2))
