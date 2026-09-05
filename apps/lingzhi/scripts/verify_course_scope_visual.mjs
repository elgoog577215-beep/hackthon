/**
 * Real-browser check for the course-change scope selector.
 *
 * The chapter option is the widest scope a learner can pick, and its hint
 * carries the "nothing changes until you confirm" promise — so it must be
 * readable, not silently truncated. The existing style uses `white-space:
 * nowrap` with an ellipsis, which is exactly the setup that hides longer copy,
 * and English copy is longer than Chinese.
 *
 * Usage: node scripts/verify_course_scope_visual.mjs
 */
import { mkdir, writeFile, rm } from 'node:fs/promises'
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
      // try the next one
    }
  }
  throw new Error('playwright not found. Set PLAYWRIGHT_MODULE to its path.')
}

const outputDir = process.argv[2] || path.resolve(root, '..')
const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
]
const LOCALES = ['zh', 'en']

const harness = `
<!doctype html>
<html><head><meta charset="utf-8" />
<style>
  body { margin:0; padding:16px; font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         background:#f8fafc; --lz-brand:#6366f1; --lz-brand-strong:#4f46e5;
         --lz-text:#1e293b; --lz-text-strong:#0f172a; --lz-text-secondary:#475569;
         --lz-text-muted:#94a3b8; --lz-surface-soft:#f1f5f9; }
  #app { max-width:420px; margin:0 auto; }
</style>
</head><body><div id="app"></div>
<script type="module">
  import { createApp, h } from 'vue'
  import { createPinia } from 'pinia'
  import Panel from '/src/components/CourseEvolutionPanel.vue'
  import { setLocale } from '/src/shared/i18n'

  const params = new URLSearchParams(location.search)
  await setLocale(params.get('locale') || 'zh')

  const app = createApp({
    render: () => h(Panel, { courseId: 'course-visual', sectionId: 'section-1' }),
  })
  app.use(createPinia())
  app.mount('#app')
  document.documentElement.dataset.ready = '1'
</script></body></html>
`

async function main() {
  await mkdir(outputDir, { recursive: true })
  await writeFile(path.join(root, 'course-scope-probe.html'), harness, 'utf-8')

  const server = await createServer({
    root,
    configFile: path.join(root, 'vite.config.ts'),
    server: { port: 5198, strictPort: true },
    logLevel: 'error',
  })
  await server.listen()

  const browser = await chromium.launch()
  const failures = []
  const notes = []

  try {
    for (const locale of LOCALES) {
      for (const viewport of VIEWPORTS) {
        const context = await browser.newContext({
          viewport: { width: viewport.width, height: viewport.height },
          deviceScaleFactor: 2,
        })
        const page = await context.newPage()
        await page.goto(
          `http://127.0.0.1:5198/course-scope-probe.html?locale=${locale}`,
          { waitUntil: 'networkidle' },
        )
        await page.waitForSelector('.request-scope-control', { timeout: 15_000 })

        const tag = `${locale}-${viewport.name}`
        const scopes = await page.locator('.request-scope-control button').evaluateAll(
          buttons => buttons.map(button => {
            const rect = button.getBoundingClientRect()
            const hint = button.querySelector('small')
            const hintRect = hint?.getBoundingClientRect()
            return {
              scope: button.dataset.scope,
              text: button.innerText,
              width: rect.width, right: rect.right,
              scrollWidth: button.scrollWidth, clientWidth: button.clientWidth,
              hintText: hint?.textContent?.trim() || '',
              // A nowrap+ellipsis hint that overflows is silently truncated.
              hintTruncated: hint ? hint.scrollWidth > hint.clientWidth + 1 : false,
              hintHeight: hintRect?.height || 0,
            }
          }),
        )

        await page.screenshot({
          path: path.join(outputDir, `design-qa-course-scope-${locale}-${viewport.name}.png`),
          clip: await page.locator('.section-growth-request').boundingBox(),
        })

        const offered = scopes.map(item => item.scope)
        // Owner decision Q6: chapter is the cap; no whole-course entry.
        if (!offered.includes('current_section') || !offered.includes('current_chapter')) {
          failures.push(`${tag}: expected section + chapter scopes, got ${offered.join(', ')}`)
        }
        if (offered.includes('whole_course')) {
          failures.push(`${tag}: whole-course entry is still offered to students`)
        }
        for (const item of scopes) {
          if (item.scrollWidth > item.clientWidth + 1) {
            failures.push(`${tag}: scope "${item.scope}" overflows its button`)
          }
          if (item.right > viewport.width + 1) {
            failures.push(`${tag}: scope "${item.scope}" escapes the viewport`)
          }
          if (item.hintTruncated) {
            failures.push(
              `${tag}: scope "${item.scope}" hint is cut off: "${item.hintText}"`,
            )
          }
          if (locale === 'en' && /[一-鿿]/.test(item.text)) {
            failures.push(`${tag}: Chinese leaked into the English scope selector`)
          }
          if (item.text.includes('courseEvolution.')) {
            failures.push(`${tag}: raw i18n key visible in scope selector`)
          }
        }
        notes.push(`${tag}: ${offered.join(' | ')}`)
        await context.close()
      }
    }
  } finally {
    await browser.close()
    await server.close()
    await rm(path.join(root, 'course-scope-probe.html'), { force: true })
  }

  console.log(notes.join('\n'))
  console.log(`\nScreenshots: ${outputDir}`)
  if (failures.length) {
    console.error(`\nFAILED (${failures.length}):`)
    for (const failure of failures) console.error(`  - ${failure}`)
    process.exit(1)
  }
  console.log('\nPASS: scope selector across zh/en x desktop/mobile.')
}

await main()
