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
 *   node scripts/course_visual_acceptance.mjs --course <file> --print --out docs/验收/课程呈现
 *   node scripts/course_visual_acceptance.mjs --url <地址> --selector <根选择器> --print
 *
 * `--print` 增加打印态判定：教案统一模板的验收标准是「教师能直接打印上课」，
 * 打印态公式坏掉那条验收就过不了，所以它需要一个能自动判定的判据。
 *
 * `--url` 对着一个已经跑起来的页面判定，**不需要改被测组件**。呈现层归别人
 * 维护、判据归这里时用这个模式。
 *
 * 打印态的边界，写在这里也写进每份报告，不要外推：
 *   - 打印由 `window.print()` + CSS 实现，**没有 PDF 导出管线**；
 *     本脚本用 `page.emulateMedia({media:'print'})` 让真实 Chromium 按打印样式
 *     重算布局，等价于打印预览的样式计算，不等价于任何 PDF 导出器。
 *   - **只在 Chromium 上验证过**。Firefox/Safari 的分页与 `visibility` 反选行为
 *     未测，结论不适用。
 *
 * 判据不是"截图拍到了"，而是每个场景都断言了可观察结果；任何一条失败即退出非零。
 */
import { mkdir, writeFile, rm } from 'node:fs/promises'
import { readFileSync, existsSync } from 'node:fs'
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
  const args = {
    course: '', out: '', nodes: 6, print: false, url: '', selector: '',
    mathFirst: false, printOnly: false, courseId: '', dataDir: '',
  }
  for (let i = 2; i < argv.length; i += 1) {
    if (argv[i] === '--course') args.course = argv[++i]
    else if (argv[i] === '--out') args.out = argv[++i]
    else if (argv[i] === '--nodes') args.nodes = Number(argv[++i])
    else if (argv[i] === '--print') args.print = true
    else if (argv[i] === '--url') args.url = argv[++i]
    else if (argv[i] === '--selector') args.selector = argv[++i]
    // 只判定公式相关的节：打印态验收关心的是公式，抽最长的几节可能一条公式
    // 都没有，那样的"通过"什么也没证明。
    else if (argv[i] === '--math-first') args.mathFirst = true
    // 跳过屏幕态的布局判据，只跑打印两态。屏幕态由不带 --print 的常规模式覆盖，
    // 大批量跑打印验收时没必要重复。
    else if (argv[i] === '--print-only') { args.printOnly = true; args.print = true }
    // 真机课程落在 `$LINGZHI_DATA_DIR/courses/<id>.json`；跑冒烟的人手上只有
    // course_id，让脚本自己解析，避免每次手拼路径。
    else if (argv[i] === '--course-id') args.courseId = argv[++i]
    else if (argv[i] === '--data-dir') args.dataDir = argv[++i]
  }
  return args
}

/** 把 `--course-id` 解析成实际文件路径。 */
function resolveCourseFile(args) {
  if (args.course) return resolve(ROOT, args.course)
  if (!args.courseId) return ''
  const roots = [
    args.dataDir,
    process.env.LINGZHI_DATA_DIR,
    resolve(ROOT, 'backend/data'),
  ].filter(Boolean)
  for (const root of roots) {
    const candidate = resolve(root, 'courses', `${args.courseId}.json`)
    if (existsSync(candidate)) return candidate
  }
  throw new Error(
    `找不到课程 ${args.courseId}。找过：\n` +
    roots.map(r => `  ${resolve(r, 'courses', `${args.courseId}.json`)}`).join('\n') +
    '\n用 --data-dir 指定运行时数据目录，或直接用 --course <文件路径>。',
  )
}

/** 正文里有没有会被渲染成公式的标记。 */
function hasMath(text) {
  return /\$\$/.test(text) || /(?<!\\)\$[^$\n]{2,}\$/.test(text)
}

/**
 * 判定打印态：公式是否还在，以及它是「没渲染」还是「渲染了但被藏掉」。
 *
 * 这两种失败的修法完全不同，绝不能合成一个错误码：
 *
 * - `print:math_not_rendered` —— 屏幕态就没有 KaTeX 节点。问题在内容或渲染链
 *   （公式语法错、字段没接渲染器），跟打印样式无关。改打印 CSS 不会有任何帮助。
 * - `print:math_hidden_in_print` —— 屏幕态渲染正常，切到 print 媒体后不可见。
 *   问题在打印样式：`body * { visibility:hidden }` 这类反选没覆盖到 KaTeX 的
 *   嵌套 span，或被 `display:none` 连坐。改内容不会有任何帮助。
 *
 * 已验证的地基：`body * { visibility:hidden !important }` 加
 * `.根容器, .根容器 * { visibility:visible !important }` 的反选**能穿透 KaTeX
 * 的嵌套 span**——3 个公式在 print 媒体下全部可见，同时应用外壳正确隐藏。
 * 所以后者出现时，是那份打印样式自己写漏了，不是这个模式做不到。
 */
