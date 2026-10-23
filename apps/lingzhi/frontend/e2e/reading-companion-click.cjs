// Real local source fixture. No production course or student data is used.
// Set BASE_URL, SESSION_FILE, ARTIFACT_DIR and PLAYWRIGHT_MODULE for an isolated run.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright')
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict')
;(async()=>{
 const browser=await chromium.launch({channel:'msedge',headless:true})
 try {
  const context=await browser.newContext({viewport:{width:1440,height:1000}})
  const page=await context.newPage()
  await page.goto(process.env.BASE_URL)
  await page.evaluate(({token,user})=>{sessionStorage.setItem('lingzhi_student_session_v1',token);sessionStorage.setItem('lingzhi_student_identity_v1',JSON.stringify(user))},JSON.parse(fs.readFileSync(process.env.SESSION_FILE,'utf8')))
  await page.goto(process.env.BASE_URL+'/course/pilot-course/learn/pilot-n')
  const paragraph=page.locator('.course-content-block p').first();await paragraph.waitFor();await page.waitForTimeout(1200)
  await paragraph.evaluate(el=>{const range=document.createRange();const walker=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let text;while(text=walker.nextNode()){if(text.textContent.trim().length>8)break}range.setStart(text,0);range.setEnd(text,8);const selection=getSelection();selection.removeAllRanges();selection.addRange(range);el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}))})
  await page.locator('#selection-menu').waitFor();await page.waitForTimeout(300)
  assert.equal(await page.locator('.reading-companion-surface.is-inline:visible').count(),0,'Selecting text must not open the companion')
  console.log('Selection leaves the companion closed: passed')
 } finally {await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1})
