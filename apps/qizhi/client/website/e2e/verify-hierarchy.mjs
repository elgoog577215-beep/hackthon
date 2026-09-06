#!/usr/bin/env node
/**
 * 课程资源层级化（课程 → 大纲版本 → 教案版本 → PPT/视频绑定）端到端验证脚本
 *
 * 覆盖：
 *   - API：大纲版本号自增（课程作用域）、教案/PPT 版本号自增（父资源作用域）
 *   - API：父类型链校验（PPT 不允许直接挂大纲）
 *   - API：视频绑定教案版本 + 按 resource_id 过滤
 *   - UI：课程页大纲版本面板 / 大纲详情页教案版本列表 / 教案详情页 PPT+视频区 / 层级步骤条
 *
 * 前置：
 *   1. `cp server/.env.dev server/.env && cd deploy && ENV=LOCAL docker compose up -d --build`
 *   2. 测试用户角色需为 teacher（脚本内通过 docker exec psql 提权）
 *
 * 运行：node client/website/e2e/verify-hierarchy.mjs
 *
 * 产物（仓库根 tmp/hierarchy-verify/，已 gitignore）：
 *   01-course-outline-versions.png   课程页：大纲版本面板（v2/v1 倒序）
 *   02-outline-detail-plans.png      大纲详情页：教案版本列表 + 层级步骤条
 *   03-plan-detail-ppt-video.png     教案详情页：PPT 版本 + 已绑定视频
 *   04-bind-video-modal.png          绑定视频弹窗
 *   05-stepper-back-to-course.png    步骤条回跳课程页
 */

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { execSync } from 'node:child_process'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(SCRIPT_DIR, '..', '..', '..')
const OUT_DIR = resolve(REPO_ROOT, 'tmp', 'hierarchy-verify')

const FRONTEND = process.env.HIER_E2E_FRONTEND ?? 'http://localhost'
const BACKEND = process.env.HIER_E2E_BACKEND ?? 'http://localhost/api'

const TEACHER_ZJU_ID = 'hier-teacher-001'

mkdirSync(OUT_DIR, { recursive: true })
mkdirSync(resolve(OUT_DIR, '_failures'), { recursive: true })

function log(msg) {
  process.stdout.write(`[hier-e2e] ${msg}\n`)
}

function assert(cond, msg) {
  if (!cond) throw new Error(`assertion failed: ${msg}`)
}

async function shot(page, file) {
  // 路由切换带滑动过渡动画（route-slide），等动画结束再截，避免新旧页面同框
  await page.waitForTimeout(900)
  const target = resolve(OUT_DIR, file)
  await page.screenshot({ path: target, fullPage: true })
  log(`screenshot → ${target}`)
}

async function fetchJson(url, init = {}) {
  const res = await fetch(url, init)
  let body = null
  try {
    body = await res.json()
  } catch {
    body = null
  }
  return { res, body }
}

let TOKEN = ''

