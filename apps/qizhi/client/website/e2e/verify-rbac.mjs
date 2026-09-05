#!/usr/bin/env node
/**
 * RBAC feature 完工闸门：端到端 + 截图验证脚本
 *
 * 覆盖：
 *   - 学生 / 教师 / 管理员三种角色的导航可见性
 *   - 学生地址栏直输教师路由 → 守卫拦截 + rbac:denied toast
 *   - 管理员用户管理 UI（列表 / 改角色弹窗 / 乐观更新 / 防自降级）
 *   - 改角色写入 audit_logs（action=user.role_update）
 *
 * 前置：
 *   1. `cd deploy && docker compose -f docker-compose.dashboard-local.yml up -d`
 *      （后端 + Postgres 起来；用 audit-e2e 同一份本地栈）
 *   2. `cd client/website && npm run dev` 起 Vite dev server（默认 5173）
 *   3. ADMIN_ZJU_IDS 环境变量包含 '99999999'（同 audit-e2e）
 *
 * 运行：node client/website/e2e/verify-rbac.mjs
 *
 * 产物（仓库根 tmp/screenshots/rbac/，已 gitignore）：
 *   01-student-navbar.png            学生 navbar 仅 智能对话
 *   02-student-blocked-outline.png   学生直输 /outline-form 被拦
 *   03-student-home.png              学生首页只剩 智能对话 卡片
 *   04-teacher-navbar.png            教师 navbar 全显
 *   05-teacher-outline-allowed.png   教师可进 /outline-form
 *   06-admin-users-list.png          管理员看 /admin/users 列表
 *   07-admin-role-change-dialog.png  改角色弹窗
 *   08-admin-role-change-success.png 改完徽章变色（乐观更新）
 *   09-admin-audit-log.png           audit 列表里 user.role_update 一行
 *   10-admin-self-demote-blocked.png 自降级被拦
 */

import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(SCRIPT_DIR, '..', '..', '..')
const OUT_DIR = resolve(REPO_ROOT, 'tmp', 'screenshots', 'rbac')

const BACKEND = process.env.RBAC_E2E_BACKEND ?? 'http://127.0.0.1:8000'
const FRONTEND = process.env.RBAC_E2E_FRONTEND ?? 'http://localhost:5173'

mkdirSync(OUT_DIR, { recursive: true })
mkdirSync(resolve(OUT_DIR, '_failures'), { recursive: true })

const ADMIN_ZJU_ID = '99999999'
const TEACHER_ZJU_ID = 'rbac-teacher-001'
const STUDENT_ZJU_ID = 'rbac-student-001'

function log(msg) {
  process.stdout.write(`[rbac-e2e] ${msg}\n`)
}

function fail(step, err) {
  process.stderr.write(`[rbac-e2e] FAIL @ ${step}: ${err?.stack ?? err}\n`)
  process.exit(1)
}

async function shot(page, file, fullPage = true) {
  const target = resolve(OUT_DIR, file)
  await page.screenshot({ path: target, fullPage })
  log(`screenshot → ${target}`)
}

async function shotFail(page, file) {
  try {
    const target = resolve(OUT_DIR, '_failures', file)
    await page.screenshot({ path: target, fullPage: true })
    log(`FAIL screenshot → ${target}`)
  } catch {
    // ignore secondary errors
  }
}

