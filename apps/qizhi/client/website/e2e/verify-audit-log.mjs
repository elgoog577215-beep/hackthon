#!/usr/bin/env node
/**
 * 审计日志 feature 完工闸门：端到端 + 截图验证脚本
 *
 * 前置：
 *   1. `cd deploy && docker compose -f docker-compose.dashboard-local.yml up -d`
 *      （后端 + Postgres + 假数据已起来）
 *   2. `cd client/website && npm run dev` 起 Vite dev server（默认 5173）
 *   3. 已 `npm install playwright` 且 `npx playwright install chromium`
 *
 * 运行：node client/website/e2e/verify-audit-log.mjs
 *
 * 产物（仓库根 tmp/audit-log-e2e/，已 gitignore）：
 *   01-dashboard-with-audit-nav.png
 *   02-agent-toggled.png
 *   03-audit-list-default.png
 *   04-filter-agent-only.png
 *   05-detail-modal.png
 *   06-export-clicked.png
 *   07-redaction-verified.png  + redaction-payload.json
 *   export.xlsx
 *
 * 任何一步失败 → 进程非 0 退出码 + 失败步骤截图（可能不完整）。
 */

import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execSync } from 'node:child_process'

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(SCRIPT_DIR, '..', '..', '..')
const OUT_DIR = resolve(REPO_ROOT, 'tmp', 'audit-log-e2e')

const BACKEND = process.env.AUDIT_E2E_BACKEND ?? 'http://127.0.0.1:8000'
const FRONTEND = process.env.AUDIT_E2E_FRONTEND ?? 'http://localhost:5173'
const SERVICE_TOKEN = process.env.AUDIT_E2E_TOKEN ?? 'local-dev-only-token-aaaa1111'
const DB_CONTAINER = process.env.AUDIT_E2E_DB_CONTAINER ?? 'edu-ai-home-db-dashboard-local'

mkdirSync(OUT_DIR, { recursive: true })

function log(msg) {
  process.stdout.write(`[audit-e2e] ${msg}\n`)
}

function fail(step, err) {
  process.stderr.write(`[audit-e2e] FAIL @ ${step}: ${err?.stack ?? err}\n`)
  process.exit(1)
}

