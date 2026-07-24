import { execFileSync, spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(import.meta.url)
const { chromium } = require('/Users/yq/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright')

const root = path.resolve(import.meta.dirname, '..')
const input = path.join('/tmp', 'lingzhi-real-input')
const dryRun = process.argv.includes('--dry-run')
const frontendOrigin = process.env.VIDEO2_FRONTEND_ORIGIN || 'http://127.0.0.1:5175'
const apiOrigin = process.env.VIDEO2_API_ORIGIN || 'http://127.0.0.1:8001'
const requestId = 'video2-project-prep-20260724-v1'
const sleep = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds))

const demo = {
  goal: '设计一个可验证的 AI 论文助手，研究 AI 辅助学习是否提高大学生学习效果',
  deliverable: '一套论文检索、证据比较和引用核验流程，以及一份带来源的研究报告',
  priorExperience: '会写提示词，能限定资料范围、规定输出格式并要求标注原文依据',
  uncertainty: '不会设计多步骤检索，不会筛选可靠论文，也不确定怎样核验结论和引用',
}

const generationPayload = {
  subject: '设计一个可验证的 AI 论文助手',
  difficulty: 'intermediate',
  composition_style: 'project_driven',
  pedagogy_mode: 'programming_engineering',
  secondary_mode: 'humanities_social',
  secondary_intensity: 'collaborative',
  generation_mode: 'review_blueprint',
  course_purpose: 'systematic',
  course_type: 'project',
  course_intent: {
    schema_version: 'course_intent_v1',
    type: 'project',
    project_goal: demo.goal,
    expected_deliverable: '一套可运行的论文检索、证据比较与引用核验流程，以及一份带来源的研究报告',
    prior_experience: '会写清楚提示词，能限定资料范围、规定输出格式并要求标注原文依据',
    current_uncertainty: '不会设计多步骤检索流程，不会筛选可靠论文，也不确定怎样核验结论与引用',
    project_constraints: '无来源结论不得进入报告；生成最终报告前必须人工确认',
  },
  grounding_strategy: 'material_first',
  requirements: '围绕真实研究任务边做边学；已会的提示词基础快速通过，重点补足检索、筛选、证据比较、引用核验和人工确认',
  web_question_enrichment: { enabled: true },
  request_id: requestId,
}

execFileSync('swiftc', ['-O', path.join(root, 'scripts', 'video2_real_input.swift'), '-o', input])

async function prepareOutline() {
  const response = await fetch(`${apiOrigin}/api/course-generation/generate`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(generationPayload),
  })
  if (!response.ok) throw new Error(`样板课程准备失败：HTTP ${response.status}`)
  const job = await response.json()
  const deadline = Date.now() + 5 * 60_000
  while (Date.now() < deadline) {
    const taskResponse = await fetch(`${apiOrigin}/api/tasks/${job.job_id}`)
    if (!taskResponse.ok) throw new Error(`样板任务读取失败：HTTP ${taskResponse.status}`)
    const task = await taskResponse.json()
    if (task.status === 'waiting_for_review' && task.current_phase === 'outline_ready') {
      return { ...job, task }
    }
    if (['failed', 'error', 'cancelled'].includes(task.status)) {
      throw new Error(`样板课程未生成成功：${task.error || task.message || task.status}`)
    }
    await sleep(2500)
  }
  throw new Error('样板课程在 5 分钟内没有进入个人路径待确认状态')
}

const prepared = await prepareOutline()
const browser = await chromium.connectOverCDP('http://127.0.0.1:9223')
const context = browser.contexts()[0]
const page = context.pages().find(item => item.url().startsWith(frontendOrigin)) || await context.newPage()
page.setDefaultTimeout(30_000)

await page.route('**/api/course-generation/generate', async route => {
  const request = route.request()
  const body = request.postDataJSON()
  body.request_id = requestId
  await route.continue({
    postData: JSON.stringify(body),
    headers: { ...request.headers(), 'content-type': 'application/json' },
  })
})

const windowMetrics = await page.evaluate(() => ({
  x: window.screenX,
  y: window.screenY,
  chromeHeight: window.outerHeight - window.innerHeight,
}))

function realInput(...args) {
  execFileSync(input, args.map(String))
}

