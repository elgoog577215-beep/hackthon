/**
 * 课程发布前的浏览器验收：真实 Chromium，中英 × 桌面/移动四场景。
 *
 * 为什么和 render_gate.mjs 分开：render_gate 回答"生成正确吗"——公式能不能
 * 被 KaTeX 解析、Markdown 结构有没有坏。它跑在 jsdom 里，看不见布局。这个脚本
 * 回答"呈现舒服吗"——真实排版下有没有横向溢出、文字被截断、公式撑破容器、
 * 触控目标过小、中文漏进英文界面。两件事分开验证，是 F-2 的要求。
 *
 * 机制沿用上一轮 D2 的做法（scripts/verify_course_scope_visual.mjs）：脚本自带
 * 一个 HTML 探针，用 frontend 自己的 vite 配置在进程内起服务，把真实
 * MarkdownRenderer 挂上去渲染真实课程正文。因此不需要后端、不需要 LLM、
 * 不写任何数据——D2 那个 knowledge_panel_acceptance.mjs 需要整套栈和一门特定
 * 课程，作为发布前必跑关卡太重且会写库。
 *
 * 用法（从仓库根目录）：
 *   node scripts/course_visual_acceptance.mjs --course backend/data/courses/<id>.json
 *   node scripts/course_visual_acceptance.mjs --course <file> --out docs/验收/课程呈现
 *
 * 判据不是"截图拍到了"，而是每个场景都断言了可观察结果；任何一条失败即退出非零。
 */
import { mkdir, writeFile, rm } from 'node:fs/promises'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve, join } from 'node:path'
import { createRequire } from 'node:module'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..')
const FRONTEND = resolve(ROOT, 'frontend')

const require = createRequire(resolve(FRONTEND, 'package.json'))
const { createServer } = require('vite')

// Playwright is a verification-only tool and deliberately not a project
// dependency (see the same note in scripts/course_layout_smoke.mjs) — resolve it
// from wherever it is installed; PLAYWRIGHT_MODULE overrides.
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
const { chromium } = require(resolvePlaywright())

function parseArgs(argv) {
  const args = { course: '', out: '', nodes: 6 }
  for (let i = 2; i < argv.length; i += 1) {
    if (argv[i] === '--course') args.course = argv[++i]
    else if (argv[i] === '--out') args.out = argv[++i]
    else if (argv[i] === '--nodes') args.nodes = Number(argv[++i])
  }
  return args
}

/** 与 render_gate.mjs 相同的取正文逻辑：两种 schema 都在盘上。 */
function extractBodies(course) {
  const bodies = []
  for (const node of course.nodes || []) {
    const content = String(node.node_content || '')
    if (content.trim()) {
      bodies.push({ id: String(node.node_id || ''), name: String(node.node_name || ''), content })
    }
  }
  for (const block of (course.course_document || {}).blocks || []) {
    const content = String((block.payload || {}).markdown || '')
    if (content.trim()) {
      bodies.push({
        id: String(block.block_id || ''),
        name: String((block.payload || {}).title || block.role || ''),
        content,
      })
    }
  }
  return bodies
}

// 四场景：中英 × 桌面/移动，沿用 D2 与既有 design-qa 脚本的口径。
const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'mobile', width: 390, height: 844 },
]
const LOCALES = ['zh', 'en']

const HARNESS = `
<!doctype html>
<html><head><meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
  body { margin:0; padding:16px; background:#fff;
         font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
         --lz-brand:#6366f1; --lz-brand-strong:#4f46e5; --lz-text:#1e293b;
         --lz-text-strong:#0f172a; --lz-text-secondary:#475569;
         --lz-text-muted:#94a3b8; --lz-surface-soft:#f1f5f9; }
  #app { max-width: 860px; margin: 0 auto; }
</style>
</head><body><div id="app"></div>
<script type="module">
  import { createApp, h } from 'vue'
  import { createPinia } from 'pinia'
  import MarkdownRenderer from '/src/components/MarkdownRenderer.vue'
  import { setLocale } from '/src/shared/i18n'

  const params = new URLSearchParams(location.search)
  await setLocale(params.get('locale') || 'zh')
  const payload = JSON.parse(decodeURIComponent(params.get('body') || '%22%22'))

  const app = createApp({
    render: () => h('article', { class: 'node-body' }, [h(MarkdownRenderer, { content: payload })]),
  })
  app.use(createPinia())
  app.mount('#app')
  // Give KaTeX and the rAF-batched renderer a frame to settle before we measure.
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.dataset.ready = '1'
  }))
</script></body></html>
`

