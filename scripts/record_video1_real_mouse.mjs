import { execFileSync, spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require('/Users/yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')

const root = path.resolve(import.meta.dirname, '..')
const input = path.join('/tmp', 'lingzhi-real-input')
const dryRun = process.argv.includes('--dry-run')
const interactionCheck = process.argv.includes('--interaction-check')
const cdpEndpoint = process.env.EDGE_CDP_URL ?? 'http://127.0.0.1:9224'
const useRecordly = process.env.USE_RECORDLY === '1'
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))

if (!dryRun && !interactionCheck && process.env.ALLOW_GLOBAL_RECORDING !== '1') {
  throw new Error('视频一正式录制需要 ALLOW_GLOBAL_RECORDING=1，避免占用其他录制会话。')
}

execFileSync('swiftc', ['-O', path.join(root, 'scripts', 'macos_real_input.swift'), '-o', input])

const browser = await chromium.connectOverCDP(cdpEndpoint)
const page = browser.contexts()[0].pages().find(item => item.url().includes('demo-ai-literacy-update-v1'))
if (!page) throw new Error(`未在 ${cdpEndpoint} 找到视频一 Edge 页面`)
page.setDefaultTimeout(30_000)
await page.reload({ waitUntil: 'networkidle' })

const windowMetrics = await page.evaluate(() => ({
  x: window.screenX,
  y: window.screenY,
  chromeHeight: window.outerHeight - window.innerHeight,
}))

function realInput(...args) {
  execFileSync(input, args.map(String))
}

async function point(locator) {
  const box = await locator.boundingBox()
  if (!box) throw new Error(`目标不可见: ${await locator.first().textContent().catch(() => '')}`)
  return {
    x: windowMetrics.x + box.x + box.width / 2,
    y: windowMetrics.y + windowMetrics.chromeHeight + box.y + box.height / 2,
  }
}

async function realClick(locator, pause = 420) {
  const box = await locator.boundingBox()
  if (!box) throw new Error('点击目标不可见')
  await page.evaluate(({ x, y }) => window.__recordingPointer?.(x, y, true), {
    x: box.x + box.width / 2,
    y: box.y + box.height / 2,
  })
  const target = await point(locator)
  realInput('click', target.x, target.y, 0.58)
  await sleep(pause)
}

async function focusRecordingPage() {
  await page.bringToFront()
  await sleep(650)
  const canvas = page.locator('.deck-canvas').first()
  const target = await point(canvas)
  realInput('click', target.x, target.y, 0.42)
  await sleep(550)
  if (!await page.evaluate(() => document.hasFocus())) throw new Error('目标 Edge 窗口没有获得焦点')
}

async function ensureVisibleInSidebar(locator) {
  const viewport = await page.evaluate(() => ({ width: innerWidth, height: innerHeight }))
  const sidebarBox = await page.locator('.slide-thumbnails').boundingBox()
  if (!sidebarBox) throw new Error('课件缩略图栏不可见')
  const scrollPoint = {
    x: windowMetrics.x + sidebarBox.x + Math.min(sidebarBox.width / 2, 115),
    y: windowMetrics.y + windowMetrics.chromeHeight + Math.min(sidebarBox.y + sidebarBox.height / 2, viewport.height - 120),
  }

  for (let attempt = 0; attempt < 24; attempt += 1) {
    const box = await locator.boundingBox()
    if (box && box.y >= 90 && box.y + box.height <= viewport.height - 18) return box
    realInput('scroll', scrollPoint.x, scrollPoint.y, -8, 0.28)
    await sleep(240)
  }
  throw new Error('无法把第 17 课滚动到可见区域')
}

async function stopRecordingFromTray() {
  // Recordly 录制中托盘菜单依次为“显示控制栏”“停止录制”。
  realInput('click', 1140, 19, 0.38)
  await sleep(500)
  realInput('down')
  realInput('down')
  realInput('enter')
  await sleep(3200)
}

async function cue(text, locator = null, eyebrow = '操作提示') {
  const box = locator ? await locator.boundingBox() : null
  await page.evaluate(({ text, eyebrow, box }) => window.__recordingCue?.({ text, eyebrow, box }), { text, eyebrow, box })
}

async function chooseKeyMessage() {
  const select = page.locator('.slide-inspector select').first()
  await cue('选择“核心信息”，修改课程真正表达的内容', select, '编辑范围')
  await realClick(select, 180)
  realInput('down')
  realInput('down')
  realInput('enter')
  await sleep(420)
  if (await select.inputValue() !== 'key_message') throw new Error('核心信息选择失败')
}

async function replaceByPaste(textarea, text) {
  await realClick(textarea, 800)
  realInput('select-all')
  realInput('delete')
  await sleep(650)
  spawnSync('pbcopy', [], { input: text })
  realInput('paste')
  await sleep(1100)
  if (await textarea.inputValue() !== text) throw new Error('粘贴后的文本不完整')
}