async function point(locator) {
  await locator.scrollIntoViewIfNeeded()
  const box = await locator.boundingBox()
  if (!box) throw new Error(`目标不可见：${await locator.first().textContent().catch(() => '')}`)
  return {
    x: windowMetrics.x + box.x + box.width / 2,
    y: windowMetrics.y + windowMetrics.chromeHeight + box.y + box.height / 2,
  }
}

async function realClick(locator, pause = 450) {
  const target = await point(locator)
  realInput('click', target.x, target.y, 0.62)
  await sleep(pause)
}

async function replaceByPaste(locator, value, pause = 1050) {
  await realClick(locator, 520)
  realInput('select-all')
  realInput('delete')
  await sleep(380)
  spawnSync('pbcopy', [], { input: value })
  realInput('paste')
  await sleep(pause)
  if (await locator.inputValue() !== value) throw new Error('输入内容校验失败')
}

async function installVisualLayer() {
  await page.evaluate(() => {
    document.getElementById('recording-visual-layer-style')?.remove()
    document.getElementById('recording-cursor')?.remove()
    const style = document.createElement('style')
    style.id = 'recording-visual-layer-style'
    style.textContent = `
      html,body,button,input,textarea,select,a,*{cursor:none!important}
      #recording-cursor{position:fixed;z-index:2147483647;width:34px;height:34px;border:3px solid #fff;border-radius:50%;background:rgba(79,70,229,.38);box-shadow:0 0 0 5px rgba(79,70,229,.2),0 7px 20px rgba(15,23,42,.32);transform:translate(-50%,-50%);pointer-events:none;transition:width .12s,height .12s,background .12s}
      #recording-cursor.is-down{width:25px;height:25px;background:rgba(245,158,11,.78)}
      .recording-trail{position:fixed;z-index:2147483645;width:10px;height:10px;border-radius:50%;background:rgba(79,70,229,.42);transform:translate(-50%,-50%);pointer-events:none;animation:recordingTrail .75s ease-out forwards}
      .recording-ripple{position:fixed;z-index:2147483646;width:18px;height:18px;border:3px solid #f59e0b;border-radius:50%;transform:translate(-50%,-50%);pointer-events:none;animation:recordingRipple .62s ease-out forwards}
      #recording-cue{position:fixed;z-index:2147483646;left:50%;top:76px;max-width:760px;padding:12px 22px 14px;color:#fff;background:rgba(17,24,39,.94);border:1px solid rgba(255,255,255,.24);border-radius:8px;box-shadow:0 14px 34px rgba(0,0,0,.24);transform:translateX(-50%);pointer-events:none;text-align:center}
      #recording-cue small{display:block;margin-bottom:3px;color:#9ee6c8;font-size:13px;font-weight:800}
      #recording-cue strong{display:block;font-size:21px;line-height:1.35;letter-spacing:0}
      #recording-target{position:fixed;z-index:2147483644;border:3px solid #f59e0b;border-radius:8px;box-shadow:0 0 0 5px rgba(245,158,11,.18);pointer-events:none;transition:all .24s ease}
      #recording-target:after{content:'↓';position:absolute;left:50%;top:-38px;width:30px;height:30px;display:grid;place-items:center;color:#111827;background:#f59e0b;border-radius:50%;font-size:20px;font-weight:900;transform:translateX(-50%)}
      @keyframes recordingTrail{to{opacity:0;transform:translate(-50%,-50%) scale(.2)}}
      @keyframes recordingRipple{to{opacity:0;width:72px;height:72px}}
    `
    document.head.appendChild(style)
    const cursor = document.createElement('div')
    cursor.id = 'recording-cursor'
    document.body.appendChild(cursor)
    let lastTrailAt = 0
    document.addEventListener('pointermove', event => {
      cursor.style.left = `${event.clientX}px`
      cursor.style.top = `${event.clientY}px`
      if (performance.now() - lastTrailAt < 70) return
      lastTrailAt = performance.now()
      const trail = document.createElement('i')
      trail.className = 'recording-trail'
      trail.style.left = `${event.clientX}px`
      trail.style.top = `${event.clientY}px`
      document.body.appendChild(trail)
      window.setTimeout(() => trail.remove(), 780)
    }, true)
    document.addEventListener('pointerdown', event => {
      cursor.classList.add('is-down')
      const ripple = document.createElement('i')
      ripple.className = 'recording-ripple'
      ripple.style.left = `${event.clientX}px`
      ripple.style.top = `${event.clientY}px`
      document.body.appendChild(ripple)
      window.setTimeout(() => ripple.remove(), 650)
    }, true)
    document.addEventListener('pointerup', () => cursor.classList.remove('is-down'), true)
    window.__recordingCue = ({ text, eyebrow, box }) => {
      document.getElementById('recording-cue')?.remove()
      document.getElementById('recording-target')?.remove()
      const card = document.createElement('div')
      card.id = 'recording-cue'
      const small = document.createElement('small')
      small.textContent = eyebrow
      const strong = document.createElement('strong')
      strong.textContent = text
      card.append(small, strong)
      document.body.appendChild(card)
      if (!box) return
      const target = document.createElement('div')
      target.id = 'recording-target'
      Object.assign(target.style, {
        left: `${box.x - 6}px`,
        top: `${box.y - 6}px`,
        width: `${box.width + 12}px`,
        height: `${box.height + 12}px`,
      })
      document.body.appendChild(target)
    }
  })
}

