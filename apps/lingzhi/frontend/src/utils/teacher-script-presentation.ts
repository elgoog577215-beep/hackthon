import { t } from '../shared/i18n'
import type { TeacherLessonJob } from '../stores/teacherLessonAuthoring'

export function hasScriptPreviewContent(job?: TeacherLessonJob): boolean {
  return Boolean(
    job?.result_sections?.some(section => section.content?.trim() || section.blocks?.some(block => block.content?.trim()))
    || Object.values(job?.streamed_block_content || {}).some(content => content.trim()),
  )
}

// Job messages describe scheduling and shard internals. Keep the reading UI
// tied to the real phase without publishing those implementation details.
export function scriptGenerationPresentation(job?: TeacherLessonJob) {
  const phase = String(job?.phase || '')
  const state = job?.status === 'pending' || phase === 'queued'
    ? 'preparing'
    : ['lesson_script_block_repair', 'lesson_script_auto_improvement'].includes(phase)
      ? 'improving'
      : 'writing'
  return {
    title: t(`courseWorkbench.scriptDocument.progress.${state}Title`),
    detail: t(`courseWorkbench.scriptDocument.progress.${phase === 'lesson_script_block_failed' ? 'partialFailure' : state}Detail`),
  }
}

export function readableScriptTitle(value: unknown, internalIds: string[] = []): string {
  const title = String(value || '').trim()
  if (!title || internalIds.includes(title) || /^tsb-[a-f\d]+$/i.test(title)) return ''
  return title
}