async function shot(page, file, fullPage = true) {
  const target = resolve(OUT_DIR, file)
  await page.screenshot({ path: target, fullPage })
  log(`screenshot → ${target}`)
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

async function main() {
  // ====== STEP 0: test-login，拿 admin token ======
  log('STEP 0: test-login as 验证管理员 / 99999999')
  const loginUrl = `${BACKEND}/auth/test-login?name=${encodeURIComponent('验证管理员')}&zju_id=99999999`
  const { res: loginRes, body: loginBody } = await fetchJson(loginUrl, { method: 'POST' })
  assert(loginRes.ok, `test-login HTTP ${loginRes.status}`)
  const token = loginBody?.data
  assert(typeof token === 'string' && token.length > 0, 'test-login did not return a token')
  log(`got token ${token.slice(0, 12)}...`)

  // ====== Playwright ======
  const browser = await chromium.launch({ headless: true })
  const ctx = await browser.newContext({
    userAgent: 'PlaywrightAuditE2E/1.0',
    viewport: { width: 1440, height: 900 },
  })
  // 写 localStorage.auth_token 跳过 OAuth
  await ctx.addInitScript((injectedToken) => {
    try {
      window.localStorage.setItem('auth_token', injectedToken)
      window.localStorage.setItem('auth_token_set_at', String(Date.now()))
    } catch {}
  }, token)

  const page = await ctx.newPage()

  // ====== STEP 1: 进 admin/dashboard，确认审计日志侧栏入口 ======
  try {
    log('STEP 1: dashboard baseline')
    await page.goto(`${FRONTEND}/admin/dashboard`, { waitUntil: 'networkidle' })
    await page.waitForSelector('text=数据驾驶舱', { timeout: 10000 })
    await page.waitForSelector('text=审计日志', { timeout: 5000 })
    await shot(page, '01-dashboard-with-audit-nav.png')
  } catch (e) {
    await shot(page, '01-dashboard-with-audit-nav-FAILED.png').catch(() => {})
    fail('STEP 1', e)
  }

  // ====== STEP 2: 触发一次 admin 写操作（toggle 第一个 agent） ======
  try {
    log('STEP 2: toggle first agent → admin write')
    await page.goto(`${FRONTEND}/admin/agents`, { waitUntil: 'networkidle' })
    await page.waitForSelector('table tbody tr', { timeout: 10000 })
    // AdminAgentsView 的上下架开关：每行有 <label class="toggle"><input type="checkbox" ...></label>
    // checkbox 用 CSS 隐藏，点击 label 才能正确触发原生 change 事件
    const toggleLabel = page.locator('table tbody tr label.toggle').first()
    await toggleLabel.click()
    // 等 onToggle 完成（POST /admin/agents/toggle），UI 上 togglingId 变化反映状态
    await page.waitForTimeout(1200)
    await shot(page, '02-agent-toggled.png')
  } catch (e) {
    await shot(page, '02-agent-toggled-FAILED.png').catch(() => {})
    fail('STEP 2', e)
  }

  // ====== STEP 3: 直接以 X-Audit-Service-Token 调 /audit/report ======
  try {
    log('STEP 3: POST /audit/report (agent)')
    const { res } = await fetchJson(`${BACKEND}/audit/report`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Audit-Service-Token': SERVICE_TOKEN,
      },
      body: JSON.stringify({
        actor_id: 'essay_check',
        actor_label: '论文检测服务',
        action: 'essay_check.delete',
        target_type: 'essay_task',
        target_id: 'demo-paper-001',
        target_label: '示例论文.docx',
        result: 'success',
      }),
    })
    assert(res.ok, `agent report HTTP ${res.status}`)
  } catch (e) {
    fail('STEP 3', e)
  }

  // ====== STEP 4: /admin/audit-logs 默认列表 ======
  try {
    log('STEP 4: visit /admin/audit-logs default list')
    await page.goto(`${FRONTEND}/admin/audit-logs`, { waitUntil: 'networkidle' })
    await page.waitForSelector('text=审计日志', { timeout: 8000 })
    // 默认应该有至少 2 行（admin toggle + agent report）
    await page.waitForSelector('table tbody tr', { timeout: 8000 })
    const rowCount = await page.locator('table tbody tr').count()
    assert(rowCount >= 2, `expected ≥2 rows, got ${rowCount}`)
    await shot(page, '03-audit-list-default.png')
  } catch (e) {
    await shot(page, '03-audit-list-default-FAILED.png').catch(() => {})
    fail('STEP 4', e)
  }

  // ====== STEP 5: 筛选 actor_type=agent ======
  try {
    log('STEP 5: filter actor_type=agent')
    // 第一个 .filter-select 即 actor_type 下拉
    const select = page.locator('select.filter-select').first()
    await select.selectOption('agent')
    await page.locator('button.btn-secondary:has-text("查询")').click()
    await page.waitForTimeout(1000)
    const visibleRows = await page.locator('table tbody tr').count()
    assert(visibleRows >= 1, 'expected ≥1 agent row after filter')
    // 校验 actor_type 列内容都是 agent
    const badges = await page.locator('table tbody tr .badge-agent').count()
    assert(badges === visibleRows, `expected all rows badge-agent, got ${badges}/${visibleRows}`)
    await shot(page, '04-filter-agent-only.png')
  } catch (e) {
    await shot(page, '04-filter-agent-only-FAILED.png').catch(() => {})
    fail('STEP 5', e)
  }

  // ====== STEP 6: 详情 modal ======
  try {
    log('STEP 6: open detail modal')
    await page.locator('table tbody tr .link-btn:has-text("详情")').first().click()
    await page.waitForSelector('.audit-modal', { timeout: 5000 })
    // 校验 modal 里能看到 essay_check + 示例论文.docx
    const modalText = await page.locator('.audit-modal').textContent()
    assert(modalText?.includes('essay_check'), 'modal missing essay_check actor_id')
    assert(modalText?.includes('示例论文.docx'), 'modal missing target_label')
    await shot(page, '05-detail-modal.png')
    await page.locator('.audit-modal-close').click()
    await page.waitForTimeout(300)
  } catch (e) {
    await shot(page, '05-detail-modal-FAILED.png').catch(() => {})
    fail('STEP 6', e)
  }

  // ====== STEP 7: 清空筛选 → 导出 Excel ======
  try {
    log('STEP 7: clear filters + export xlsx')
    await page.locator('button.btn-secondary:has-text("重置")').click()
    await page.waitForTimeout(800)
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 10000 }),
      page.locator('button.btn-primary:has-text("导出")').click(),
    ])
    const suggested = download.suggestedFilename()
    assert(
      /^审计日志_\d{8,}.*\.xlsx$/.test(suggested),
      `unexpected download name: ${suggested}`,
    )
    const exportPath = resolve(OUT_DIR, 'export.xlsx')
    await download.saveAs(exportPath)
    log(`download → ${exportPath}`)
    await shot(page, '06-export-clicked.png')
  } catch (e) {
    await shot(page, '06-export-clicked-FAILED.png').catch(() => {})
    fail('STEP 7', e)
  }

  // ====== STEP 8: 脱敏 + 截断 + 幂等 三件套验证 ======
  try {
    log('STEP 8: redaction + truncation + idempotency')

    // 8a) 小 payload，验证 PII 关键字递归脱敏（不会触发截断）
    const idemKeyRedact = `e2e-redact-${Date.now()}`
    let rsp = await fetch(`${BACKEND}/audit/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Audit-Service-Token': SERVICE_TOKEN },
      body: JSON.stringify({
        actor_id: 'e2e-redaction-tester',
        actor_label: 'E2E 脱敏验证',
        action: 'e2e.redaction_check',
        idempotency_key: idemKeyRedact,
        payload: {
          password: 'p@ssw0rd',
          nested: { api_key: 'sk-secret-xyz', ok: 'visible' },
          plain: 'visible-too',
        },
      }),
    })
    assert(rsp.ok, `redact-small HTTP ${rsp.status}`)

    // 8b) 大 payload，验证 8KiB 截断
    const idemKeyTrunc = `e2e-truncate-${Date.now()}`
    rsp = await fetch(`${BACKEND}/audit/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Audit-Service-Token': SERVICE_TOKEN },
      body: JSON.stringify({
        actor_id: 'e2e-redaction-tester',
        action: 'e2e.truncate_check',
        idempotency_key: idemKeyTrunc,
        payload: { password: 'p@ssw0rd', big: 'x'.repeat(9 * 1024) },
      }),
    })
    assert(rsp.ok, `truncate-large HTTP ${rsp.status}`)

    // 8c) 幂等：相同 (actor_type=agent, idempotency_key) 再发一次，仍 200 但 DB 不增行
    rsp = await fetch(`${BACKEND}/audit/report`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Audit-Service-Token': SERVICE_TOKEN },
      body: JSON.stringify({
        actor_id: 'e2e-redaction-tester',
        action: 'e2e.redaction_check',
        idempotency_key: idemKeyRedact,
      }),
    })
    assert(rsp.ok, `idempotent retry HTTP ${rsp.status}`)

    function psql(sql) {
      const cmd = `docker exec -i ${DB_CONTAINER} psql -U postgres -d edu_ai_home -At -c "${sql.replace(/"/g, '\\"')}"`
      try {
        return execSync(cmd, { encoding: 'utf-8' }).trim()
      } catch (e) {
        throw new Error(`psql exec failed: ${e?.message ?? e}\n(cmd: ${cmd})`)
      }
    }

    // —— 验证 8a: redaction 命中且不触发截断 ——
    const redactRows = psql(
      `SELECT payload::text FROM audit_logs WHERE idempotency_key='${idemKeyRedact}' AND actor_type='agent';`,
    ).split(/\r?\n/).filter(Boolean)
    assert(redactRows.length === 1, `redact row count=${redactRows.length} (期望幂等去重后只有 1)`)
    const redactPayload = JSON.parse(redactRows[0])
    log(`redact payload from DB: ${JSON.stringify(redactPayload).slice(0, 200)}`)
    assert(redactPayload.password === '***', `password not redacted: ${redactPayload.password}`)
    assert(
      redactPayload.nested?.api_key === '***',
      `nested.api_key not redacted: ${redactPayload.nested?.api_key}`,
    )
    assert(redactPayload.nested?.ok === 'visible', 'non-sensitive nested key was unexpectedly redacted')
    assert(redactPayload.plain === 'visible-too', 'non-sensitive top-level key was unexpectedly redacted')
    assert(redactPayload._truncated !== true, 'small payload should NOT be truncated')

    // —— 验证 8b: 大 payload 触发截断 ——
    const truncRows = psql(
      `SELECT payload::text FROM audit_logs WHERE idempotency_key='${idemKeyTrunc}' AND actor_type='agent';`,
    ).split(/\r?\n/).filter(Boolean)
    assert(truncRows.length === 1, `truncate row count=${truncRows.length}`)
    const truncPayload = JSON.parse(truncRows[0])
    log(`truncate payload from DB: ${JSON.stringify(truncPayload).slice(0, 200)}...`)
    assert(truncPayload._truncated === true, `expected _truncated=true on big payload, got: ${JSON.stringify(truncPayload).slice(0, 200)}`)
    assert(typeof truncPayload._size === 'number' && truncPayload._size > 8 * 1024, 'expected _size > 8KiB')
    assert(typeof truncPayload._preview === 'string', 'expected _preview string')
    // 截断的预览里也应该含有脱敏后的 "***"
    assert(truncPayload._preview.includes('"password": "***"'), 'expected redacted password to appear in _preview')

    writeFileSync(
      resolve(OUT_DIR, 'redaction-payload.json'),
      JSON.stringify({ redact: redactPayload, truncate: truncPayload }, null, 2),
      'utf-8',
    )

    // 截一张审计日志页面快照固化结果
    await page.goto(`${FRONTEND}/admin/audit-logs?actor_id=e2e-redaction-tester`, {
      waitUntil: 'networkidle',
    })
    await page.waitForTimeout(800)
    await shot(page, '07-redaction-verified.png')
    log('STEP 8 OK: redaction + truncation + idempotency all pass')
  } catch (e) {
    await shot(page, '07-redaction-verified-FAILED.png').catch(() => {})
    fail('STEP 8', e)
  }

  await ctx.close()
  await browser.close()

  log('ALL STEPS PASSED ✓')
  log(`产物目录: ${OUT_DIR}`)
}

main().catch((e) => {
  process.stderr.write(`[audit-e2e] uncaught: ${e?.stack ?? e}\n`)
  process.exit(1)
})
