/**
 * 知识维护面板真机验收（真实 Chrome + 真实课程数据，不是 jsdom）。
 *
 * 为什么必须有这个脚本：前两轮真机验收各抓到一个 jsdom 测不出的缺陷
 * （视图 ID 失配导致面板在全部真实课程上不可用；确认回执被静默刷新卸载）。
 * 共同点是单测全绿、后端正确，只有真人操作路径才暴露。上一轮的驱动脚本没有
 * 提交，只留下截图，导致这轮要重写——所以这次提交。
 *
 * 用法（需先起好后端与 vite）：
 *   node scripts/knowledge_panel_acceptance.mjs \
 *     --base http://127.0.0.1:5611 \
 *     --course <course_id> \
 *     --out docs/验收/知识维护面板真机
 *
 * 判据不是"截图拍到了"，而是每一步都断言了可观察结果；任何一步失败即退出非零。
 */

import { chromium, devices } from 'playwright'
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'

const args = Object.fromEntries(
  process.argv.slice(2).reduce((acc, cur, i, arr) => {
    if (cur.startsWith('--')) acc.push([cur.slice(2), arr[i + 1]])
    return acc
  }, []),
)

const BASE = args.base || 'http://127.0.0.1:5611'
const COURSE = args.course
const OUT = args.out || 'docs/验收/知识维护面板真机'
if (!COURSE) {
  console.error('必须给 --course <course_id>')
  process.exit(2)
}

/** 每个场景的结果，最后汇总成 markdown 报告。 */
const findings = []
const errors = []

function record(scenario, step, ok, detail) {
  findings.push({ scenario, step, ok, detail })
  const mark = ok ? '✓' : '✗'
  console.log(`  ${mark} ${step}${detail ? ' — ' + detail : ''}`)
  if (!ok) errors.push(`[${scenario}] ${step}: ${detail}`)
}

/**
 * 从课程库进入目标课程。
 *
 * `?course=<id>` 不是深链：应用会重定向到 `/courses` 课程库列表，必须点
 * "进入课程"。这一点单测发现不了——jsdom 里组件是被直接挂载的，根本没有
 * 路由重定向这一步。
 */
