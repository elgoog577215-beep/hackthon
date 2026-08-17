/**
 * 发布前真实渲染关卡：用学习者浏览器里的同一条链路渲染课程正文。
 *
 * Why this exists: the Python gate cannot run KaTeX, so its math rules are
 * pattern matching over source text. Measured on 8 real courses (792 nodes),
 * that tier misses 72% of the nodes that actually fail to render — the defects
 * it cannot see are `\omega^0^2`, `\left{ ... \right$}`, `\text{ J·s}`: the
 * `$$` pairing and block structure are all legal, so no regex tier can know
 * KaTeX will reject them. Only a real parse finds these.
 *
 * This script is that parse. It imports `frontend/src/utils/markdown.ts` — the
 * single render path behind every surface in the product — and reports what the
 * learner would actually see. Output is shaped for
 * `evaluate_node_content(render_diagnostics=...)`, so the verdict travels back
 * through the channel that already exists rather than a new one.
 *
 * Run from the repo root:
 *   node scripts/render_gate.mjs --course backend/data/courses/<id>.json
 *   node scripts/render_gate.mjs --course <file> --out report.json
 *   node scripts/render_gate.mjs --course <file> --format text
 *
 * Exits non-zero when any node fails to render, so it can gate a release.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
import { dirname, resolve } from 'node:path'
import { createRequire } from 'node:module'
import { spawnSync } from 'node:child_process'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROOT = resolve(HERE, '..')
const FRONTEND = resolve(ROOT, 'frontend')

// `markdown.ts` is TypeScript and imports via the `@` alias and a CSS side
// effect, none of which bare node resolves. vite-node applies the app's own
// vite config, so the module loads exactly as it does in the browser build.
// Re-exec through it once, rather than making every caller remember to.
if (!process.env.RENDER_GATE_UNDER_VITE) {
  const viteNode = resolve(FRONTEND, 'node_modules/.bin/vite-node')
  if (!existsSync(viteNode)) {
    console.error(`找不到 vite-node：${viteNode}\n请先在 frontend/ 执行 npm install`)
    process.exit(2)
  }
  const result = spawnSync(
    viteNode,
    [fileURLToPath(import.meta.url), '--', ...process.argv.slice(2)],
    {
      cwd: FRONTEND,
      stdio: 'inherit',
      env: { ...process.env, RENDER_GATE_UNDER_VITE: '1' },
    },
  )
  process.exit(result.status === null ? 1 : result.status)
}


function parseArgs(argv) {
  const args = { course: '', out: '', format: 'json', quiet: false }
  for (let i = 2; i < argv.length; i += 1) {
    const flag = argv[i]
    if (flag === '--course') args.course = argv[++i]
    else if (flag === '--out') args.out = argv[++i]
    else if (flag === '--format') args.format = argv[++i]
    else if (flag === '--quiet') args.quiet = true
  }
  return args
}

/**
 * Pull every renderable body out of a course file.
 *
 * Two schemas coexist in this repo and both are still on disk: the legacy flat
 * `nodes[].node_content`, and the canonical `course_document.blocks[].payload
 * .markdown`. Reading both means the gate works on stored courses and on
 * freshly generated ones without the caller having to know which it holds.
 */