async function api(method, path, payload) {
  const init = {
    method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${TOKEN}`,
    },
  }
  if (payload !== undefined) init.body = JSON.stringify(payload)
  const { res, body } = await fetchJson(`${BACKEND}${path}`, init)
  return { status: res.status, body }
}

async function apiOk(method, path, payload) {
  const { status, body } = await api(method, path, payload)
  assert(status === 200 && body?.success, `${method} ${path} → HTTP ${status} ${JSON.stringify(body)}`)
  return body.data
}

async function main() {
  // ====== Setup：登录 + 提权 teacher ======
  log('SETUP: test-login + SQL 提权 teacher')
  const { res: loginRes, body: loginBody } = await fetchJson(
    `${BACKEND}/auth/test-login?name=${encodeURIComponent('层级验证教师')}&zju_id=${TEACHER_ZJU_ID}`,
    { method: 'POST' },
  )
  assert(loginRes.ok && loginBody?.data, `test-login HTTP ${loginRes.status}`)
  TOKEN = loginBody.data

  // test_login 不更新已有用户角色，统一用 SQL 兜底提权
  execSync(
    `docker exec edu-ai-home-db psql -U postgres -d edu_ai_home -c "UPDATE users SET role='teacher' WHERE zju_id='${TEACHER_ZJU_ID}';"`,
    { stdio: 'pipe' },
  )

  // ====== API 层验证 ======
  log('API: 创建课程')
  // 课程可见性按 managers 关联判定（不看 creator_id），必须把当前用户放进 manager_ids
  const me = await apiOk('GET', '/user/current')
  const courseId = await apiOk('POST', '/course/operation', {
    operation: 'create',
    name: '数据结构与算法（层级验证）',
    description: '课程 → 大纲 → 教案 → 课件 层级化验证用课程',
    labels: ['层级验证'],
    lesson_count: 32,
    manager_ids: [me.id],
  })

  log('API: 创建大纲 v1 / v2（课程作用域版本号自增）')
  const outline1 = await apiOk('POST', '/resource/operation', {
    operation: 'create',
    name: '教学大纲（初稿）',
    resource_type: 'outline',
    editable: true,
    related_course_id: courseId,
  })
  const outline2 = await apiOk('POST', '/resource/operation', {
    operation: 'create',
    name: '教学大纲（修订版）',
    resource_type: 'outline',
    editable: true,
    related_course_id: courseId,
  })
  const o1 = await apiOk('GET', `/resource?id=${outline1}`)
  const o2 = await apiOk('GET', `/resource?id=${outline2}`)
  assert(o1.version_number === 1, `outline1 版本应为 1，实际 ${o1.version_number}`)
  assert(o2.version_number === 2, `outline2 版本应为 2，实际 ${o2.version_number}`)

  log('API: 大纲 v2 下创建教案 v1 / v2（父资源作用域版本号自增）')
  const plan1 = await apiOk('POST', '/resource/operation', {
    operation: 'create',
    name: '教案（第一版）',
    resource_type: 'teaching_plan',
    editable: true,
    parent_resource_id: outline2,
  })
  const plan2 = await apiOk('POST', '/resource/operation', {
    operation: 'create',
    name: '教案（第二版）',
    resource_type: 'teaching_plan',
    editable: true,
    parent_resource_id: outline2,
  })
  const p1 = await apiOk('GET', `/resource?id=${plan1}`)
  const p2 = await apiOk('GET', `/resource?id=${plan2}`)
  assert(p1.version_number === 1 && p2.version_number === 2, `教案版本应为 1/2，实际 ${p1.version_number}/${p2.version_number}`)
  assert(p2.parent_resource_id === outline2, '教案应挂在大纲 v2 下')
  assert(p2.related_course?.id === courseId, '教案应继承大纲的课程归属')

  log('API: 教案 v2 下创建 PPT v1')
  const ppt1 = await apiOk('POST', '/resource/operation', {
    operation: 'create',
    name: '课堂 PPT',
    resource_type: 'ppt',
    editable: true,
    parent_resource_id: plan2,
  })
  const pp1 = await apiOk('GET', `/resource?id=${ppt1}`)
  assert(pp1.version_number === 1 && pp1.parent_resource_id === plan2, 'PPT 应为 v1 且挂在教案 v2 下')

  log('API: 负向用例——PPT 直接挂大纲应被类型链拒绝')
  const { body: badBody } = await api('POST', '/resource/operation', {
    operation: 'create',
    name: '非法 PPT',
    resource_type: 'ppt',
    editable: true,
    parent_resource_id: outline2,
  })
  assert(badBody?.success === false, `PPT 挂大纲应失败，实际 ${JSON.stringify(badBody)}`)

  log('API: root_only 大纲版本列表（倒序）')
  const roots = await apiOk(
    'GET',
    `/resource/list?course_id=${courseId}&resource_type=outline&root_only=true`,
  )
  assert(roots.length === 2, `根级大纲应为 2 个，实际 ${roots.length}`)
  assert(roots[0].version_number === 2 && roots[1].version_number === 1, '大纲列表应按版本倒序')
  assert(roots[0].child_count === 2, `大纲 v2 子级数应为 2，实际 ${roots[0].child_count}`)

  log('API: parent_resource_id 下钻教案版本列表')
  const plans = await apiOk('GET', `/resource/list?parent_resource_id=${outline2}`)
  assert(plans.length === 2, `大纲 v2 下应有 2 个教案，实际 ${plans.length}`)

  log('API: 创建视频并绑定到教案 v2')
  const videoId = await apiOk('POST', '/video/operation', {
    operation: 'create',
    name: '课堂实录-第1讲',
    path: '',
    cover: '',
  })
  await apiOk('POST', '/video/binding', {
    id: videoId,
    related_resource_id: plan2,
    related_course_id: courseId,
  })
  const boundVideos = await apiOk('GET', `/video/list?resource_id=${plan2}`)
  assert(boundVideos.length === 1 && boundVideos[0].id === videoId, '按教案过滤应命中绑定视频')
  assert(boundVideos[0].related_course_id === courseId, '视频应同时绑定课程')

  log('API 层验证全部通过 ✓')

  // ====== UI 层验证 ======
  const browser = await chromium.launch()
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  await ctx.addInitScript((t) => {
    try {
      window.localStorage.setItem('auth_token', t)
      window.localStorage.setItem('auth_token_set_at', String(Date.now()))
    } catch {}
  }, TOKEN)
  const page = await ctx.newPage()

  try {
    log('UI: 课程页大纲版本面板')
    await page.goto(`${FRONTEND}/course/${courseId}`, { waitUntil: 'networkidle' })
    await page.waitForSelector('.outline-versions-panel .outline-version-row', { timeout: 15000 })
    const rowCount = await page.locator('.outline-version-row').count()
    assert(rowCount === 2, `课程页应显示 2 个大纲版本，实际 ${rowCount}`)
    const firstBadge = await page.locator('.outline-version-row .version-badge').first().innerText()
    assert(firstBadge.trim() === 'v2', `首行版本徽章应为 v2，实际 ${firstBadge}`)
    await shot(page, '01-course-outline-versions.png')

    log('UI: 进入大纲详情页（教案版本列表 + 步骤条）')
    await page.locator('.outline-version-row').first().click()
    await page.waitForURL(`**/course/${courseId}/outline/${outline2}`, { timeout: 15000 })
    await page.waitForSelector('.children-section .version-row', { timeout: 15000 })
    const stepperCurrent = await page.locator('.hierarchy-stepper .step-chip.is-current .step-label').innerText()
    assert(stepperCurrent.includes('大纲'), `步骤条当前层级应为大纲，实际 ${stepperCurrent}`)
    const planRows = await page.locator('.version-row').count()
    assert(planRows === 2, `大纲详情页应显示 2 个教案版本，实际 ${planRows}`)
    await shot(page, '02-outline-detail-plans.png')

    log('UI: 进入教案详情页（PPT 版本 + 绑定视频）')
    await page.locator('.version-row').first().click()
    await page.waitForURL(`**/plan/${plan2}`, { timeout: 15000 })
    await page.waitForSelector('.video-card', { timeout: 15000 })
    const pptRows = await page.locator('.version-badge.red').count()
    assert(pptRows >= 1, `教案详情页应显示 PPT 版本，实际 ${pptRows}`)
    const videoCards = await page.locator('.video-card').count()
    assert(videoCards === 1, `应显示 1 个绑定视频，实际 ${videoCards}`)
    await shot(page, '03-plan-detail-ppt-video.png')

    log('UI: 绑定视频弹窗')
    await page.getByRole('button', { name: '+ 绑定已有视频' }).click()
    await page.waitForSelector('.bind-video-modal', { timeout: 10000 })
    await shot(page, '04-bind-video-modal.png')
    await page.locator('.bind-video-modal .action-btn.secondary').click()

    log('UI: 步骤条回跳课程页')
    await page.locator('.hierarchy-stepper .step-chip.is-done').first().click()
    await page.waitForURL(`**/course/${courseId}`, { timeout: 15000 })
    await page.waitForSelector('.outline-versions-panel', { timeout: 15000 })
    await shot(page, '05-stepper-back-to-course.png')

    log('UI 层验证全部通过 ✓')
  } catch (err) {
    await page.screenshot({ path: resolve(OUT_DIR, '_failures', 'failure.png'), fullPage: true }).catch(() => {})
    throw err
  } finally {
    await browser.close()
  }

  log('ALL PASS ✓ 截图见 tmp/hierarchy-verify/')
}

main().catch((err) => {
  process.stderr.write(`[hier-e2e] FAIL: ${err?.stack ?? err}\n`)
  process.exit(1)
})
