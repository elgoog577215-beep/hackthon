/**
 * Observable record of Markdown/KaTeX render failures.
 *
 * Both render fallbacks used to swallow their failure: `renderMathContent`
 * catches a KaTeX error and returns `<code class="math-fallback">` with the raw
 * source, and a whole-block failure falls back to `DOMPurify.sanitize(raw)`.
 * Neither throws, logs, or reports — so a course full of broken formulas looks
 * to every automated check like a course that merely has ugly typography, and
 * the publication gate never learns anything went wrong.
 *
 * This module is the signal those paths were missing. It deliberately does not
 * change what the user sees: degrading to readable source is still better than
 * a blank page. It only makes the degradation *countable*, so L3b can turn the
 * count into a release blocker and L3e can score it as a render defect rather
 * than a content defect.
 */

export type RenderFailureKind = 'math' | 'block'

export interface RenderFailure {
  kind: RenderFailureKind
  /** Trimmed source that failed, bounded so a runaway block cannot flood memory. */
  source: string
  /** Error text when the renderer produced one. */
  detail: string
  /** Caller-supplied origin, e.g. a course block id. Empty when rendering ad-hoc text. */
  contextId: string
}

const MAX_RECORDED = 200
const MAX_SOURCE_CHARS = 400

let failures: RenderFailure[] = []
let listeners: Array<(failure: RenderFailure) => void> = []
let activeContextId = ''

/**
 * Tag subsequent renders with the content they belong to.
 *
 * Rendering is synchronous, so a simple ambient value is enough to attribute a
 * failure to a block without threading an argument through markdown-it's
 * plugin callbacks.
 */
export function withRenderContext<T>(contextId: string, run: () => T): T {
  const previous = activeContextId
  activeContextId = contextId
  try {
    return run()
  } finally {
    activeContextId = previous
  }
}

export function recordRenderFailure(
  kind: RenderFailureKind,
  source: string,
  detail: unknown = '',
): void {
  const rawDetail = detail instanceof Error ? detail.message : String(detail || '')
  const failure: RenderFailure = {
    kind,
    source: String(source || '').trim().slice(0, MAX_SOURCE_CHARS),
    detail: rawDetail.slice(0, MAX_SOURCE_CHARS),
    contextId: activeContextId,
  }
  // Keep the newest records: the tail of a long run is what a reporter needs.
  failures.push(failure)
  if (failures.length > MAX_RECORDED) failures = failures.slice(-MAX_RECORDED)
  for (const listener of listeners) {
    try {
      listener(failure)
    } catch {
      // A broken reporter must never break rendering.
    }
  }
}

/** Every failure recorded since the last reset. */
export function renderFailures(): RenderFailure[] {
  return failures.slice()
}

/** How many renders degraded, optionally for one piece of content. */
export function renderFailureCount(contextId?: string): number {
  if (contextId === undefined) return failures.length
  return failures.filter(item => item.contextId === contextId).length
}

/** Subscribe a reporter. Returns an unsubscribe function. */
export function onRenderFailure(listener: (failure: RenderFailure) => void): () => void {
  listeners.push(listener)
  return () => {
    listeners = listeners.filter(item => item !== listener)
  }
}

export function resetRenderFailures(): void {
  failures = []
}

/** Test seam: drop subscribers so one suite cannot leak into the next. */
export function resetRenderFailureListeners(): void {
  listeners = []
}