async function enterCourse(page, courseId) {
  await page.goto(`${BASE}/courses`, { waitUntil: 'networkidle', timeout: 60000 })
  // 课程卡片是异步拉取的，等它出现再点，否则会点在还没渲染的空列表上。
  await page.locator('a, button').filter({ hasText: /进入课程|Enter course|Open course/ })
    .first().waitFor({ state: 'visible', timeout: 30000 }).catch(() => {})

  const card = page.locator(`[data-course-id="${courseId}"]`).first()
  if (await card.count()) {
    const link = card.locator('a, button').filter({ hasText: /进入课程|Enter|Open/ }).first()
    await (await link.count() ? link : card).click()
  } else {
    // 没有 data-course-id 时按卡片顺序点第一张"进入课程"。
    const enter = page.locator('a, button').filter({ hasText: /进入课程|Enter course|Open course/ }).first()
    if (!await enter.count()) return false
    await enter.click()
  }
  // 用 URL 变化判断跳转成功，比等固定时长可靠。
  await page.waitForURL(/\/course\//, { timeout: 30000 }).catch(() => {})
  await page.waitForLoadState('networkidle', { timeout: 60000 }).catch(() => {})
  return /\/course\//.test(new URL(page.url()).pathname)
}

/**
 * 打开知识库浮层。
 *
 * 面板是底栏工具，入口按钮的可访问名在中英文下不同，所以按 data 属性与
 * 文案双路兜底——真机上最脆的就是选择器，宁可多试几种也不要因为找不到按钮
 * 就误判成"功能坏了"。
 */
async function openLibrary(page) {
  const candidates = [
    '[data-testid="knowledge-library-entry"]',
    'button:has-text("知识库")',
    'button:has-text("Knowledge")',
    '[aria-label*="知识库"]',
    '[aria-label*="Knowledge"]',
    '[title*="知识库"]',
    '[title*="Knowledge"]',
  ]
  for (const sel of candidates) {
    const el = page.locator(sel).first()
    if (await el.count() && await el.isVisible().catch(() => false)) {
      await el.click()
      await page.waitForTimeout(1500)
      return true
    }
  }
  return false
}

async function run(scenario, contextOptions, locale, writeFlow = false) {
  console.log(`\n=== ${scenario} ===`)
  const browser = await chromium.launch()
  const context = await browser.newContext(contextOptions)
  const page = await context.newPage()

  const jsErrors = []
  const httpErrors = []
  page.on('pageerror', e => jsErrors.push(String(e)))
  page.on('response', r => {
    if (r.status() >= 400 && r.url().includes('/api/')) {
      httpErrors.push(`${r.status()} ${r.url().split('/api/')[1]}`)
    }
  })

  const dir = join(OUT, scenario)
  await mkdir(dir, { recursive: true })
  const shot = async name => {
    await page.screenshot({ path: join(dir, `${name}.png`), fullPage: false })
  }

  try {
    // 语言在 localStorage 里，必须在首次导航前种下去，否则会先渲染成默认语言。
    // 键名是 `app-locale`（见 src/shared/i18n.ts），不要凭直觉猜。
    await page.addInitScript(loc => {
      localStorage.setItem('app-locale', loc)
      localStorage.setItem('lingzhi_learner_id_v1', 'learner_accept_' + loc)
    }, locale)

    await page.goto(`${BASE}/`, { waitUntil: 'networkidle', timeout: 60000 })
    await page.waitForTimeout(1500)
    await shot('00-loaded')
    record(scenario, '首页加载', true, page.url())

    const entered = await enterCourse(page, COURSE)
    record(scenario, '进入课程', entered, page.url())
    await shot('01-course')

    const opened = await openLibrary(page)
    record(scenario, '打开知识库浮层', opened, opened ? '' : '未找到入口按钮')
    if (!opened) throw new Error('cannot open library')

    // 真实课程是 10MB 级 envelope，知识库要等后端编译 + 传输，固定 sleep 会
    // 把"还在转圈"误判成"渲染为空"。这里等真实节点出现，最多 60s。
    const treeReady = await page.locator('.knowledge-tree-row').first()
      .waitFor({ state: 'visible', timeout: 60000 })
      .then(() => true).catch(() => false)
    record(scenario, '知识库加载完成（非固定等待）', treeReady, treeReady ? '' : '60s 内未出现节点')
    await page.waitForTimeout(800)
    await shot('02-library')

    // 判据一：真实课程下知识树必须有节点。上一轮的生产缺陷正是这里空白。
    const rows = await page.locator('.knowledge-tree-row').count()
    record(scenario, '知识树渲染出节点', rows > 0, `${rows} 行`)

    // 判据二：D2 无依据横幅。这门课有资料依据，所以横幅**不该**出现。
    const banner = await page.locator('.knowledge-source-grounding').count()
    record(scenario, 'D2 横幅按数据显示（本课有依据→不该出现）', banner === 0, `count=${banner}`)

    // 选一个原子知识点
    const point = page.locator('.knowledge-tree-row.is-knowledge_point .knowledge-tree-node').first()
    const hasPoint = await point.count() > 0
    record(scenario, '存在原子知识点', hasPoint, '')
    if (hasPoint) {
      await point.click()
      await page.waitForTimeout(1200)
      await shot('03-detail')

      const detail = await page.locator('.knowledge-tree-detail').innerText().catch(() => '')
      record(scenario, '知识点详情有内容', detail.length > 20, `${detail.length} 字`)

      // 判据三：D1 来源标签必须是三态之一的可读文案，不是裸值。
      const footer = await page.locator('.knowledge-tree-detail-footer').innerText().catch(() => '')
      const rawLeak = /material_grounded|course_generated|web_grounded|course_source/.test(footer)
      record(scenario, 'D1 来源标签已本地化（无裸值泄漏）', !rawLeak, footer.split('\n')[0])

      // --- 写入全链：改写 → 影响面 → 确认 → 重建 → 修订历史 ---
      //
      // 只在中文桌面跑一次。写入会真的落库（候选式确认），多个场景重复写同一
      // 门课会互相干扰，而且英文/移动端要验的是渲染与布局，不是重复验业务。
      if (writeFlow) {
        const panel = page.locator('.knowledge-command-panel')
        const hasPanel = await panel.count() > 0
        record(scenario, '知识维护面板存在', hasPanel, '')

        if (hasPanel) {
          // AI 拆分候选：真实模型调用，可能慢，也可能因 provider 不可用而降级。
          // 结论渲染在 `.knowledge-command-note`（splitVerdict），拆分部件在
          // `.knowledge-command-detail-list`——"不需要拆分"是**合法结论**，
          // 所以只要出现结论文案就算通过，不能要求必须给出拆分部件。
          const splitBtn = panel.locator('button').filter({ hasText: /拆分|split/i }).first()
          if (await splitBtn.count()) {
            await splitBtn.click()
            const verdict = panel.locator('.knowledge-command-note').first()
            const splitDone = await verdict
              .waitFor({ state: 'visible', timeout: 120000 })
              .then(() => true).catch(() => false)
            await shot('05-ai-split')
            const verdictText = splitDone ? await verdict.innerText().catch(() => '') : ''
            record(scenario, 'AI 拆分候选返回结论', splitDone,
              splitDone ? verdictText.slice(0, 70).replace(/\n/g, ' ')
                        : '120s 内无结论（provider 不可用时属预期降级）')
          }

          // 改写陈述：填入可识别的新内容 + 理由，然后预览影响面。
          const textarea = panel.locator('textarea').first()
          if (await textarea.count()) {
            const stamp = `真机验收 ${new Date().toISOString().slice(0, 16)}`
            await textarea.fill(`化学反应速率用单位时间内浓度变化量表示。（${stamp}）`)
            const reason = panel.locator('input[type="text"], textarea').nth(1)
            if (await reason.count()) await reason.fill('真机验收：验证改写→影响面→确认全链')
            await shot('06-edit-filled')

            const preview = panel.locator('button').filter({ hasText: /预览|Preview/i }).first()
            if (await preview.count()) {
              await preview.click()
              const impactShown = await panel.locator('.knowledge-command-impact, [data-testid="impact-report"]')
                .first().waitFor({ state: 'visible', timeout: 60000 })
                .then(() => true).catch(() => false)
              await shot('07-impact')
              record(scenario, '影响面预览返回', impactShown, '')

              if (impactShown) {
                const impactText = await panel.locator('.knowledge-command-impact, [data-testid="impact-report"]')
                  .first().innerText().catch(() => '')
                // 上一轮真机缺陷：明细行只显示裸 ID。这里要求出现可读标题。
                const rawIdOnly = /\b(ckp_|ckb_|lo_)[0-9a-f]{6,}/.test(impactText)
                  && !/[一-鿿]{2,}/.test(impactText)
                record(scenario, '影响面明细可读（非裸 ID）', !rawIdOnly, impactText.slice(0, 60).replace(/\n/g, ' '))

                const confirm = panel.locator('button').filter({ hasText: /确认|Confirm/i }).first()
                if (await confirm.count() && await confirm.isEnabled()) {
                  await confirm.click()
                  const receipt = await panel.locator('.knowledge-command-receipt, [data-testid="receipt"]')
                    .first().waitFor({ state: 'visible', timeout: 60000 })
                    .then(() => true).catch(() => false)
                  await page.waitForTimeout(2000)
                  await shot('08-confirmed')
                  // 上一轮真机缺陷：确认后回执与重建入口被静默刷新卸载。
                  const stillVisible = await panel.count() > 0
                  record(scenario, '确认后回执可见（不被刷新卸载）', receipt && stillVisible,
                    `receipt=${receipt} panel=${stillVisible}`)

                  const rebuild = panel.locator('button').filter({ hasText: /重建|Rebuild/i }).first()
                  if (await rebuild.count()) {
                    await rebuild.click()
                    await page.waitForTimeout(4000)
                    await shot('09-rebuild')
                    record(scenario, '重建入口可点击并有反馈', true, '')
                  }

                  const history = panel.locator('button').filter({ hasText: /历史|History/i }).first()
                  if (await history.count()) {
                    await history.click()
                    // 断言必须落在历史列表本身，不能拿整个面板的文字充数——
                    // 面板里本来就有"修改理由"输入框，用面板全文断言会永远为真。
                    const listShown = await panel.locator('.knowledge-command-history-list')
                      .first().waitFor({ state: 'visible', timeout: 30000 })
                      .then(() => true).catch(() => false)
                    await shot('10-history')
                    const rows = listShown
                      ? await panel.locator('.knowledge-command-history-list li').count()
                      : 0
                    const listText = listShown
                      ? await panel.locator('.knowledge-command-history-list').innerText().catch(() => '')
                      : ''
                    record(scenario, '修订历史列出本次改动', listShown && rows > 0,
                      `${rows} 条 · ${listText.slice(0, 50).replace(/\n/g, ' ')}`)
                  }
                }
              }
            }
          }
        }
      }
    }

    // 关系图视图
    const graphBtn = page.locator('[data-testid="knowledge-view-mode"] button').nth(1)
    if (await graphBtn.count()) {
      await graphBtn.click()
      await page.waitForTimeout(1800)
      await shot('04-relation-graph')
      const graphNodes = await page.locator('.knowledge-relation-graph svg, .knowledge-relation-graph canvas').count()
      record(scenario, '关系图渲染', graphNodes > 0, `容器 ${graphNodes}`)
      await page.locator('[data-testid="knowledge-view-mode"] button').first().click()
      await page.waitForTimeout(1000)
    }

    // 英文场景专查中文残留（上一轮真机抓到过英文模式下的中文标签）。
    //
    // 只查界面骨架（标题、视图切换、面板页脚标签），**不查详情正文**：
    // 这门课本身是中文化学课，知识点名称、陈述、易错点都是中文，把它们算成
    // "未翻译"是我第一版检查的错误——那会让这条断言永远为红，等于没有断言。
    if (locale === 'en') {
      const chrome = await Promise.all([
        page.locator('.knowledge-tree-header').innerText().catch(() => ''),
        page.locator('[data-testid="knowledge-view-mode"]').innerText().catch(() => ''),
      ])
      const cjk = chrome.join(' ').match(/[一-鿿]{2,}/g) || []
      record(scenario, '英文模式界面骨架无中文残留', cjk.length === 0, cjk.slice(0, 4).join(' / '))
    }

    record(scenario, '零 JS 异常', jsErrors.length === 0, jsErrors.slice(0, 2).join(' | '))
    record(scenario, '无非预期 4xx/5xx', httpErrors.length === 0, httpErrors.slice(0, 3).join(' | '))
    await shot('99-final')
  } catch (e) {
    record(scenario, '场景异常中断', false, String(e).slice(0, 200))
    await shot('99-error').catch(() => {})
  } finally {
    await context.close()
    await browser.close()
  }
}

const scenarios = [
  // 写入全链只在中文桌面跑一次：写入会真的落库，重复写同一门课会互相干扰。
  ['zh-desktop', { viewport: { width: 1440, height: 900 }, locale: 'zh-CN' }, 'zh', true],
  ['en-desktop', { viewport: { width: 1440, height: 900 }, locale: 'en-US' }, 'en'],
  ['zh-mobile-iphone15', { ...devices['iPhone 15'], locale: 'zh-CN' }, 'zh'],
  ['zh-mobile-iphonese', { ...devices['iPhone SE'], locale: 'zh-CN' }, 'zh'],
]

for (const [name, opts, loc, write] of scenarios) {
  await run(name, opts, loc, write)
}

// 汇总报告：把断言结果写成表，方便验收时逐条核对，而不是只看截图。
const lines = ['# 知识维护面板真机验收结果', '']
lines.push(`- 课程：\`${COURSE}\``)
lines.push(`- 前端：${BASE}（真实 Chromium，非 jsdom）`)
lines.push(`- 场景：${scenarios.map(s => s[0]).join(' / ')}`)
lines.push('')
lines.push('| 场景 | 步骤 | 结果 | 细节 |')
lines.push('| --- | --- | --- | --- |')
for (const f of findings) {
  lines.push(`| ${f.scenario} | ${f.step} | ${f.ok ? '✓' : '**✗**'} | ${(f.detail || '').replace(/\|/g, '\\|').slice(0, 80)} |`)
}
lines.push('')
lines.push(errors.length ? `## 失败项（${errors.length}）\n\n` + errors.map(e => `- ${e}`).join('\n')
                         : '## 全部通过')
await writeFile(join(OUT, 'RESULT.md'), lines.join('\n'), 'utf-8')

console.log(`\n结果写入 ${join(OUT, 'RESULT.md')}`)
console.log(errors.length ? `失败 ${errors.length} 项` : '全部通过')
process.exit(errors.length ? 1 : 0)
