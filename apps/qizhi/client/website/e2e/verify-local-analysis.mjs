#!/usr/bin/env node
/**
 * 「使用本地分析」端到端 + 截图验证脚本。
 *
 * 覆盖：
 *   - 上传本地视频（分片上传 API：init/upload/finish/operation）
 *   - report-new 页「开始分析」弹出「选择分析方式」弹窗（新功能入口）
 *   - 选择「使用本地分析」→ 后端走自建 vLLM 跑通 POC 流水线
 *   - 轮询至分析完成 → 渲染五维度报告 → 逐 tab 截图
 *
 * 前置：
 *   1. cd deploy && docker compose -f docker-compose.dashboard-local.yml up -d --build
 *   2. cd client/website && npm run dev   （Vite，默认 5173）
 *   3. .env.dev 里 LOCAL_ANALYSIS_* 指向可达的自建 vLLM；LOCAL_ANALYSIS_MAX_SECONDS=120
 *
 * 运行：node client/website/e2e/verify-local-analysis.mjs
 * 产物（仓库根 tmp/screenshots/local-analysis/，已 gitignore）
 */

import { chromium } from 'playwright'
import { mkdirSync, readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(SCRIPT_DIR, '..', '..', '..')
const OUT_DIR = resolve(REPO_ROOT, 'tmp', 'screenshots', 'local-analysis')

const BACKEND = process.env.LA_E2E_BACKEND ?? 'http://127.0.0.1:8000'
const FRONTEND = process.env.LA_E2E_FRONTEND ?? 'http://localhost:5173'
const CLIP = process.env.LA_E2E_CLIP ?? resolve(REPO_ROOT, 'tmp', 'sample_2min.mp4')
const ADMIN_ZJU_ID = '99999999'
const POLL_TIMEOUT_MS = 15 * 60 * 1000
const POLL_INTERVAL_MS = 5000

mkdirSync(OUT_DIR, { recursive: true })
mkdirSync(resolve(OUT_DIR, '_failures'), { recursive: true })

function log(m) { process.stdout.write(`[la-e2e] ${m}\n`) }
function fail(step, err) { process.stderr.write(`[la-e2e] FAIL @ ${step}: ${err?.stack ?? err}\n`); process.exit(1) }
function assert(c, m) { if (!c) throw new Error(`assertion failed: ${m}`) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function shot(page, file, fullPage = true) {
  const target = resolve(OUT_DIR, file)
  await page.screenshot({ path: target, fullPage })
  log(`screenshot → ${target}`)
}
async function shotFail(page, file) {
  try { await page.screenshot({ path: resolve(OUT_DIR, '_failures', file), fullPage: true }) } catch {}
}

async function jpost(url, init = {}) {
  const res = await fetch(url, init)
  let body = null
  try { body = await res.json() } catch {}
  return { res, body }
}

async function testLogin(name, zjuId) {
  const { res, body } = await jpost(
    `${BACKEND}/auth/test-login?name=${encodeURIComponent(name)}&zju_id=${encodeURIComponent(zjuId)}`,
    { method: 'POST' },
  )
  assert(res.ok, `test-login HTTP ${res.status}`)
  const token = body?.data
  assert(typeof token === 'string' && token.length > 0, 'test-login returned no token')
  return token
}

async function uploadVideo(token, filePath) {
  const auth = { Authorization: `Bearer ${token}` }
  const buf = readFileSync(filePath)
  const blob = new Blob([buf], { type: 'video/mp4' })
  log(`uploading ${filePath} (${(buf.length / 1e6).toFixed(1)} MB) as 1 chunk`)

  const initForm = new FormData(); initForm.set('chunks', '1')
  const init = await jpost(`${BACKEND}/video/init`, { method: 'POST', headers: auth, body: initForm })
  assert(init.res.ok && init.body?.data, `init HTTP ${init.res.status} ${JSON.stringify(init.body)}`)
  const uploadId = init.body.data

  const upForm = new FormData()
  upForm.set('upload_id', uploadId); upForm.set('index', '0'); upForm.set('file', blob, 'sample_2min.mp4')
  const up = await jpost(`${BACKEND}/video/upload`, { method: 'POST', headers: auth, body: upForm })
  assert(up.res.ok, `upload HTTP ${up.res.status} ${JSON.stringify(up.body)}`)

  const finForm = new FormData(); finForm.set('upload_id', uploadId)
  const fin = await jpost(`${BACKEND}/video/finish`, { method: 'POST', headers: auth, body: finForm })
  assert(fin.res.ok && fin.body?.data?.path, `finish HTTP ${fin.res.status} ${JSON.stringify(fin.body)}`)
  const { path, cover_path } = fin.body.data

  const op = await jpost(`${BACKEND}/video/operation`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...auth },
    body: JSON.stringify({ operation: 'create', name: '本地分析E2E样例', path, cover: cover_path || '' }),
  })
  assert(op.res.ok && op.body?.data, `operation HTTP ${op.res.status} ${JSON.stringify(op.body)}`)
  const videoId = typeof op.body.data === 'string' ? op.body.data : op.body.data?.id
  assert(videoId, `no video id from operation: ${JSON.stringify(op.body)}`)
  return videoId
}