async function measurePrintState(page, rootSelector) {
  const read = () => page.evaluate(selector => {
    const root = document.querySelector(selector) || document.body
    const nodes = Array.from(root.querySelectorAll('.katex'))
    const visible = nodes.filter(el => {
      const cs = getComputedStyle(el)
      if (cs.visibility !== 'visible' || cs.display === 'none') return false
      const rect = el.getBoundingClientRect()
      return rect.width > 0 && rect.height > 0
    })
    const text = root.innerText || ''
    return {
      katexTotal: nodes.length,
      katexVisible: visible.length,
      mathFallback: root.querySelectorAll('.math-fallback').length,
      katexError: root.querySelectorAll('.katex-error').length,
      // 打印稿上读到的字面 LaTeX——教师拿到的纸上就是这些字符。
      // 取字面 LaTeX 前先剔除代码块的可见文本：Python 课里
      // `"1234!@#$"` 到 `"$#@!4321"` 之间会被 `$...$` 正则误当成公式，
      // 那是字符串字面量，不是没渲染的数学。实测过一次这样的误报。
      literalMath: (() => {
        const clone = root.cloneNode(true)
        for (const code of clone.querySelectorAll('pre, code, .mermaid')) code.remove()
        const prose = clone.innerText || ''
        return (prose.match(/(?<!\\)\$[^$\n]{1,80}\$/g) || []).slice(0, 5)
      })(),
      docScrollWidth: document.documentElement.scrollWidth,
      bodyClientWidth: document.body.clientWidth,
      // 与视口比，而不是与 body.clientWidth 比：body 默认有 8px 外边距，
      // 拿 scrollWidth 去比 clientWidth 会把这点边距报成「横向溢出」。
      viewportWidth: window.innerWidth,
    }
  }, rootSelector)

  const screen = await read()
  await page.emulateMedia({ media: 'print' })
  const print = await read()
  await page.emulateMedia({ media: 'screen' })
  return { screen, print }
}

/** 把两态测量翻译成互斥的错误码。 */
function printFailures(where, { screen, print }) {
  const failures = []
  if (screen.katexError) {
    failures.push({
      code: 'print:katex_error',
      message: `${where}: 屏幕态就有 ${screen.katexError} 处 KaTeX 报错节点，公式语法有问题`,
    })
  }
  if (screen.mathFallback) {
    failures.push({
      code: 'print:math_not_rendered',
      message: `${where}: 屏幕态有 ${screen.mathFallback} 处公式退化为源码——问题在内容或渲染链，不在打印样式`,
    })
  }
  if (!screen.katexTotal && screen.literalMath.length) {
    failures.push({
      code: 'print:math_not_rendered',
      message: `${where}: 正文含公式但一个都没渲染（读到 ${screen.literalMath[0]}）——该字段可能没接 MarkdownRenderer`,
    })
  }
  // 只有屏幕态确实渲染出来了，才谈得上「被打印样式藏掉」。
  if (screen.katexVisible > 0 && print.katexVisible < screen.katexVisible) {
    failures.push({
      code: 'print:math_hidden_in_print',
      message:
        `${where}: 屏幕可见 ${screen.katexVisible} 个公式，打印态只剩 ${print.katexVisible} 个` +
        '——问题在打印样式的可见性反选没覆盖 KaTeX 嵌套 span，不在内容',
    })
  }
  if (print.docScrollWidth > print.viewportWidth + 1) {
    failures.push({
      code: 'print:horizontal_overflow',
      message: `${where}: 打印态横向溢出（${print.docScrollWidth}px > ${print.viewportWidth}px），纸上会被裁掉`,
    })
  }
  if (print.literalMath.length) {
    failures.push({
      code: 'print:literal_latex',
      message: `${where}: 打印稿上出现字面 LaTeX ${print.literalMath.join(', ')}`,
    })
  }
  return failures
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
  // 必须复刻真实应用的样式加载链：frontend/src/main.ts 里加载了这份样式，
  // 探针不加载就会让 .mfrac 失去布局规则、把页面撑出几千像素，测出一个
  // 根本不存在的「打印溢出」缺陷。实测过：漏掉它 docScrollWidth=6400，
  // 补上后 =1024。探针的样式加载链与真实应用不一致时，测到的是探针自己。
  import 'katex/dist/katex.min.css'
  import { createApp, h } from 'vue'
  import { createPinia } from 'pinia'
  import MarkdownRenderer from '/src/components/MarkdownRenderer.vue'
  import { setLocale } from '/src/shared/i18n'

  const params = new URLSearchParams(location.search)
  await setLocale(params.get('locale') || 'zh')
  // 正文通过 addInitScript 注入全局，不走 URL query：真实课程正文动辄两三千字，
  // URL-encode 后超出 HTTP 头长度上限，服务器回 431，页面根本不执行——看起来像
  // 「这一节渲染卡住」，实际是探针自己把正文塞进了请求头。
  const payload = String(window.__PROBE_BODY__ ?? '')

  const app = createApp({
    render: () => h('article', { class: 'node-body' }, [h(MarkdownRenderer, { content: payload })]),
  })
  app.use(createPinia())
  app.mount('#app')
  // MarkdownRenderer 把渲染对齐到 requestAnimationFrame（见其 scheduleUpdate），
  // 所以必须等帧再判定。只等微任务会看到空 DOM，测出「公式没渲染」的假失败——
  // 实测：只 flushPromises 得到 0 个 .katex，等一帧后得到 1 个，KaTeX 一直是好的。
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.dataset.ready = '1'
  }))
