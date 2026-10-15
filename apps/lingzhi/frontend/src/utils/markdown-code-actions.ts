type RunState = {
  code: HTMLElement; language: string; button: HTMLButtonElement; result: HTMLElement
  phase: 'idle' | 'running' | 'done' | 'failed'; output: string; request?: AbortController
}
type CopyState = { phase: 'idle' | 'copying' | 'copied' | 'failed'; timer?: ReturnType<typeof setTimeout> }
export class MarkdownCodeExecutionError extends Error {}
type Options = {
  tr: (zh: string, en: string) => string
  execute: (code: string, language: string, signal: AbortSignal) => Promise<string>
  notify: (message: string, error: boolean) => void
}

export const markdownCodeLanguage = (code: HTMLElement) => {
  const raw = (code.closest<HTMLElement>('[data-lang]')?.dataset.lang
    || Array.from(code.classList).find(name => name.startsWith('language-'))?.slice(9)
    || '').toLowerCase()
  if (raw === 'python' || raw === 'py') return 'python'
  if (raw === 'javascript' || raw === 'js') return 'javascript'
  return ''
}

export function createMarkdownCodeActions(root: HTMLElement, options: Options) {
  const runs = new Map<HTMLButtonElement, RunState>()
  const copies = new Map<HTMLButtonElement, CopyState>()
  let enabled = false, disposed = false
  const { tr } = options

  function copyLabel(button: HTMLButtonElement, state: CopyState) {
    button.textContent = state.phase === 'copied' ? tr('已复制', 'Copied')
      : state.phase === 'copying' ? tr('复制中…', 'Copying…')
      : state.phase === 'failed' ? tr('重试复制', 'Retry copy') : tr('复制', 'Copy')
    button.title = tr('复制代码', 'Copy code')
    button.disabled = state.phase === 'copying'
  }

  function runLabel(state: RunState) {
    state.button.textContent = state.phase === 'running' ? tr('运行中…', 'Running…') : tr('运行', 'Run')
    state.button.title = tr(`运行 ${state.language} 代码`, `Run ${state.language} code`)
    state.button.disabled = state.phase === 'running'
    state.result.textContent = state.phase === 'running' ? tr('运行中…', 'Running…')
      : state.phase === 'failed' ? [tr('运行失败', 'Execution failed'), state.output].filter(Boolean).join('\n')
      : state.phase === 'done' ? (state.output || tr('无输出', 'No output')) : ''
  }

  function refresh() {
    for (const [button, state] of copies) copyLabel(button, state)
    for (const state of runs.values()) runLabel(state)
  }

  function removeRun(state: RunState) {
    state.request?.abort()
    state.button.remove()
    state.result.remove()
    runs.delete(state.button)
  }

  async function click(event: MouseEvent) {
    const target = event.target instanceof Element ? event.target : null
    const copy = target?.closest<HTMLButtonElement>('.copy-btn')
    if (copy && root.contains(copy)) {
      // ContentArea retains a legacy delegated handler for other surfaces.
      // This shared renderer owns its own action exactly once.
      event.stopPropagation()
      event.preventDefault()
      const state = copies.get(copy)
      if (!state || state.phase === 'copying') return
      if (state.timer) clearTimeout(state.timer)
      state.phase = 'copying'; copyLabel(copy, state)
      try {
        const source = copy.dataset.code || ''
        let code = source
        try { code = decodeURIComponent(source) } catch { /* Preserve malformed encoded source. */ }
        await navigator.clipboard.writeText(code)
        if (disposed || !copies.has(copy)) return
        state.phase = 'copied'
        options.notify(tr('代码已复制', 'Code copied'), false)
      } catch {
        if (disposed || !copies.has(copy)) return
        state.phase = 'failed'
        options.notify(tr('复制失败', 'Copy failed'), true)
      }
      copyLabel(copy, state)
      state.timer = setTimeout(() => { state.phase = 'idle'; copyLabel(copy, state) }, 2000)
      return
    }
    const button = target?.closest<HTMLButtonElement>('.code-run-button')
    const state = button ? runs.get(button) : undefined
    if (!button || !state) return
    event.stopPropagation(); event.preventDefault()
    if (!enabled || state.phase === 'running') return
    state.phase = 'running'; state.output = ''; state.result.hidden = false
    const controller = new AbortController()
    state.request = controller
    runLabel(state)
    try {
      const output = await options.execute(state.code.textContent || '', state.language, controller.signal)
      if (disposed || controller.signal.aborted || !runs.has(button)) return
      state.output = output; state.phase = 'done'
    } catch (error) {
      if (disposed || controller.signal.aborted || !runs.has(button)) return
      state.phase = 'failed'
      state.output = error instanceof MarkdownCodeExecutionError ? error.message : ''
      options.notify(tr('代码运行失败', 'Code execution failed'), true)
    }
    runLabel(state)
  }
  root.addEventListener('click', click)

  return {
    enhance(enableCodeRun: boolean) {
      enabled = enableCodeRun
      root.querySelectorAll<HTMLButtonElement>('.copy-btn').forEach(button => {
        if (copies.has(button)) return
        button.type = 'button'
        copies.set(button, { phase: 'idle' })
        button.closest('.code-block-wrapper')?.querySelector('.copy-btn')?.parentElement?.classList.add('markdown-code-tools')
      })
      if (!enabled) for (const state of Array.from(runs.values())) removeRun(state)
      else root.querySelectorAll<HTMLElement>('pre > code').forEach(code => {
        const language = markdownCodeLanguage(code)
        if (!language || code.closest('.mermaid, .teaching-diagram-host')) return
        if (Array.from(runs.values()).some(state => state.code === code)) return
        const pre = code.parentElement!
        const button = document.createElement('button')
        button.type = 'button'; button.className = 'code-run-button'
        const result = document.createElement('pre')
        result.className = 'code-run-result'; result.hidden = true; result.setAttribute('aria-live', 'polite')
        const toolbar = code.closest('.code-block-wrapper')?.querySelector('.markdown-code-tools')
        if (toolbar) toolbar.prepend(button)
        else pre.before(button)
        pre.after(result)
        runs.set(button, { code, language, button, result, phase: 'idle', output: '' })
      })
      refresh()
    },
    refresh,
    remove(node: Node) {
      for (const [button, state] of copies) if (node.contains(button)) {
        if (state.timer) clearTimeout(state.timer)
        copies.delete(button)
      }
      for (const state of Array.from(runs.values())) if (node.contains(state.code)) removeRun(state)
    },
    dispose() {
      disposed = true; root.removeEventListener('click', click)
      for (const state of copies.values()) if (state.timer) clearTimeout(state.timer)
      copies.clear()
      for (const state of Array.from(runs.values())) removeRun(state)
    },
  }
}
