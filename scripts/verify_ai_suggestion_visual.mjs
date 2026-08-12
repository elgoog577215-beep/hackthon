/**
 * Real-browser check for the proactive AI-teacher suggestion card and the
 * course impact preview.
 *
 * Covers the four combinations the owner asked for — zh/en × desktop/mobile —
 * with the narrow viewport treated as the important one, since that is where a
 * banner most easily overflows or covers the content it is talking about.
 *
 * Renders the real component against the real locale files through Vite, so the
 * CSS, fonts and layout are the shipped ones rather than jsdom approximations.
 *
 * Usage: node scripts/verify_ai_suggestion_visual.mjs [outputDir]
 *
 * Run from anywhere; pass an absolute path to the script.
 */
import { mkdir, writeFile, rm } from 'node:fs/promises'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const here = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(here, '..', 'frontend')
const require = createRequire(path.join(root, 'package.json'))

// Vite comes from the frontend's own dependencies so the probe compiles the
// component exactly the way the app does. Playwright is a verification-only
// tool and is not a project dependency, so it is resolved from wherever it
// happens to be installed; set PLAYWRIGHT_MODULE to override.
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
      // Resolve to a real file path so the later require() cannot be
      // reinterpreted relative to a different base directory.
      return require.resolve(candidate)
    } catch {
      // try the next one
    }
  }
  throw new Error(
    'playwright not found. Install it, or set PLAYWRIGHT_MODULE to its path.',
  )
}

const outputDir = process.argv[2] || path.resolve(root, '..')

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
]
const LOCALES = ['zh', 'en']
const ACTIONS = ['resume_diagnostic', 'start_due_review', 'resolve_blocking_issue']

const harness = `
<!doctype html>
<html><head><meta charset="utf-8" />
<style>
  body { margin:0; font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         background:#f8fafc; --lz-brand:#6366f1; --lz-brand-strong:#4f46e5;
         --lz-text:#1e293b; --lz-text-strong:#0f172a; --lz-text-secondary:#475569;
         --lz-text-muted:#94a3b8; --lz-surface-soft:#f1f5f9; }
  #app { padding:16px; }
  .probe-frame { max-width:760px; margin:0 auto; }
  .probe-body { margin-top:10px; padding:14px; border-radius:10px; background:#fff;
                box-shadow:0 1px 2px rgba(15,23,42,.06); color:#334155; font-size:13px; line-height:1.8; }
</style>
</head><body><div id="app"></div>
<script type="module">
  import { createApp, h, ref } from 'vue'
  import Suggestion from '/src/components/AITeacherSuggestion.vue'
  import ImpactPreview from '/src/components/CourseImpactPreview.vue'
  import { setLocale } from '/src/shared/i18n'

  const params = new URLSearchParams(location.search)
  await setLocale(params.get('locale') || 'zh')

  const suggestion = {
    trigger_id: 'ait-visual', trigger_type: 'runtime_support',
    moment: 'section_completed', node_id: 'node-1', scope_ref: { node_id: 'node-1' },
    severity: params.get('severity') || 'high', eligible_action: 'explain_runtime_action',
    runtime_action: { action_type: params.get('action') || 'resume_diagnostic' },
    dedupe_key: 'dk-visual', runtime_revision_id: 'runtime-1',
  }

  createApp({
    setup() {
      const current = ref(suggestion)
      const sections = [
        { node_id: 's1', node_name: '1.2 矩阵：线性映射与矩阵运算' },
        { node_id: 's2', node_name: '1.3 复合变换的几何意义' },
        { node_id: 's3', node_name: '1.4 逆变换与可逆条件' },
      ]
      return () => h('div', { class: 'probe-frame' }, [
        h(Suggestion, {
          suggestion: current.value,
          onAccept: () => {},
          onDecline: () => {},
          onShown: () => {},
        }),
        h(ImpactPreview, {
          affectedSectionIds: ['s1', 's2', 's3'],
          sections,
        }),
        h('div', { class: 'probe-body' },
          '正文占位：这段文字用来确认建议卡不会遮挡正在阅读的内容，' +
          'and to confirm the card does not overflow its container at any width.'),
      ])
    },
  }).mount('#app')
  document.documentElement.dataset.ready = '1'
</script></body></html>
`