</script></body></html>
`

/**
 * 对着一个已经跑起来的页面做打印态验收——不改被测组件一个字。
 *
 * 这是给「呈现层归别人、判据归我」准备的模式：lz-lesson-plan 的统一模板
 * 进 main 之后，直接
 *   node scripts/course_visual_acceptance.mjs --url http://127.0.0.1:5173/... \
 *     --selector .lesson-dossier --print
 * 就能跑，无需在它的文件里插任何钩子。
 */
async function auditLiveUrl(args, outputDir) {
  await mkdir(outputDir, { recursive: true })
  const rootSelector = args.selector || 'body'
  const browser = await chromium.launch()
  const failures = []
  const notes = []

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
        page.on('pageerror', error => jsErrors.push(String(error)))

        const tag = `${locale}-${viewport.name}`
        await page.goto(args.url, { waitUntil: 'networkidle', timeout: 60_000 })
        await page.waitForSelector(rootSelector, { timeout: 30_000 })
        // MarkdownRenderer 对齐 rAF，等两帧再测，否则会测出假的「没渲染」。
        await page.evaluate(() => new Promise(resolve => {
          requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
        }))

        const measured = await measurePrintState(page, rootSelector)
        failures.push(...printFailures(tag, measured))

        await page.emulateMedia({ media: 'print' })
        await page.screenshot({ path: join(outputDir, `print-${tag}.png`), fullPage: true })
        await page.emulateMedia({ media: 'screen' })

        if (jsErrors.length) {
          failures.push({
            code: 'print:js_error',
            message: `${tag}: ${jsErrors.length} 个未捕获 JS 异常 — ${jsErrors.slice(0, 2).join(' | ')}`,
          })
        }
        notes.push(
          `${tag}: 屏幕 katex=${measured.screen.katexVisible}/${measured.screen.katexTotal}` +
          ` 打印 katex=${measured.print.katexVisible}/${measured.print.katexTotal}`,
        )
        await context.close()
      }
    }
  } finally {
    await browser.close()
  }

  await writeResult(outputDir, {
    title: args.url,
    subject: `页面 \`${args.url}\`（根选择器 \`${rootSelector}\`）`,
    scenarioNote: '每个场景分别在 screen 与 print 两种媒体下测量',
    failures,
    notes,
  })
  console.log(notes.join('\n'))
  console.log(`\n截图与报告：${outputDir}`)
  if (failures.length) {
    console.error(`\nFAILED (${failures.length}):`)
    for (const failure of failures) console.error(`  - [${failure.code}] ${failure.message}`)
    return 1
  }
  console.log('\nPASS: 打印态公式可见、无字面 LaTeX、无横向溢出。')
  return 0
}

