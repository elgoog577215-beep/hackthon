/** Print a snapshot of the selected handout, including answers, without changing
 * the live disclosure state or printing the application navigation. */
export function buildHandoutPrintBody(source: HTMLElement, title: string): HTMLElement {
  const body = document.createElement('main')
  body.className = 'handout-document handout-print-document'
  const heading = document.createElement('h1')
  heading.textContent = title
  if (title) body.append(heading)
  const content = source.cloneNode(true) as HTMLElement
  content.querySelectorAll('[data-handout-print-exclude], button, textarea, .stream-caret, .stream-cursor').forEach(node => node.remove())
  content.querySelectorAll('details').forEach(node => { node.open = true })
  body.append(content)
  return body
}

export async function printHandoutDocument(source: HTMLElement, title: string): Promise<void> {
  const frame = document.createElement('iframe')
  frame.title = title
  frame.style.cssText = 'position:fixed;width:0;height:0;border:0;bottom:0;left:0;'
  frame.setAttribute('aria-hidden', 'true')
  document.body.append(frame)
  const target = frame.contentDocument
  if (!target || !frame.contentWindow) { frame.remove(); return }
  target.title = title
  const base = target.createElement('base')
  base.href = document.baseURI
  target.head.append(base)
  const stylesReady: Promise<void>[] = []
  document.querySelectorAll('style, link[rel="stylesheet"]').forEach(node => {
    const copy = node.cloneNode(true) as HTMLElement
    if (copy instanceof HTMLLinkElement) stylesReady.push(new Promise(resolve => { copy.onload = () => resolve(); copy.onerror = () => resolve() }))
    target.head.append(copy)
  })
  const style = target.createElement('style')
  style.textContent = `
    @page { margin: 18mm; }
    html,body{margin:0;background:#fff;color:#000;height:auto;overflow:visible}
    .handout-print-document{padding:0}
    .handout-print-document h1{font:700 24pt/1.4 var(--handout-serif);margin:0 0 24pt}
    .handout-print-document :is(.script-document,.script-continuous,.preview-section,.script-body){width:100%;max-width:none;padding:0;margin:0;border:0;box-shadow:none;min-height:0;overflow:visible}
    .handout-print-document .script-body>header{padding-top:24pt;margin-bottom:18pt;break-after:avoid}
    .handout-print-document .course-content-block{margin:0;padding:0;border:0}
    .handout-print-document .handout-block{break-inside:avoid;print-color-adjust:exact;-webkit-print-color-adjust:exact}
    .handout-print-document details>summary{margin-bottom:12pt}
  `
  target.head.append(style)
  target.body.append(buildHandoutPrintBody(source, title))
  await Promise.race([Promise.all(stylesReady), new Promise(resolve => setTimeout(resolve, 3000))])
  // Force font discovery before waiting; source images and font loading have a
  // bounded wait so an unavailable image cannot leave the print action busy.
  target.body.getBoundingClientRect()
  await Promise.race([
    Promise.all([target.fonts?.ready, ...Array.from(target.images).map(image => image.complete ? Promise.resolve() : new Promise<void>(resolve => { image.onload = () => resolve(); image.onerror = () => resolve() }))]),
    new Promise(resolve => setTimeout(resolve, 3000)),
  ])
  frame.contentWindow.addEventListener('afterprint', () => frame.remove(), { once: true })
  try { frame.contentWindow.print() }
  catch (error) { frame.remove(); throw error }
  setTimeout(() => frame.remove(), 120000)
}