async function openImpact(analyzeButton) {
  const createPlan = page.getByRole('button', { name: '生成精准同步方案' })
  const openWorkspace = page.getByRole('button', { name: '进入同源影响工作台' })
  await realClick(analyzeButton, 500)
  await Promise.race([createPlan.waitFor({ state: 'visible' }), openWorkspace.waitFor({ state: 'visible' })])
  if (await openWorkspace.isVisible().catch(() => false)) await realClick(openWorkspace, 420)
  await createPlan.waitFor({ state: 'visible' })
  return createPlan
}

await page.evaluate(() => {
  document.getElementById('recording-visual-layer-style')?.remove()
  const style = document.createElement('style')
  style.id = 'recording-visual-layer-style'
  style.textContent = `
    #recording-cue{position:fixed;z-index:2147483646;left:50%;top:78px;max-width:720px;padding:12px 22px 14px;color:#fff;background:rgba(17,24,39,.94);border:1px solid rgba(255,255,255,.24);border-radius:8px;box-shadow:0 14px 34px rgba(0,0,0,.24);transform:translateX(-50%);pointer-events:none;text-align:center}
    #recording-cue small{display:block;margin-bottom:3px;color:#8dd8ff;font-size:13px;font-weight:800}#recording-cue strong{display:block;font-size:21px;line-height:1.35;letter-spacing:0}
    #recording-target{position:fixed;z-index:2147483644;border:3px solid #ffb800;border-radius:8px;box-shadow:0 0 0 5px rgba(255,184,0,.18);pointer-events:none}
    #recording-target:after{content:'↓';position:absolute;left:50%;top:-38px;width:30px;height:30px;display:grid;place-items:center;color:#111827;background:#ffb800;border-radius:50%;font-size:20px;font-weight:900;transform:translateX(-50%)}
    #recording-pointer{position:fixed;z-index:2147483647;left:50%;top:55%;width:30px;height:30px;border:3px solid #fff;border-radius:50%;background:rgba(15,23,42,.76);box-shadow:0 0 0 3px rgba(15,23,42,.7),0 7px 18px rgba(0,0,0,.35);transform:translate(-50%,-50%);transition:left .56s cubic-bezier(.2,.75,.22,1),top .56s cubic-bezier(.2,.75,.22,1);pointer-events:none}
    #recording-pointer:after{content:'';position:absolute;inset:8px;border-radius:50%;background:#ffbd2e}
    #recording-pointer.is-clicking{animation:recording-click .48s ease-out}@keyframes recording-click{0%{box-shadow:0 0 0 3px rgba(15,23,42,.7),0 0 0 0 rgba(255,189,46,.8)}100%{box-shadow:0 0 0 3px rgba(15,23,42,.7),0 0 0 22px rgba(255,189,46,0)}}
  `
  document.head.appendChild(style)
  const pointer = document.createElement('div'); pointer.id = 'recording-pointer'; document.body.appendChild(pointer)
  window.__recordingPointer = (x, y, clicking = false) => {
    pointer.style.left = `${x}px`; pointer.style.top = `${y}px`
    if (!clicking) return
    pointer.classList.remove('is-clicking'); void pointer.offsetWidth; pointer.classList.add('is-clicking')
  }
  window.__recordingCue = ({ text, eyebrow, box }) => {
    document.getElementById('recording-cue')?.remove(); document.getElementById('recording-target')?.remove()
    const card = document.createElement('div'); card.id = 'recording-cue'
    const small = document.createElement('small'); small.textContent = eyebrow
    const strong = document.createElement('strong'); strong.textContent = text
    card.append(small, strong); document.body.appendChild(card)
    if (!box) return
    const target = document.createElement('div'); target.id = 'recording-target'
    Object.assign(target.style, { left:`${box.x-6}px`, top:`${box.y-6}px`, width:`${box.width+12}px`, height:`${box.height+12}px` })
    document.body.appendChild(target)
  }
})

const targetSlide = page.locator('.slide-thumbnails > button', { hasText: '第17讲 DeepSeek 核心能力与应用' }).first()
const sidebar = page.locator('.slide-thumbnails')
await cue('20 讲人工智能通识课已经准备完成', null, '视频一 · 课程随知识更新')

if (dryRun) {
  const result = {
    url: page.url(),
    windowMetrics,
    targetSlide: await targetSlide.count(),
    inspector: await page.locator('.slide-inspector').count(),
    analyzeButton: await page.getByRole('button', { name: '分析影响' }).count(),
  }
  console.log(JSON.stringify(result, null, 2))
  await browser.close()
  process.exit(0)
}

if (interactionCheck) {
  await focusRecordingPage()
  await ensureVisibleInSidebar(targetSlide)
  await realClick(targetSlide, 650)
  await chooseKeyMessage()
  console.log(JSON.stringify({
    focused: await page.evaluate(() => document.hasFocus()),
    selectedSlide: await targetSlide.getAttribute('aria-pressed').catch(() => null),
    selectedField: await page.locator('.slide-inspector select').first().inputValue(),
    inspectorText: await page.locator('.slide-inspector textarea').inputValue(),
  }, null, 2))
  await browser.close()
  process.exit(0)
}