function extractBodies(course) {
  const bodies = []
  for (const node of course.nodes || []) {
    const content = String(node.node_content || '')
    if (content.trim()) {
      bodies.push({
        id: String(node.node_id || ''),
        name: String(node.node_name || ''),
        content,
      })
    }
  }
  const doc = course.course_document || {}
  for (const block of doc.blocks || []) {
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

async function main() {
  const args = parseArgs(process.argv)
  if (!args.course) {
    console.error('用法: node scripts/render_gate.mjs --course <course.json> [--out <report.json>] [--format json|text]')
    return 2
  }

  // markdown.ts touches `document`/`NodeFilter` at render time, and DOMPurify
  // silently returns its input unsanitized when there is no DOM — so install
  // one before importing, or the gate would quietly stop sanitizing.
  const require = createRequire(pathToFileURL(`${FRONTEND}/package.json`))
  const { JSDOM } = require('jsdom')
  const dom = new JSDOM('<!doctype html><html><body></body></html>')
  globalThis.window = dom.window
  globalThis.document = dom.window.document
  globalThis.NodeFilter = dom.window.NodeFilter
  globalThis.Node = dom.window.Node
  globalThis.DOMParser = dom.window.DOMParser
  globalThis.Element = dom.window.Element
  globalThis.HTMLElement = dom.window.HTMLElement

  const { renderMarkdown } = await import('@/utils/markdown')
  const { renderFailures, resetRenderFailures, withRenderContext } =
    await import('@/utils/render-diagnostics')

  const course = JSON.parse(readFileSync(resolve(ROOT, args.course), 'utf8'))
  const bodies = extractBodies(course)

  const nodes = []
  for (const body of bodies) {
    resetRenderFailures()
    let html = ''
    let threw = ''
    try {
      html = withRenderContext(body.id, () => renderMarkdown(body.content))
    } catch (error) {
      threw = String((error && error.message) || error)
    }
    const failures = renderFailures()

    const box = document.createElement('div')
    box.innerHTML = html
    const katexErrors = Array.from(box.querySelectorAll('.katex-error'))
    const mathFallbacks = Array.from(box.querySelectorAll('.math-fallback'))

    // What the learner would read, excluding the math that rendered correctly.
    // KaTeX output legitimately contains LaTeX-looking strings in its MathML
    // annotations, so the check runs on the text *outside* every `.katex` node:
    // anything left there is source the renderer failed to convert, which is
    // exactly the `cases/aligned` symptom — real corpus example, a node whose
    // matrices render but whose `A \xrightarrow{R_2 \leftarrow R_2 - 2R_1}`
    // connectors are read out as literal backslash commands.
    const outside = box.cloneNode(true)
    for (const rendered of outside.querySelectorAll('.katex, .math-fallback')) {
      rendered.remove()
    }
    const leakedSource = /\\(?:begin|end)\{|\\frac|\\left|\\right|\\xrightarrow|\\mathbf|\\rangle/
      .test(outside.textContent || '')

    const mathFailureCount = katexErrors.length + mathFallbacks.length
    const blockFailureCount = (threw ? 1 : 0) +
      failures.filter(f => f.kind === 'block').length

    nodes.push({
      node_id: body.id,
      node_name: body.name,
      chars: body.content.length,
      passed: mathFailureCount === 0 && blockFailureCount === 0 && !leakedSource,
      leaked_source: leakedSource,
      threw,
      // Exactly the shape `evaluate_node_content(render_diagnostics=...)` reads.
      render_diagnostics: {
        math_failure_count: mathFailureCount,
        block_failure_count: blockFailureCount,
      },
      katex_error_count: katexErrors.length,
      math_fallback_count: mathFallbacks.length,
      samples: [
        ...katexErrors.slice(0, 2).map(el => ({
          kind: 'katex_error',
          detail: (el.getAttribute('title') || el.textContent || '').slice(0, 200),
        })),
        ...mathFallbacks.slice(0, 2).map(el => ({
          kind: 'math_fallback',
          detail: (el.textContent || '').slice(0, 200),
        })),
      ],
    })
  }
  resetRenderFailures()

  const failing = nodes.filter(n => !n.passed)
  const report = {
    contract_version: 'render_gate_v1',
    dimension: 'visual',
    course_id: course.course_id || '',
    course_name: course.course_name || (course.course_document || {}).title || '',
    source: args.course,
    renderer: 'frontend/src/utils/markdown.ts (markdown-it + KaTeX + DOMPurify)',
    passed: failing.length === 0,
    checked_nodes: nodes.length,
    failing_nodes: failing.length,
    failing_node_ids: failing.map(n => n.node_id),
    nodes,
  }

  if (args.out) {
    writeFileSync(resolve(ROOT, args.out), JSON.stringify(report, null, 1))
  }
  if (!args.quiet) {
    if (args.format === 'text') {
      console.log(`视觉正确性报告 — ${report.course_name || report.course_id}`)
      console.log(`渲染器：${report.renderer}`)
      console.log(`检查 ${report.checked_nodes} 节，失败 ${report.failing_nodes} 节\n`)
      for (const node of failing) {
        console.log(`✗ ${node.node_id} ${node.node_name}`)
        if (node.threw) console.log(`    渲染抛错：${node.threw}`)
        if (node.leaked_source) console.log('    LaTeX 源码泄漏到正文')
        for (const sample of node.samples) {
          console.log(`    [${sample.kind}] ${sample.detail.slice(0, 120)}`)
        }
      }
      if (!failing.length) console.log('全部节点渲染正常。')
    } else {
      console.log(JSON.stringify(report, null, 1))
    }
  }
  return failing.length ? 1 : 0
}

process.exitCode = await main()