async function main() {
  // Only ensure the directory exists. Never wipe it — the default output is the
  // repository root, which holds every other design-qa artefact.
  await mkdir(outputDir, { recursive: true })
  await writeFile(path.join(root, 'ai-suggestion-probe.html'), harness, 'utf-8')

  const server = await createServer({
    root,
    configFile: path.join(root, 'vite.config.ts'),
    server: { port: 5199, strictPort: true },
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
        for (const action of ACTIONS) {
          const url = `http://127.0.0.1:5199/ai-suggestion-probe.html`
            + `?locale=${locale}&action=${action}`
          await page.goto(url, { waitUntil: 'networkidle' })
          await page.waitForSelector('[data-testid="ai-suggestion-card"]', { timeout: 15_000 })

          const card = page.locator('[data-testid="ai-suggestion-card"]')
          const metrics = await card.evaluate((element) => {
            const rect = element.getBoundingClientRect()
            const buttons = [...element.querySelectorAll('button')].map((button) => {
              const box = button.getBoundingClientRect()
              return { label: button.textContent.trim(), width: box.width, height: box.height,
                       right: box.right, left: box.left }
            })
            return {
              width: rect.width, height: rect.height, left: rect.left, right: rect.right,
              scrollWidth: element.scrollWidth, clientWidth: element.clientWidth,
              text: element.innerText, buttons,
            }
          })

          const tag = `${locale}-${viewport.name}-${action}`
          if (action === ACTIONS[0]) {
            await page.screenshot({
              path: path.join(outputDir, `design-qa-ai-suggestion-${locale}-${viewport.name}.png`),
              fullPage: false,
            })
          }

          // 1. No horizontal overflow — the spec's explicit 390px requirement.
          if (metrics.scrollWidth > metrics.clientWidth + 1) {
            failures.push(`${tag}: card overflows horizontally `
              + `(scrollWidth=${metrics.scrollWidth} > clientWidth=${metrics.clientWidth})`)
          }
          // 2. Nothing escapes the viewport.
          if (metrics.left < -1 || metrics.right > viewport.width + 1) {
            failures.push(`${tag}: card escapes viewport (left=${metrics.left}, right=${metrics.right})`)
          }
          // 3. Every control stays inside the card and is tappable.
          for (const button of metrics.buttons) {
            if (button.right > metrics.right + 1) {
              failures.push(`${tag}: button "${button.label}" overflows the card`)
            }
            if (button.height < 20) {
              failures.push(`${tag}: button "${button.label}" is only ${button.height}px tall`)
            }
          }
          // 4. Language purity — an English UI must not leak Chinese copy.
          const hasChinese = /[一-鿿]/.test(metrics.text)
          if (locale === 'en' && hasChinese) {
            failures.push(`${tag}: Chinese text leaked into the English UI: ${metrics.text.slice(0, 80)}`)
          }
          if (locale === 'zh' && !hasChinese) {
            failures.push(`${tag}: Chinese UI rendered no Chinese text`)
          }
          // 5. No raw i18n keys or action codes on screen.
          if (metrics.text.includes('courseWorkspace.') || metrics.text.includes(action)) {
            failures.push(`${tag}: raw key or action code visible: ${metrics.text.slice(0, 80)}`)
          }

          // The impact preview shares the same surface and the same narrow
          // viewport, and its number is what a learner judges scope by — so it
          // gets the same overflow and language checks.
          const preview = await page.locator('[data-testid="course-impact-preview"]').evaluate(
            (element) => {
              const rect = element.getBoundingClientRect()
              return {
                left: rect.left, right: rect.right,
                scrollWidth: element.scrollWidth, clientWidth: element.clientWidth,
                text: element.innerText,
                rows: element.querySelectorAll('[data-testid="impact-section"]').length,
              }
            },
          )
          if (preview.scrollWidth > preview.clientWidth + 1) {
            failures.push(`${tag}: impact preview overflows horizontally`)
          }
          if (preview.left < -1 || preview.right > viewport.width + 1) {
            failures.push(`${tag}: impact preview escapes viewport`)
          }
          // The probe feeds it three sections; the rendered count and the
          // stated number must both be 3, in both languages.
          if (preview.rows !== 3) {
            failures.push(`${tag}: impact preview listed ${preview.rows} sections, expected 3`)
          }
          const expectedCount = locale === 'en' ? 'Affects 3 sections' : '将影响 3 个小节'
          if (!preview.text.includes(expectedCount)) {
            failures.push(`${tag}: impact preview missing "${expectedCount}": ${preview.text.slice(0, 80)}`)
          }
          // Section names are course content, not UI chrome — a Chinese course
          // keeps Chinese titles in an English UI. So the language check applies
          // to the preview's own strings only.
          const previewChrome = preview.text
            .split('\n')
            .filter(line => !/^[\u2022\s]*\d+\.\d+\s/.test(line))
            .join('\n')
          if (locale === 'en' && /[一-鿿]/.test(previewChrome)) {
            failures.push(`${tag}: Chinese leaked into English impact-preview chrome: `
              + previewChrome.slice(0, 80))
          }

          notes.push(`${tag}: ${Math.round(metrics.width)}x${Math.round(metrics.height)}px, `
            + `${metrics.buttons.length} controls`)
        }
        await context.close()
      }
    }
  } finally {
    await browser.close()
    await server.close()
    await rm(path.join(root, 'ai-suggestion-probe.html'), { force: true })
  }

  console.log(notes.join('\n'))
  console.log(`\nScreenshots: ${outputDir}`)
  if (failures.length) {
    console.error(`\nFAILED (${failures.length}):`)
    for (const failure of failures) console.error(`  - ${failure}`)
    process.exit(1)
  }
  console.log('\nPASS: 4 combinations (zh/en x desktop/mobile), 3 action variants each.')
}

await main()