async function cue(text, locator = null, eyebrow = '操作提示') {
  const box = locator ? await locator.boundingBox() : null
  await page.evaluate(({ text, eyebrow, box }) => window.__recordingCue?.({ text, eyebrow, box }), {
    text,
    eyebrow,
    box,
  })
}

async function reachCourseLibrary() {
  await page.goto(`${frontendOrigin}/courses`, { waitUntil: 'networkidle' })
  await installVisualLayer()
  await page.getByRole('button', { name: /新建课程/ }).waitFor()
}

if (dryRun) {
  await page.goto(`${frontendOrigin}/courses`, { waitUntil: 'networkidle' })
  const targetCenters = {}
  const createCourse = page.getByRole('button', { name: /新建课程/ })
  targetCenters.createCourse = await point(createCourse)
  await createCourse.click()
  const projectType = page.locator('[data-course-type="project"]')
  targetCenters.projectType = await point(projectType)
  await projectType.click()
  await page.locator('#project-goal').fill(demo.goal)
  await page.locator('#project-deliverable').fill(demo.deliverable)
  await page.locator('#project-prior-experience').fill(demo.priorExperience)
  await page.locator('#project-current-uncertainty').fill(demo.uncertainty)
  targetCenters.goal = await point(page.locator('#project-goal'))
  targetCenters.deliverable = await point(page.locator('#project-deliverable'))
  targetCenters.priorExperience = await point(page.locator('#project-prior-experience'))
  targetCenters.uncertainty = await point(page.locator('#project-current-uncertainty'))
  const submit = page.getByRole('button', { name: /确认需求，生成目录/ })
  targetCenters.submit = await point(submit)
  await submit.click()
  await page.waitForURL(`**/course/${prepared.course_id}/learn**`)
  await page.locator('.outline-review').waitFor()
  await page.locator('.outline-review__starting-point').waitFor()
  await page.locator('.outline-review__nodes li').first().waitFor()
  const pathNodes = await page.locator('.outline-review__nodes li').allTextContents()
  targetCenters.startingPoint = await point(page.locator('.outline-review__starting-point'))
  targetCenters.promptValidation = await point(page.locator('.outline-review__nodes li').nth(2))
  targetCenters.retrievalFocus = await point(page.locator('.outline-review__nodes li').nth(4))
  targetCenters.citationGate = await point(page.locator('.outline-review__nodes li').nth(21))
  targetCenters.finalMilestone = await point(page.locator('.outline-review__nodes li').nth(24))
  targetCenters.confirmPath = await point(page.getByRole('button', { name: '确认目录并继续' }))
  const result = {
    browser: 'Microsoft Edge',
    frontendOrigin,
    apiOrigin,
    courseId: prepared.course_id,
    jobId: prepared.job_id,
    taskStatus: prepared.task.status,
    outlineNodes: pathNodes.length,
    hasTentativeStartingPoint: await page.getByText('暂定起点', { exact: true }).count(),
    hasProjectValidation: pathNodes.some(text => text.includes('项目中验证')),
    hasFocus: pathNodes.some(text => text.includes('重点补充')),
    hasMilestone: pathNodes.some(text => text.includes('项目节点')),
    targetCenters,
    recordlyStartStopPoint: { x: 950, y: 949 },
  }
  console.log(JSON.stringify(result, null, 2))
  process.exit(0)
}

await reachCourseLibrary()