function assert(cond, msg) {
  if (!cond) throw new Error(`assertion failed: ${msg}`)
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

async function testLogin(name, zjuId) {
  const url = `${BACKEND}/auth/test-login?name=${encodeURIComponent(name)}&zju_id=${encodeURIComponent(zjuId)}`
  const { res, body } = await fetchJson(url, { method: 'POST' })
  assert(res.ok, `test-login(${zjuId}) HTTP ${res.status}`)
  const token = body?.data
  assert(typeof token === 'string' && token.length > 0, `test-login(${zjuId}) returned no token`)
  return token
}

async function getCurrentUser(token) {
  const { res, body } = await fetchJson(`${BACKEND}/user/current`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  assert(res.ok, `/user/current HTTP ${res.status}`)
  return body?.data
}

async function patchRole(adminToken, userId, role) {
  const { res, body } = await fetchJson(
    `${BACKEND}/admin/users/${encodeURIComponent(userId)}/role`,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${adminToken}`,
      },
      body: JSON.stringify({ role }),
    },
  )
  assert(res.ok, `PATCH role HTTP ${res.status} ${JSON.stringify(body)}`)
}

async function newPageWithToken(browser, token) {
  const ctx = await browser.newContext({
    userAgent: 'PlaywrightRbacE2E/1.0',
    viewport: { width: 1440, height: 900 },
  })
  await ctx.addInitScript((t) => {
    try {
      window.localStorage.setItem('auth_token', t)
      window.localStorage.setItem('auth_token_set_at', String(Date.now()))
    } catch {}
  }, token)
  const page = await ctx.newPage()
  return { ctx, page }
}

async function main() {
  // ====== Setup: 三个角色用户 ======
  log('SETUP: test-login admin/teacher/student')
  const adminToken = await testLogin('RBAC 验证管理员', ADMIN_ZJU_ID)
  const adminMe = await getCurrentUser(adminToken)
  assert(adminMe?.role === 'admin', `admin user role expected 'admin', got ${adminMe?.role}`)

  const teacherTokenPre = await testLogin('RBAC 验证教师', TEACHER_ZJU_ID)
  const teacherMe = await getCurrentUser(teacherTokenPre)
  // 提升到 teacher（默认创建是 student）
  await patchRole(adminToken, teacherMe.id, 'teacher')
  const teacherToken = await testLogin('RBAC 验证教师', TEACHER_ZJU_ID)  // 重新签发，token 内容相同
  const teacherMeAfter = await getCurrentUser(teacherToken)
  assert(teacherMeAfter?.role === 'teacher', `teacher role expected teacher, got ${teacherMeAfter?.role}`)

  const studentToken = await testLogin('RBAC 验证学生', STUDENT_ZJU_ID)
  const studentMe = await getCurrentUser(studentToken)
  assert(studentMe?.role === 'student', `student role expected student, got ${studentMe?.role}`)

  log(`users: admin=${adminMe.id}, teacher=${teacherMeAfter.id}, student=${studentMe.id}`)

  const browser = await chromium.launch({ headless: true })

  // ====== STEP 1: 学生 navbar ======
  let studentCtx
  try {
    log('STEP 1: student navbar')
    const { ctx, page } = await newPageWithToken(browser, studentToken)
    studentCtx = ctx
    await page.goto(`${FRONTEND}/chat`, { waitUntil: 'networkidle' })
    // 等导航栏渲染
    await page.waitForSelector('.nav-menu', { timeout: 8000 })
    const labels = await page.locator('.nav-menu .nav-item').allTextContents()
    log(`student nav items: ${JSON.stringify(labels)}`)
    assert(labels.length === 1 && labels[0].includes('智能对话'),
      `expected only '智能对话' for student, got ${JSON.stringify(labels)}`)
    await shot(page, '01-student-navbar.png')
  } catch (e) {
    await shotFail(studentCtx?.pages()?.[0], '01-student-navbar-FAILED.png')
    fail('STEP 1', e)
  }

  // ====== STEP 2: 学生直输 /outline-form 被拦 + toast ======
  try {
    log('STEP 2: student blocked from /outline-form')
    const page = studentCtx.pages()[0]
    await page.goto(`${FRONTEND}/outline-form`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(800)
    // 守卫会重定向到 /
    assert(new URL(page.url()).pathname === '/', `expected redirect to /, got ${page.url()}`)
    // toast 由路由守卫 dispatchEvent('rbac:denied') 触发，App.vue 监听后弹 3s
    await page.waitForSelector('.rbac-toast', { timeout: 3000 })
    await shot(page, '02-student-blocked-outline.png')
  } catch (e) {
    await shotFail(studentCtx?.pages()?.[0], '02-student-blocked-outline-FAILED.png')
    fail('STEP 2', e)
  }

  // ====== STEP 3: 学生首页只剩 智能对话 卡片 ======
  try {
    log('STEP 3: student home intro features')
    const page = studentCtx.pages()[0]
    await page.goto(`${FRONTEND}/`, { waitUntil: 'networkidle' })
    await page.waitForSelector('.home-intro-features', { timeout: 8000 })
    const cards = await page.locator('.intro-feature-card .intro-feature-card-title').allTextContents()
    log(`student home cards: ${JSON.stringify(cards)}`)
    assert(cards.length === 1 && cards[0].includes('智能对话'),
      `expected only 智能对话 card, got ${JSON.stringify(cards)}`)
    await shot(page, '03-student-home.png')
    await studentCtx.close()
    studentCtx = null
  } catch (e) {
    await shotFail(studentCtx?.pages()?.[0], '03-student-home-FAILED.png')
    fail('STEP 3', e)
  }

  // ====== STEP 4: 教师 navbar 全显 ======
  let teacherCtx
  try {
    log('STEP 4: teacher navbar')
    const { ctx, page } = await newPageWithToken(browser, teacherToken)
    teacherCtx = ctx
    await page.goto(`${FRONTEND}/chat`, { waitUntil: 'networkidle' })
    await page.waitForSelector('.nav-menu', { timeout: 8000 })
    const labels = await page.locator('.nav-menu .nav-item').allTextContents()
    log(`teacher nav items: ${JSON.stringify(labels)}`)
    assert(labels.length === 4, `expected 4 nav items for teacher, got ${labels.length}`)
    await shot(page, '04-teacher-navbar.png')
  } catch (e) {
    await shotFail(teacherCtx?.pages()?.[0], '04-teacher-navbar-FAILED.png')
    fail('STEP 4', e)
  }

  // ====== STEP 5: 教师可进 /outline-form ======
  try {
    log('STEP 5: teacher can access /outline-form')
    const page = teacherCtx.pages()[0]
    await page.goto(`${FRONTEND}/outline-form`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(800)
    assert(new URL(page.url()).pathname === '/outline-form',
      `expected on /outline-form, got ${page.url()}`)
    await shot(page, '05-teacher-outline-allowed.png')
    await teacherCtx.close()
    teacherCtx = null
  } catch (e) {
    await shotFail(teacherCtx?.pages()?.[0], '05-teacher-outline-allowed-FAILED.png')
    fail('STEP 5', e)
  }

  // ====== STEP 6: 管理员 /admin/users 列表 ======
  let adminCtx
  try {
    log('STEP 6: admin /admin/users list')
    const { ctx, page } = await newPageWithToken(browser, adminToken)
    adminCtx = ctx
    await page.goto(`${FRONTEND}/admin/users`, { waitUntil: 'networkidle' })
    await page.waitForSelector('.users-table tbody tr', { timeout: 8000 })
    // 确认至少能看到三种角色徽章
    const roles = new Set(await page.locator('.role-badge').allTextContents())
    log(`admin sees role badges: ${[...roles].join(', ')}`)
    assert(roles.has('管理员'), 'expected 管理员 badge visible')
    await shot(page, '06-admin-users-list.png')
  } catch (e) {
    await shotFail(adminCtx?.pages()?.[0], '06-admin-users-list-FAILED.png')
    fail('STEP 6', e)
  }

  // ====== STEP 7: 改角色弹窗 (对 student 行) ======
  try {
    log('STEP 7: open role change dialog on student row')
    const page = adminCtx.pages()[0]
    // 用搜索过滤定位到目标 student
    await page.locator('.filter-input').first().fill(STUDENT_ZJU_ID)
    await page.locator('.btn-secondary:has-text("查询")').click()
    await page.waitForTimeout(800)
    const targetRow = page.locator('.users-table tbody tr', { hasText: STUDENT_ZJU_ID }).first()
    await targetRow.locator('.btn-link:has-text("改角色")').click()
    await page.waitForSelector('.app-dialog-box', { timeout: 3000 })
    await shot(page, '07-admin-role-change-dialog.png')
  } catch (e) {
    await shotFail(adminCtx?.pages()?.[0], '07-admin-role-change-dialog-FAILED.png')
    fail('STEP 7', e)
  }

  // ====== STEP 8: 确认改 student → teacher，徽章立刻变色 ======
  try {
    log('STEP 8: change student → teacher')
    const page = adminCtx.pages()[0]
    // 在弹窗内选 teacher
    await page.locator('.role-option', { hasText: '教师' }).click()
    await page.locator('.app-dialog-btn.app-dialog-btn--primary').click()
    await page.waitForSelector('.app-dialog-box', { state: 'detached', timeout: 5000 })
    // 确认列表行徽章变为 teacher
    await page.waitForTimeout(500)
    const updatedRow = page.locator('.users-table tbody tr', { hasText: STUDENT_ZJU_ID }).first()
    const badge = await updatedRow.locator('.role-badge').textContent()
    assert(badge?.includes('教师'), `expected updated badge=教师, got ${badge}`)
    await shot(page, '08-admin-role-change-success.png')
    // 复位：再改回 student，便于脚本可重跑
    await patchRole(adminToken, studentMe.id, 'student')
  } catch (e) {
    await shotFail(adminCtx?.pages()?.[0], '08-admin-role-change-success-FAILED.png')
    fail('STEP 8', e)
  }

  // ====== STEP 9: audit 列表里能看到 user.role_update ======
  try {
    log('STEP 9: audit log contains user.role_update')
    const page = adminCtx.pages()[0]
    await page.goto(`${FRONTEND}/admin/audit-logs?action=user.role_update`, {
      waitUntil: 'networkidle',
    })
    await page.waitForTimeout(800)
    const rowCount = await page.locator('table tbody tr').count()
    assert(rowCount >= 1, `expected ≥1 role_update audit row, got ${rowCount}`)
    await shot(page, '09-admin-audit-log.png')
  } catch (e) {
    await shotFail(adminCtx?.pages()?.[0], '09-admin-audit-log-FAILED.png')
    fail('STEP 9', e)
  }

  // ====== STEP 10: 自降级被拦（后端校验） ======
  try {
    log('STEP 10: self-demote blocked')
    const { res, body } = await fetchJson(
      `${BACKEND}/admin/users/${encodeURIComponent(adminMe.id)}/role`,
      {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${adminToken}`,
        },
        body: JSON.stringify({ role: 'student' }),
      },
    )
    assert(!res.ok || body?.success === false,
      `expected self-demote to fail, got ${res.status} ${JSON.stringify(body)}`)
    // 截图：在 UI 上演示一次
    const page = adminCtx.pages()[0]
    await page.goto(`${FRONTEND}/admin/users?keyword=${encodeURIComponent(ADMIN_ZJU_ID)}`, {
      waitUntil: 'networkidle',
    })
    await page.waitForSelector('.users-table tbody tr', { timeout: 5000 })
    const adminRow = page.locator('.users-table tbody tr', { hasText: ADMIN_ZJU_ID }).first()
    await adminRow.locator('.btn-link:has-text("改角色")').click()
    await page.waitForSelector('.app-dialog-box', { timeout: 3000 })
    await page.locator('.role-option', { hasText: '学生' }).click()
    await page.locator('.app-dialog-btn').last().click()
    // 等错误提示出现
    await page.waitForSelector('.app-dialog-error', { timeout: 5000 })
    await shot(page, '10-admin-self-demote-blocked.png')
  } catch (e) {
    await shotFail(adminCtx?.pages()?.[0], '10-admin-self-demote-blocked-FAILED.png')
    fail('STEP 10', e)
  }

  await adminCtx?.close()
  await browser.close()

  log('ALL STEPS PASSED ✓')
  log(`产物目录: ${OUT_DIR}`)
}

main().catch((e) => {
  process.stderr.write(`[rbac-e2e] uncaught: ${e?.stack ?? e}\n`)
  process.exit(1)
})
