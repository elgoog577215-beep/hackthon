#!/usr/bin/env node
/**
 * L3f — page-level layout acceptance in a real browser.
 *
 * What this adds over L3b: jsdom does not lay anything out. Measured on this
 * repo, `getBoundingClientRect().width` is `0` for every element under jsdom,
 * so the L3b validator can prove a formula *renders without error* but cannot
 * prove it *fits on screen*. A formula that overflows a phone viewport is
 * clipped and unreadable while every existing check reports success.
 *
 * Deliberate non-goals, to avoid duplicating L3b:
 *   - no KaTeX/Markdown syntax checking (L3b already does it, in-process);
 *   - no pixel screenshot baseline. Font rendering differs per machine, the
 *     content is AI-generated and changes every run, and several agents edit
 *     the UI in parallel — a pixel baseline would break constantly and end up
 *     blanket-updated, which is worse than no baseline. Screenshots are written
 *     only for failures, as evidence for a human, never as the criterion.
 *
 * Dependency policy: playwright is intentionally NOT added to package.json.
 * The existing `scripts/record_video*.mjs` hardcode an absolute macOS path into
 * one developer's playwright install, which cannot work in CI or on another
 * machine — that pattern is not reused here. Instead this resolves a browser
 * from the environment and SKIPS (exit 0) when none is available, so nobody's
 * `npm test` or CI job starts failing because of a missing browser.
 *
 * Usage:
 *   node scripts/course_layout_smoke.mjs --dry-run
 *   node scripts/course_layout_smoke.mjs --html rendered.html
 *   LAYOUT_SMOKE_BROWSER=/path/to/chrome node scripts/course_layout_smoke.mjs
 */

import { createRequire } from 'node:module'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import process from 'node:process'

const require = createRequire(import.meta.url)

const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'desktop', width: 1280, height: 900 },
]

const SEVERITY_CRITICAL = 'critical'
const SEVERITY_MAJOR = 'major'

// Minimum WCAG AA ratio for body text. Below this a learner can see the text
// but cannot comfortably read it.
const MIN_CONTRAST_RATIO = 4.5

function parseArgs(argv) {
  const args = { dryRun: false, html: '', out: '', json: false }
  for (let index = 0; index < argv.length; index += 1) {
    const flag = argv[index]
    if (flag === '--dry-run') args.dryRun = true
    else if (flag === '--json') args.json = true
    else if (flag === '--html') args.html = argv[++index] || ''
    else if (flag === '--out') args.out = argv[++index] || ''
  }
  return args
}

/** Resolve a browser without making it a project dependency. */
function resolveBrowser() {
  const explicit = process.env.LAYOUT_SMOKE_BROWSER
  if (explicit && existsSync(explicit)) return explicit
  const cacheRoot = path.join(os.homedir(), '.cache', 'ms-playwright')
  if (!existsSync(cacheRoot)) return ''
  // Pick any cached chromium build rather than pinning a version number.
  const { readdirSync } = require('node:fs')
  for (const entry of readdirSync(cacheRoot)) {
    if (!entry.startsWith('chromium-')) continue
    const candidate = path.join(cacheRoot, entry, 'chrome-linux64', 'chrome')
    if (existsSync(candidate)) return candidate
  }
  return ''
}

function resolvePlaywright() {
  for (const id of ['playwright-core', 'playwright']) {
    try {
      return require(id)
    } catch {
      // try the next one
    }
  }
  return null
}