async function getStatus(token, id) {
  const { body } = await jpost(`${BACKEND}/video?id=${encodeURIComponent(id)}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  return body?.data?.status
}

async function newPageWithToken(browser, token) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  await ctx.addInitScript((t) => {
    try {
      window.localStorage.setItem('auth_token', t)
      window.localStorage.setItem('auth_token_set_at', String(Date.now()))
    } catch {}
  }, token)
  return { ctx, page: await ctx.newPage() }
}

async function main() {
  log(`SETUP: test-login admin(${ADMIN_ZJU_ID})`)
  const token = await testLogin('本地分析验证管理员', ADMIN_ZJU_ID)

  log('SETUP: upload sample clip via chunk API')
  const videoId = await uploadVideo(token, CLIP)
  log(`video created: ${videoId}`)
  const reportUrl = `${FRONTEND}/resource-analysis/report-new/${encodeURIComponent(videoId)}`

  const browser = await chromium.launch({ headless: true })
  let ctx, page
  try {
    ({ ctx, page } = await newPageWithToken(browser, token))

    // STEP 1：未分析态
    log('STEP 1: report-new unstarted')
    await page.goto(reportUrl, { waitUntil: 'networkidle' })
    await page.waitForSelector('.start-analysis-btn', { timeout: 15000 })
    await shot(page, '01-unstarted.png')

    // STEP 2：点击「开始分析」→ 方式选择弹窗
    log('STEP 2: open method-select modal')
    await page.locator('.start-analysis-btn').click()
    await page.waitForSelector('.method-modal', { timeout: 8000 })
    assert(await page.locator('.option-card', { hasText: '使用本地分析' }).count() === 1, '缺少「使用本地分析」选项')
    await shot(page, '02-method-modal.png')

    // STEP 3：选择「使用本地分析」并确认
    log('STEP 3: choose 使用本地分析')
    await page.locator('.option-card', { hasText: '使用本地分析' }).click()
    await page.locator('.method-modal .footer-btn.primary').click()
    await page.waitForSelector('.method-modal', { state: 'detached', timeout: 15000 })
    await page.waitForTimeout(1500)
    await shot(page, '03-analyzing.png')

    // STEP 4：轮询后端直到分析完成
    log('STEP 4: poll until analysis success')
    const deadline = Date.now() + POLL_TIMEOUT_MS
    let status = ''
    while (Date.now() < deadline) {
      status = await getStatus(token, videoId)
      log(`  status=${status}`)
      if (status === 'success') break
      if (status === 'failed') throw new Error('本地分析返回 failed，详见后端日志')
      await sleep(POLL_INTERVAL_MS)
    }
    assert(status === 'success', `分析未在 ${POLL_TIMEOUT_MS / 1000}s 内完成（status=${status}）`)

    // STEP 5：刷新渲染报告，逐 tab 截图
    log('STEP 5: render report + screenshot tabs')
    await page.reload({ waitUntil: 'networkidle' })
    await page.waitForSelector('.tab-bar', { timeout: 20000 })
    const overall = (await page.locator('.overall-number').first().textContent())?.trim()
    log(`  综合得分 = ${overall}`)
    assert(overall && Number(overall) > 0, `综合得分应 > 0，实际 ${overall}`)

    const tabs = [
      ['总览', '04-overview.png'],
      ['教学表达', '05-expression.png'],
      ['教学设计', '06-design.png'],
      ['知识呈现', '07-knowledge.png'],
      ['互动质量', '08-interaction.png'],
      ['思政融合', '09-ideology.png'],
    ]
    for (const [label, file] of tabs) {
      await page.locator('.tab-btn', { hasText: label }).first().click()
      await page.waitForTimeout(900)
      await shot(page, file)
    }

    log('ALL STEPS PASSED ✅')
  } catch (e) {
    await shotFail(page, 'FAILED.png')
    fail('main', e)
  } finally {
    await browser.close()
  }
}

main().catch((e) => fail('main', e))