// Recordly 只捕获已经选定的 Edge 窗口；红色开始/停止按钮固定在主屏幕该坐标。
realInput('click', 950, 949, 0.45)
await sleep(1700)
execFileSync('osascript', ['-e', 'tell application "Microsoft Edge" to activate'])
await sleep(900)
const startedAt = Date.now()
async function holdUntil(seconds) {
  const remaining = seconds * 1000 - (Date.now() - startedAt)
  if (remaining > 0) await sleep(remaining)
}

await cue('同一个项目，不同学生应该从不同的地方开始', null, '视频二 · 因人而长')
await holdUntil(4)

const createCourse = page.getByRole('button', { name: /新建课程/ })
await cue('学生拿到真实项目后，从课程类型开始定义学习方式', createCourse, '创建个人课程')
await realClick(createCourse, 500)
await page.locator('[data-course-type="project"]').waitFor()
await holdUntil(7)

const projectType = page.locator('[data-course-type="project"]')
await cue('选择“项目实战”，围绕真实交付物边做边学', projectType, '先决定学习类型')
await realClick(projectType, 650)
await holdUntil(11)

const goal = page.locator('#project-goal')
await cue('先说清楚要完成的真实项目', goal, '项目目标')
await replaceByPaste(goal, demo.goal)
await holdUntil(19)

const deliverable = page.locator('#project-deliverable')
await cue('再明确最后必须交付什么', deliverable, '可检查的成果')
await replaceByPaste(deliverable, demo.deliverable)
await holdUntil(27)

const prior = page.locator('#project-prior-experience')
await cue('林晓已经会写 Prompt，并能限定来源和格式', prior, '已有经验')
await replaceByPaste(prior, demo.priorExperience)
await holdUntil(36)

const uncertainty = page.locator('#project-current-uncertainty')
await cue('但他不会检索、筛选，也不会核验引用', uncertainty, '当前短板')
await replaceByPaste(uncertainty, demo.uncertainty, 1350)
await holdUntil(45)

const startingNote = page.locator('.starting-point-note')
await cue('自述只形成暂定起点，后续还要在项目中验证', startingNote, '不把自述当成掌握证据')
await holdUntil(50)

const submit = page.getByRole('button', { name: /确认需求，生成目录/ })
await cue('确认后，系统为这个学生生成第一版个人路径', submit, '生成个人课程')
await realClick(submit, 600)
await page.waitForURL(`**/course/${prepared.course_id}/learn**`)
await page.locator('.outline-review').waitFor()
await page.locator('.outline-review__starting-point').waitFor()
await page.locator('.outline-review__nodes li').first().waitFor()
await installVisualLayer()
await holdUntil(57)

const startingPoint = page.locator('.outline-review__starting-point')
await cue('交付物、已有经验和重点短板同时进入课程起点', startingPoint, '个人起点清楚可查')
await holdUntil(66)

const nodes = page.locator('.outline-review__nodes li')
const verifyPrompt = nodes.nth(2)
await cue('会写 Prompt 的部分不再重复教学，先放进项目里验证', verifyPrompt, '项目中验证')
await verifyPrompt.scrollIntoViewIfNeeded()
await holdUntil(73)

const retrievalFocus = nodes.nth(4)
await retrievalFocus.scrollIntoViewIfNeeded()
await cue('不会的多步骤检索被明确设为重点补充', retrievalFocus, '沿短板展开')
await holdUntil(80)

const citationGate = nodes.nth(21)
await citationGate.scrollIntoViewIfNeeded()
await cue('引用核验成为正式关卡：无来源结论不得进入报告', citationGate, '证据可验证')
await holdUntil(85)

const finalMilestone = nodes.nth(24)
await finalMilestone.scrollIntoViewIfNeeded()
await cue('最后把检索、比较、核验和报告整合成可交付流程', finalMilestone, '项目里程碑')
await holdUntil(89)

const confirm = page.getByRole('button', { name: '确认目录并继续' })
await cue('学生确认后才继续生成；同一个项目，每个人长出自己的学习路径', confirm, '保留学生确认边界')
const remaining = 91_000 - (Date.now() - startedAt)
if (remaining > 0) await sleep(remaining)
realInput('click', 950, 949, 0.45)
await sleep(2600)

console.log(JSON.stringify({
  browser: 'Microsoft Edge',
  courseId: prepared.course_id,
  jobId: prepared.job_id,
  duration: (Date.now() - startedAt) / 1000,
  finished: true,
}))