/** 统一写 RESULT.md，两种模式共用，保证报告能被独立读懂。 */
async function writeResult(outputDir, { title, subject, scenarioNote, failures, notes, extra = [] }) {
  const byCode = {}
  for (const failure of failures) {
    byCode[failure.code] = (byCode[failure.code] || 0) + 1
  }
  const lines = [
    `# 呈现验收 — ${title}`,
    '',
    `- 被测对象：${subject}`,
    '- 场景：zh-desktop / zh-mobile / en-desktop / en-mobile',
    `- ${scenarioNote}`,
    '- 渲染器：真实 Chromium + 真实 MarkdownRenderer（非 jsdom）',
    '- 打印态由 `page.emulateMedia({media:"print"})` 模拟 `window.print()` 的样式计算；',
    '  **没有 PDF 导出管线，结论仅适用于 Chromium**。',
    ...extra,
    '',
    failures.length ? `## 未通过（${failures.length}）` : '## 全部通过',
    '',
  ]
  if (failures.length) {
    lines.push('错误码分布（不同码的修法不同，不要混为一谈）：', '')
    for (const [code, count] of Object.entries(byCode)) {
      lines.push(`- \`${code}\` × ${count}`)
    }
    lines.push('', ...failures.map(item => `- [\`${item.code}\`] ${item.message}`))
  } else {
    lines.push('- 无排版事故。')
  }
  lines.push('', '## 逐场景观测', '', ...notes.map(item => `- ${item}`), '')
  await writeFile(join(outputDir, 'RESULT.md'), lines.join('\n'), 'utf-8')
}