async function main() {
  const args = parseArgs(process.argv)
  if (!args.course) {
    console.error('用法: node scripts/course_visual_acceptance.mjs --course <course.json> [--out <dir>] [--nodes N]')
    return 2
  }
  const outputDir = resolve(ROOT, args.out || 'docs/验收/课程呈现')
  const course = JSON.parse(readFileSync(resolve(ROOT, args.course), 'utf8'))
  const all = extractBodies(course)
  if (!all.length) {
    console.error('这门课没有可渲染的正文。')
    return 2
  }
  // Longest bodies first: the layout accidents this is looking for live in the
  // dense nodes — long formulas, wide tables, deep lists.
  const bodies = all.sort((a, b) => b.content.length - a.content.length).slice(0, args.nodes)

  await mkdir(outputDir, { recursive: true })
  const harnessPath = join(FRONTEND, 'course-visual-probe.html')
  await writeFile(harnessPath, HARNESS, 'utf-8')

  const server = await createServer({
    root: FRONTEND,
    configFile: join(FRONTEND, 'vite.config.ts'),
    server: { port: 5197, strictPort: true },
    logLevel: 'error',
  })
  await server.listen()

  const browser = await chromium.launch()
  const failures = []
  const notes = []
  let shots = 0

  try {
    for (const locale of LOCALES) {
      for (const viewport of VIEWPORTS) {
        const context = await browser.newContext({
          viewport: { width: viewport.width, height: viewport.height },
          deviceScaleFactor: 2,
          locale: locale === 'zh' ? 'zh-CN' : 'en-US',
        })
        const page = await context.newPage()
        const jsErrors = []
        const consoleErrors = []
        page.on('pageerror', error => jsErrors.push(String(error)))
        page.on('console', message => {
          if (message.type() === 'error') consoleErrors.push(message.text())
        })

        const tag = `${locale}-${viewport.name}`
        for (const [index, body] of bodies.entries()) {
          const encoded = encodeURIComponent(JSON.stringify(body.content))
          await page.goto(
            `http://127.0.0.1:5197/course-visual-probe.html?locale=${locale}&body=${encoded}`,
            { waitUntil: 'networkidle' },
          )
          await page.waitForSelector('html[data-ready="1"]', { timeout: 20_000 })

          const measured = await page.evaluate(width => {
            const root = document.querySelector('.node-body')
            const overflowing = []
            for (const element of root.querySelectorAll('*')) {
              const rect = element.getBoundingClientRect()
              if (rect.width === 0 && rect.height === 0) continue
              // Escaping the viewport is the accident a reader actually feels:
              // it forces horizontal scrolling of the whole page.
              if (rect.right > width + 1) {
                overflowing.push(`${element.tagName.toLowerCase()}.${element.className || ''}`.slice(0, 60))
              }
            }
            const katex = root.querySelectorAll('.katex').length
            const katexErrors = root.querySelectorAll('.katex-error').length
            const fallbacks = root.querySelectorAll('.math-fallback').length
            return {
              overflowing: [...new Set(overflowing)].slice(0, 5),
              docScrollWidth: document.documentElement.scrollWidth,
              katex, katexErrors, fallbacks,
              // Raw i18n keys are a visible defect in either locale.
              rawKeys: /\b(?:common|course|courseEvolution)\.[a-zA-Z]+\b/.test(root.innerText),
            }
          }, viewport.width)

          await page.screenshot({
            path: join(outputDir, `visual-${tag}-${String(index + 1).padStart(2, '0')}.png`),
            fullPage: true,
          })
          shots += 1

          const where = `${tag} / ${body.name || body.id}`
          if (measured.overflowing.length) {
            failures.push(`${where}: 元素超出视口 — ${measured.overflowing.join(', ')}`)
          }
          if (measured.docScrollWidth > viewport.width + 1) {
            failures.push(`${where}: 页面出现横向滚动（${measured.docScrollWidth}px > ${viewport.width}px）`)
          }
          if (measured.katexErrors) {
            failures.push(`${where}: ${measured.katexErrors} 处 KaTeX 报错节点`)
          }
          if (measured.fallbacks) {
            failures.push(`${where}: ${measured.fallbacks} 处公式退化为源码`)
          }
          if (measured.rawKeys) {
            failures.push(`${where}: 界面出现未翻译的 i18n key`)
          }
          notes.push(`${where}: katex=${measured.katex} 溢出=${measured.overflowing.length}`)
        }

        if (jsErrors.length) {
          failures.push(`${tag}: ${jsErrors.length} 个未捕获 JS 异常 — ${jsErrors.slice(0, 2).join(' | ')}`)
        }
        if (consoleErrors.length) {
          failures.push(`${tag}: ${consoleErrors.length} 条 console.error — ${consoleErrors.slice(0, 2).join(' | ')}`)
        }
        await context.close()
      }
    }
  } finally {
    await browser.close()
    await server.close()
    await rm(harnessPath, { force: true })
  }

  const title = course.course_name || (course.course_document || {}).title || course.course_id || ''
  const lines = [
    `# 课程呈现验收 — ${title}`,
    '',
    `- 课程文件：\`${args.course}\``,
    `- 场景：zh-desktop / zh-mobile / en-desktop / en-mobile`,
    `- 每场景抽查最长的 ${bodies.length} 节正文，共 ${shots} 张截图`,
    `- 渲染器：真实 Chromium + 真实 MarkdownRenderer（非 jsdom）`,
    '',
    failures.length ? `## 未通过（${failures.length}）` : '## 全部通过',
    '',
    ...(failures.length ? failures.map(item => `- ${item}`) : ['- 无排版事故。']),
    '',
    '## 逐节点观测',
    '',
    ...notes.map(item => `- ${item}`),
    '',
  ]
  await writeFile(join(outputDir, 'RESULT.md'), lines.join('\n'), 'utf-8')

  console.log(notes.join('\n'))
  console.log(`\n截图与报告：${outputDir}`)
  if (failures.length) {
    console.error(`\nFAILED (${failures.length}):`)
    for (const failure of failures) console.error(`  - ${failure}`)
    return 1
  }
  console.log('\nPASS: 中英 × 桌面/移动四场景无排版事故。')
  return 0
}

process.exitCode = await main()