await focusRecordingPage()
let recordingStarted = false
let recordingStopped = false
let startedAt = 0

try {
  if (useRecordly) {
    // 仅兼容旧流程；独立页面录制不会进入这里。
    realInput('click', 950, 949, 0.45)
    recordingStarted = true
    await sleep(450)
    realInput('move', 980, 420, 0.48)
    await sleep(3700)
  }
  await focusRecordingPage()
  startedAt = Date.now()
  await page.evaluate(() => { document.documentElement.dataset.video1Capture = 'started' })

  await sleep(3500)
  await cue('讲到第 17 讲时，DeepSeek 发布了新版本', sidebar, '找到需要更新的课程')
  await ensureVisibleInSidebar(targetSlide)
  await cue('原课程仍在讲 DeepSeek V3.2', targetSlide, '旧内容清楚可见')
  await sleep(2200)
  await realClick(targetSlide, 1200)

  await chooseKeyMessage()
  const textarea = page.locator('.slide-inspector textarea')
  await cue('V4 成为主线，同时保留 V3.2 的演进背景', textarea, '第一次真实修改')
  await sleep(1800)
  await replaceByPaste(textarea, '以 DeepSeek V4 为当前主线，并回顾 V3.2 的关键能力与技术演进')
  await sleep(1700)

  const analyze = page.getByRole('button', { name: '分析影响' })
  await cue('先分析影响，不会直接改写课程', analyze, '系统理解修改意图')
  const createPlan = await openImpact(analyze)
  await sleep(2000)
  await realClick(createPlan, 500)
  const confirmFirst = page.getByRole('button', { name: /确认联动 \d+ 处/ })
  await confirmFirst.waitFor({ state: 'visible' })
  await cue('只联动受影响内容，无关内容保持不变', page.locator('.impact-metrics'), '精准计算影响范围')
  await sleep(5000)
  await cue('教师确认后才正式更新课程', confirmFirst, '保留人工确认边界')
  await realClick(confirmFirst, 600)

  const returnToDeck = page.getByRole('button', { name: '查看更新后的课件' })
  await returnToDeck.waitFor({ state: 'visible' })
  await cue('同步回执可以逐项核对前后变化', page.locator('.impact-result-filter'), '第一次联动完成')
  await sleep(4500)
  await realClick(page.getByRole('button', { name: /^大纲/ }), 350)
  await cue('本讲目标已经更新', page.locator('.impact-detail-card').first(), '查看具体结果')
  await sleep(4500)
  await realClick(page.getByRole('button', { name: /^演示文稿/ }), 350)
  await cue('PPT 同步更新，无关页面不重写', page.locator('.impact-detail-card').first(), '所见即所得')
  await sleep(4000)
  await realClick(returnToDeck, 650)

  await ensureVisibleInSidebar(targetSlide)
  await realClick(targetSlide, 350)
  await chooseKeyMessage()
  await cue('再调整教学顺序：先回顾旧版，再比较新版', textarea, '第二次真实修改')
  await sleep(1800)
  await replaceByPaste(textarea, '先回顾 DeepSeek V3.2，再比较 V4 的核心变化、能力边界与应用场景')
  await sleep(1700)
  const secondPlan = await openImpact(page.getByRole('button', { name: '分析影响' }))
  await sleep(1800)
  await realClick(secondPlan, 420)
  const confirmSecond = page.getByRole('button', { name: /确认联动 \d+ 处/ })
  await confirmSecond.waitFor({ state: 'visible' })
  await cue('第二次修改仍沿同一来源链计算', page.locator('.impact-metrics'), '教学顺序也能联动')
  await sleep(4500)
  await realClick(confirmSecond, 500)
  await page.getByRole('button', { name: '查看更新后的课件' }).waitFor({ state: 'visible' })
  await realClick(page.getByRole('button', { name: /^演示文稿/ }), 350)
  await cue('讲稿已按“V3.2 回顾 → V4 变化 → 能力边界”重组', page.locator('.impact-detail-card').first(), '第二次联动完成')
  await sleep(6500)
  await cue('一处改变，全课联动。世界变了，课程跟着变。', null, '人工智能通识课 · 第 17 讲已更新')

  const remaining = 91_000 - (Date.now() - startedAt)
  if (remaining > 0) await sleep(remaining)
  await page.evaluate(() => { document.documentElement.dataset.video1Capture = 'finished' })
  if (useRecordly) {
    await stopRecordingFromTray()
    recordingStopped = true
  }
  console.log(JSON.stringify({ duration: (Date.now() - startedAt) / 1000, finished: true }))
} finally {
  if (recordingStarted && !recordingStopped) await stopRecordingFromTray().catch(() => {})
}

await browser.close()