/** A page containing the shapes this check exists to catch. */
function fixtureHtml() {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"><style>
    body { margin: 0; font-family: system-ui, sans-serif; }
    .markdown-renderer { width: 100%; max-width: 960px; margin: 0 auto; padding: 16px; box-sizing: border-box; }
    .markdown-renderer table { border-collapse: collapse; }
    .markdown-renderer td, .markdown-renderer th { border: 1px solid #ddd; padding: 6px 10px; }
    pre { background: #f6f8fa; padding: 12px; overflow: auto; }
  </style></head><body>
    <div class="markdown-renderer">
      <h2>正常小节</h2>
      <p>这一段是普通正文，应当在任何视口下都完整可读。</p>
      <table><thead><tr><th>结构</th><th>复杂度</th></tr></thead>
        <tbody><tr><td>数组</td><td>O(n)</td></tr></tbody></table>
      <pre><code>const total = items.reduce((sum, item) => sum + item.value, 0)</code></pre>
    </div>
  </body></html>`
}

const MEASURE = `() => {
  const findings = []
  const root = document.querySelector('.markdown-renderer') || document.body
  const rootBox = root.getBoundingClientRect()
  const limit = Math.min(root.clientWidth || rootBox.width, window.innerWidth)

  const describe = (el) => {
    const tag = el.tagName.toLowerCase()
    const text = (el.textContent || '').trim().slice(0, 60)
    return text ? tag + ': ' + text : tag
  }

  // 1) Horizontal overflow: content wider than what the viewport can show is
  //    clipped, so the learner simply cannot read part of it.
  //    An element that scrolls horizontally by design (overflow-x auto/scroll,
  //    which is how code blocks and wide tables are meant to behave) is NOT a
  //    defect — the content is still reachable.
  const scrollsHorizontally = (el) => {
    let node = el
    while (node && node !== document.documentElement) {
      const overflowX = getComputedStyle(node).overflowX
      if (overflowX === 'auto' || overflowX === 'scroll') return true
      node = node.parentElement
    }
    return false
  }
  for (const el of root.querySelectorAll('table, pre, img, .katex-display, p, li')) {
    const box = el.getBoundingClientRect()
    if (box.width === 0 && box.height === 0) continue
    if (scrollsHorizontally(el)) continue
    const overflowBy = Math.round(Math.max(el.scrollWidth - limit, box.right - window.innerWidth))
    if (overflowBy > 1) {
      findings.push({ code: 'layout_overflow', severity: 'critical',
        detail: describe(el) + ' 超出可视宽度 ' + overflowBy + 'px' })
    }
  }

  // 2) Zero-height render: the element exists and has text, but occupies no
  //    space — visually it simply is not there, and nothing reports an error.
  for (const el of root.querySelectorAll('p, li, td, h1, h2, h3, pre')) {
    const box = el.getBoundingClientRect()
    if ((el.textContent || '').trim() && box.height === 0) {
      findings.push({ code: 'zero_height_render', severity: 'critical',
        detail: describe(el) + ' 有内容但高度为 0' })
    }
  }

  // 3) Contrast: readable-but-not-legible text.
  const luminance = (rgb) => {
    const parts = (rgb.match(/[\\d.]+/g) || []).slice(0, 3).map(Number)
    if (parts.length < 3) return null
    const channel = (value) => {
      const c = value / 255
      return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4)
    }
    return 0.2126 * channel(parts[0]) + 0.7152 * channel(parts[1]) + 0.0722 * channel(parts[2])
  }
  const backgroundOf = (el) => {
    let node = el
    while (node && node !== document.documentElement) {
      const bg = getComputedStyle(node).backgroundColor
      if (bg && !bg.includes('rgba(0, 0, 0, 0)') && bg !== 'transparent') return bg
      node = node.parentElement
    }
    return 'rgb(255, 255, 255)'
  }
  for (const el of root.querySelectorAll('p, li, td, th')) {
    if (!(el.textContent || '').trim()) continue
    const style = getComputedStyle(el)
    const fg = luminance(style.color)
    const bg = luminance(backgroundOf(el))
    if (fg === null || bg === null) continue
    const ratio = (Math.max(fg, bg) + 0.05) / (Math.min(fg, bg) + 0.05)
    if (ratio < ${MIN_CONTRAST_RATIO}) {
      findings.push({ code: 'low_contrast_text', severity: 'major',
        detail: describe(el) + ' 对比度 ' + ratio.toFixed(2) + '，低于 ${MIN_CONTRAST_RATIO}' })
    }
  }
  return findings
}`

async function run(args) {
  const playwright = resolvePlaywright()
  const executablePath = resolveBrowser()
  if (!playwright || !executablePath) {
    // Skipping is deliberate: a missing browser is an environment gap, not a
    // defect in the course. Failing here would make every machine without a
    // cached browser look broken.
    console.log(JSON.stringify({
      status: 'skipped',
      reason: !playwright
        ? '未找到 playwright-core，跳过页面级验收（不是项目依赖，属预期）'
        : '未找到可用浏览器，设置 LAYOUT_SMOKE_BROWSER 后重试',
    }, null, 2))
    return 0
  }

  const html = args.html ? readFileSync(args.html, 'utf8') : fixtureHtml()
  const outDir = args.out || path.join(os.tmpdir(), 'lingzhi-layout-smoke')
  const results = []
  const browser = await playwright.chromium.launch({ executablePath })
  try {
    for (const viewport of VIEWPORTS) {
      const page = await browser.newPage({
        viewport: { width: viewport.width, height: viewport.height },
      })
      await page.setContent(html, { waitUntil: 'load' })
      // The measurement body is kept as a string so it reads as one unit, but
      // playwright treats a bare string as an *expression* and would return
      // undefined — so hand it a real function.
      const findings = (await page.evaluate(new Function(`return (${MEASURE})()`))) || []
      if (findings.length) {
        mkdirSync(outDir, { recursive: true })
        const shot = path.join(outDir, `layout-${viewport.name}.png`)
        // Evidence for a human, never the criterion.
        await page.screenshot({ path: shot, fullPage: true })
        results.push({ viewport: viewport.name, findings, screenshot: shot })
      } else {
        results.push({ viewport: viewport.name, findings: [] })
      }
      await page.close()
    }
  } finally {
    await browser.close()
  }

  const all = results.flatMap(item => item.findings)
  const critical = all.filter(item => item.severity === SEVERITY_CRITICAL)
  const major = all.filter(item => item.severity === SEVERITY_MAJOR)
  const report = {
    status: critical.length ? 'failed' : major.length ? 'passed_with_warnings' : 'passed',
    dimension: 'render',
    checked_viewports: VIEWPORTS.map(item => item.name),
    critical_count: critical.length,
    major_count: major.length,
    results,
  }
  console.log(JSON.stringify(report, null, 2))
  return critical.length ? 1 : 0
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  if (args.dryRun) {
    console.log(JSON.stringify({
      status: 'dry-run',
      viewports: VIEWPORTS,
      checks: ['layout_overflow', 'zero_height_render', 'low_contrast_text'],
      browser: resolveBrowser() || '<未找到，运行时将跳过>',
      playwright: resolvePlaywright() ? 'available' : '<未安装，运行时将跳过>',
      note: '判据为断言式几何量测；不保存像素基线，截图仅在失败时作为证据。',
    }, null, 2))
    return 0
  }
  return run(args)
}

main().then(code => process.exit(code)).catch(error => {
  console.error(JSON.stringify({ status: 'error', error: String(error?.message || error) }, null, 2))
  process.exit(2)
})