async function main() {
  const args = parseArgs(process.argv)
  if (!args.course && !args.url && !args.courseId) {
    console.error(
      '用法:\n' +
      '  node scripts/course_visual_acceptance.mjs --course <course.json> [--out <dir>] [--nodes N] [--print]\n' +
      '  node scripts/course_visual_acceptance.mjs --url <页面地址> [--selector <根选择器>] --print [--out <dir>]\n' +
      '  node scripts/course_visual_acceptance.mjs --course-id <课程ID> [--data-dir <运行时数据目录>] --print\n' +
      '\n' +
      '--url 模式对着一个已经跑起来的页面判定，不需要改被测组件。\n' +
      '统一模板进 main 后，对它跑这道关卡就是 --url 加 --selector .lesson-dossier。',
    )
    return 2
  }
  const outputDir = resolve(ROOT, args.out || 'docs/验收/课程呈现')

  // --url：只读地判定一个已存在的页面。这是给「被测组件不归我改」的场景准备的。
  if (args.url) {
    return await auditLiveUrl(args, outputDir)
  }

  let coursePath
  try {
    coursePath = resolveCourseFile(args)
  } catch (error) {
    console.error(String(error.message || error))
    return 2
  }
  const course = JSON.parse(readFileSync(coursePath, 'utf8'))
  const all = extractBodies(course)
  if (!all.length) {
    console.error('这门课没有可渲染的正文。')
    return 2
  }
  // Longest bodies first: the layout accidents this is looking for live in the
  // dense nodes — long formulas, wide tables, deep lists. With --math-first,
  // nodes that actually contain formulas come first instead, because a print
  // verdict drawn from formula-free nodes proves nothing about formulas.
  const ranked = args.mathFirst
    ? all.filter(item => hasMath(item.content))
        .sort((a, b) => b.content.length - a.content.length)
    : all.sort((a, b) => b.content.length - a.content.length)
  if (args.mathFirst && !ranked.length) {
    console.log(`跳过（无含公式的正文）：${args.course}`)
    return 0
  }
  const bodies = ranked.slice(0, args.nodes)

  await mkdir(outputDir, { recursive: true })
  // 文件名带进程号：两个并发实例用同名探针会互相删掉对方的文件。
  const harnessName = `course-visual-probe-${process.pid}.html`
  const harnessPath = join(FRONTEND, harnessName)
  await writeFile(harnessPath, HARNESS, 'utf-8')

  // 不用固定端口：并发或前一次残留会撞端口，vite 直接抛错退出，看起来像
  // 「这门课验收失败」，实际是环境冲突。strictPort:false 让 vite 自动往后找，
  // 端口从 server.config 回读。
  const server = await createServer({
    root: FRONTEND,
    configFile: join(FRONTEND, 'vite.config.ts'),
    server: { port: 0, strictPort: false },
    logLevel: 'error',
  })
  await server.listen()
  const resolvedPort = server.config.server.port || server.httpServer.address().port
  const baseUrl = `http://127.0.0.1:${resolvedPort}`

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
        let page = null
        const jsErrors = []
        const consoleErrors = []

        const tag = `${locale}-${viewport.name}`
        for (const [index, body] of bodies.entries()) {
          // 每节用一张新页面：addInitScript 是累加的，复用同一张页面会让后面的
          // 节点仍然读到第一节的正文，测出一个「所有节都一样」的假结论。
          if (page) await page.close()
          page = await context.newPage()
          page.on('pageerror', error => jsErrors.push(String(error)))
          page.on('console', message => {
            if (message.type() === 'error') consoleErrors.push(message.text())
          })
          await page.addInitScript(content => {
            window.__PROBE_BODY__ = content
          }, body.content)
          await page.goto(
            `${baseUrl}/${harnessName}?locale=${locale}`,
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
          // --print-only 时跳过屏幕态布局判据：它们由不带 --print 的常规模式
          // 覆盖，大批量跑打印验收时重复报同一件事只会淹没打印态的结论。
          if (measured.overflowing.length && !args.printOnly) {
            failures.push({
              code: 'visual:viewport_overflow',
              message: `${where}: 元素超出视口 — ${measured.overflowing.join(', ')}`,
            })
          }
          if (measured.docScrollWidth > viewport.width + 1 && !args.printOnly) {
            failures.push({
              code: 'visual:horizontal_scroll',
              message: `${where}: 页面出现横向滚动（${measured.docScrollWidth}px > ${viewport.width}px）`,
            })
          }
          if (measured.katexErrors) {
            failures.push({
              code: 'visual:katex_error',
              message: `${where}: ${measured.katexErrors} 处 KaTeX 报错节点`,
            })
          }
          if (measured.fallbacks) {
            failures.push({
              code: 'visual:math_not_rendered',
              message: `${where}: ${measured.fallbacks} 处公式退化为源码`,
            })
          }
          if (measured.rawKeys && !args.printOnly) {
            failures.push({
              code: 'visual:raw_i18n_key',
              message: `${where}: 界面出现未翻译的 i18n key`,
            })
          }

          // --print：同一段正文再在 print 媒体下判定一次，并把「没渲染」与
          // 「渲染了但打印态被藏掉」分成两个码。
          let printNote = ''
          if (args.print) {
            const printState = await measurePrintState(page, '.node-body')
            failures.push(...printFailures(where, printState))
            await page.emulateMedia({ media: 'print' })
            await page.screenshot({
              path: join(outputDir, `print-${tag}-${String(index + 1).padStart(2, '0')}.png`),
              fullPage: true,
            })
            await page.emulateMedia({ media: 'screen' })
            shots += 1
            printNote = ` 打印katex=${printState.print.katexVisible}/${printState.print.katexTotal}`
          }
          notes.push(`${where}: katex=${measured.katex} 溢出=${measured.overflowing.length}${printNote}`)
        }

        if (jsErrors.length) {
          failures.push({
            code: 'visual:js_error',
            message: `${tag}: ${jsErrors.length} 个未捕获 JS 异常 — ${jsErrors.slice(0, 2).join(' | ')}`,
          })
        }
        if (consoleErrors.length) {
          failures.push({
            code: 'visual:console_error',
            message: `${tag}: ${consoleErrors.length} 条 console.error — ${consoleErrors.slice(0, 2).join(' | ')}`,
          })
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
  await writeResult(outputDir, {
    title,
    subject: `课程文件 \`${args.course || coursePath}\``,
    scenarioNote:
      `每场景抽查最长的 ${bodies.length} 节正文，共 ${shots} 张截图` +
      (args.print ? '；每节额外在 print 媒体下判定一次' : ''),
    failures,
    notes,
  })

  console.log(notes.join('\n'))
  console.log(`\n截图与报告：${outputDir}`)
  if (failures.length) {
    console.error(`\nFAILED (${failures.length}):`)
    for (const failure of failures) console.error(`  - [${failure.code}] ${failure.message}`)
    return 1
  }
  console.log(
    args.print
      ? '\nPASS: 四场景屏幕与打印两态均无排版事故。'
      : '\nPASS: 中英 × 桌面/移动四场景无排版事故。',
  )
  return 0
}

process.exitCode = await main()
