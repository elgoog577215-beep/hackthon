// UI contract test with explicitly synthetic API responses, not model/production evidence.
// BASE_URL=http://127.0.0.1:5192 PLAYWRIGHT_MODULE=<optional module path> node e2e/reading-companion.cjs
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright')
const fs = require('node:fs')
const path = require('node:path')
const assert = require('node:assert/strict')
const output = process.env.ARTIFACT_DIR || path.resolve('test-results/reading-companion')
fs.mkdirSync(output, { recursive: true })
const baseURL = process.env.BASE_URL || 'http://127.0.0.1:5192'
const fixture = {
  id: 'companion-ui-fixture', title: '隔离验收 · 复合函数求导', purpose: 'systematic', status: 'completed',
  task_id: 'fixture-task', updated_at: '', plans: [], sources: [], notes: {},
  task: { id: 'fixture-task', status: 'completed', progress: 100 },
  revisions: [{ id: 'fixture-revision', status: 'completed', sections: [{
    id: 'section-1', title: '复合函数求导', complete: true, fragment: '',
    source: { filename: '明确合成的验收材料.md', asset_id: 'fixture-source', source_sha256: 'synthetic' },
    blocks: [{ block_id: 'block-1', content_type: 'explanation', type_label: '讲解', title: '内层与外层',
      content: '对复合函数 $y=(3x+1)^2$ 求导时，先识别内层与外层，再将两部分的导数相乘。', knowledge_names: [], answer_to: '' }],
  }] }],
}

async function main() {
  const browser = await chromium.launch({ channel: process.env.BROWSER_CHANNEL || 'msedge', headless: true })
  const results = []
  try {
    for (const language of ['zh', 'en']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } })
      const page = await context.newPage(), errors = []
      let posts = 0, reads = 0, completeAnswer
      let conversation = { conversation_id: 'fixture-conversation', messages: [] }
      page.on('pageerror', error => errors.push(error.message))
      await page.addInitScript(locale => {
        sessionStorage.setItem('lingzhi_student_session_v1', 'synthetic-ui-session')
        localStorage.setItem('app-locale', locale)
      }, language)
      await page.route('**/api/**', async route => {
        const request = route.request(), pathname = new URL(request.url()).pathname
        if (!pathname.startsWith('/api/')) return route.continue()
        let data
        if (pathname === '/api/study/auth/config') data = { local_login_enabled: true }
        else if (pathname === '/api/study/auth/me') data = { id: 'fixture-student', username: 'synthetic_student', role: 'student' }
        else if (pathname === '/api/study/materials') data = [fixture]
        else if (pathname === '/api/study/sources' || pathname === '/api/study/courses') data = []
        else if (pathname === '/api/study/materials/companion-ui-fixture') data = fixture
        else if (pathname.endsWith('/assistant')) {
          if (request.method() === 'POST') {
            posts++
            const body = request.postDataJSON()
            assert.equal(body.block_id, 'block-1'); assert.equal(body.revision_id, 'fixture-revision')
            await new Promise(resolve => { completeAnswer = resolve })
            conversation = { ...conversation, messages: [
              { message_id: 'u1', role: 'user', content: body.text, status: 'complete', context_ref: body },
              { message_id: 'a1', role: 'assistant', content: '合成回复：内层函数为 $3x+1$，其导数为 $3$。'.repeat(40), status: 'complete', context_ref: body },
            ] }
          } else reads++
          data = conversation
        } else if (pathname === '/api/usage-events') data = {}
        else throw new Error(`Unexpected synthetic API request: ${request.method()} ${pathname}`)
        await route.fulfill({ json: data })
      })
      await page.goto(`${baseURL}/study/companion-ui-fixture`)
      await page.getByTestId('personal-block-help').click()
      const inline = page.locator('[data-study-companion-anchor] .reading-companion-surface')
      await inline.waitFor({ state: 'visible' })
      await inline.locator('textarea').fill('为什么还要乘以内层导数？')
      const sent = page.waitForRequest(r => r.method() === 'POST' && new URL(r.url()).pathname.endsWith('/assistant'))
      await inline.locator('form').evaluate(form => form.requestSubmit())
      await sent
      await inline.locator('textarea').fill('保留这条尚未发送的追问')
      while(!completeAnswer)await page.waitForTimeout(10)
      completeAnswer()
      await page.getByTestId('companion-expand').click()
      const full = page.locator('.study-reading-tools .personal-assistant')
      await full.waitFor({ state: 'visible' })
      assert.equal(await full.locator('textarea').inputValue(), '保留这条尚未发送的追问')
      await full.getByText('合成回复：', { exact: false }).waitFor()
      assert.equal(await full.locator('textarea').inputValue(), '保留这条尚未发送的追问')
      await page.getByTestId('companion-return-inline').click()
      await inline.waitFor({ state: 'visible' })
      assert.equal(await inline.locator('.reading-companion-toolbar,.reading-companion-more').count(),0)
      assert.equal(await inline.locator('textarea').inputValue(), '保留这条尚未发送的追问')
      assert.equal(posts, 1); assert.equal(reads, 2)
      assert.deepEqual(errors, [])
      await page.screenshot({ path: path.join(output, `inline-${language}.png`), fullPage: true })
      results.push({ language, posts, reads, draft_preserved: true, synthetic_response: true, errors })
      await context.close()
    }
    fs.writeFileSync(path.join(output, 'result.json'), JSON.stringify(results, null, 2))
    console.log(JSON.stringify(results))
  } finally { await browser.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
