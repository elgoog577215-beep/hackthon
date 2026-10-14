import { t } from '../shared/i18n'
import type { TeacherLessonJob, TeacherLessonScriptState } from '../stores/teacherLessonAuthoring'
import { teacherFacingTeachingLabel } from './teaching-terminology'

// A saved stale handout remains readable, but is not a current source for PPT.
export function hasRetainedStaleScript(script?: TeacherLessonScriptState): boolean {
  return Boolean(
    script?.source_state === 'stale'
    && script.current_revision_id
    && script.sections?.some(section => (
      section.content?.trim() || section.blocks?.some(block => block.content?.trim())
    )),
  )
}

export function hasScriptPreviewContent(job?: TeacherLessonJob): boolean {
  return Boolean(
    job?.result_sections?.some(section => section.content?.trim() || section.blocks?.some(block => block.content?.trim()))
    || Object.values(job?.streamed_block_content || {}).some(content => content.trim()),
  )
}

export function scriptFailurePresentation(job?: TeacherLessonJob) {
  if (job?.status !== 'failed') return null
  const text = `${job.error?.code || ''} ${job.error?.message || ''}`.toLowerCase()
  const category = job.error?.category || ''
  const say = (key: string, fallback: string) => t(`courseWorkbench.scriptFailure.${key}`, fallback)
  const completed = Math.max(0, Number(job.completed_blocks) || 0)
  const total = Math.max(completed, Number(job.total_blocks) || 0)
  const hasFragment = hasScriptPreviewContent(job) || Boolean(job.unassigned_fragment?.trim())
  const retained = completed > 0
    ? say('savedParts', '已保留 {completed}/{total} 个完整部分。').replace('{completed}', String(completed)).replace('{total}', String(total))
    : hasFragment
      ? say('savedFragment', '已保留收到的正文片段，但还没有完整的小节。')
      : say('noContent', '本次尚未生成可保存的正文。已有讲义不会被覆盖。')
  const attempts = Number.isFinite(Number(job.attempt_number)) ? Math.max(1, Math.trunc(Number(job.attempt_number))) : 1
  const repeated = attempts > 1 ? say('attempts', '这个任务已尝试 {count} 次。').replace('{count}', String(attempts)) : ''
  let reason: string
  let actions: string[]
  let canReviewPlan = false
  if (category === 'conflict' || /source_changed|revision_changed|scope_stale/.test(text)) {
    reason = say('sourceChanged', '本讲教案或参考资料已变化，原生成任务不能继续使用旧内容。')
    actions = [say('useLatest', '先确认最新教案和资料，再选择重新生成；不要继续旧任务。')]
    canReviewPlan = true
  } else if (category === 'storage') {
    reason = say('saveFailure', '讲义内容未能保存，问题出在保存服务，不是教学要求。')
    actions = [say('saveAction', '先保留当前页面，联系维护人员检查保存服务和磁盘空间；不要立即重新生成整讲。')]
  } else if (category === 'missing_input') {
    reason = say('missingInput', '本讲教案或参考资料尚未准备完整，无法确定讲义生成依据。')
    actions = [say('missingAction', '检查本讲教案是否已保存，补充教学目标、内容范围和必要参考资料后，再重新生成。')]
    canReviewPlan = true
  } else if (/\b401\b|\b403\b|unauthorized|invalid.*api.?key|provider_auth/.test(text)) {
    reason = say('authorization', 'AI 生成服务的访问授权不可用。')
    actions = [say('authorizationAction', '请联系维护人员检查生成服务的授权配置；修改教案不能解决这个问题。')]
  } else if (/\b429\b|rate.?limit|quota|额度/.test(text)) {
    reason = say('capacity', 'AI 生成服务当前限制了请求次数，或可用额度不足。')
    actions = [say('capacityAction', '稍后再试；如果持续出现，请联系维护人员检查服务容量和额度。无需反复修改教案。')]
  } else if (/timeout|超时|没有内容输出|没有新内容/.test(text)) {
    const seconds = text.match(/(?:连续|超过|等待)\s*(\d{1,4})\s*秒/)
    reason = seconds
      ? say('timeoutSeconds', 'AI 生成服务连续 {seconds} 秒没有返回新的讲义正文，本次生成已停止。').replace('{seconds}', seconds[1]!)
      : say('timeout', '等待 AI 生成服务返回正文的时间过长，本次生成已停止。')
    actions = [say('retry', '可以稍后点“继续”按原条件重试；这不会自动缩小本讲范围。')]
    if (attempts > 1) {
      actions.unshift(say('avoidRepeat', '相同条件已经失败多次，不建议连续重复点击“继续”。'))
      actions.push(say('reduceScope', '如果本讲同时包含多个主题或长代码示例，可先调整教案，缩小本讲范围，再选择重新生成。这是可尝试的调整，不代表已确认教案有错。'))
      canReviewPlan = true
    }
    actions.push(say('serviceUnknown', '目前只能确认没有收到正文，无法仅凭这次失败判断是服务繁忙还是输入处理过慢；持续失败请联系维护人员。'))
  } else if (category === 'structure' || /json|parse|schema|output_incomplete|shard_invalid|block_empty|truncated/.test(text)) {
    reason = say('structure', 'AI 返回的讲义结构不完整，尚不能保存为完整讲义。')
    actions = [say('structureAction', '点“继续”补齐未完成部分；若同一问题反复出现，请联系维护人员检查生成格式，不要反复修改正常的教学内容。')]
  } else if (category === 'provider' || /connect|service_unavailable|\b50[234]\b/.test(text)) {
    reason = say('service', 'AI 生成服务连接中断或暂时无法响应，本次讲义没有完成。')
    actions = [say('serviceAction', '稍后按原条件继续；若仍失败，请联系维护人员检查服务连接。当前没有证据表明需要修改教案。')]
  } else if (category === 'quality') {
    reason = say('saveRequirements', '生成结果未满足讲义保存要求，当前还不能作为完整讲义使用。')
    actions = [say('requirementsAction', '查看本讲教案与参考资料是否完整；若无法确定缺失原因，请联系维护人员检查此次任务，不要盲目重复生成。')]
    canReviewPlan = true
  } else {
    reason = say('unknown', '讲义处理过程中出现系统异常，暂时无法确定具体原因。')
    actions = [say('unknownAction', '请联系维护人员检查此次失败记录。不要反复点击生成，也不需要根据内部错误修改教学内容。')]
  }
  return { reason, retained, repeated, actions, canReviewPlan }
}

// Job messages describe scheduling and shard internals. Keep the reading UI
// tied to the real phase without publishing those implementation details.
export function scriptGenerationPresentation(job?: TeacherLessonJob) {
  const phase = String(job?.phase || '')
  if (job?.status === 'failed' || job?.status === 'paused') {
    const failure = scriptFailurePresentation(job)
    return {
      title: t(`courseWorkbench.scriptDocument.progress.${job.status}Title`),
      detail: failure ? [failure.reason, failure.repeated, failure.retained].filter(Boolean).join(' ') : job.total_blocks ? t('courseWorkbench.scriptDocument.progress.retainedDetail')
        .replace('{completed}', String(job.completed_blocks || 0))
        .replace('{total}', String(job.total_blocks)) : '',
    }
  }
  const state = job?.status === 'pending' || phase === 'queued'
    ? 'preparing'
    : ['lesson_script_block_repair', 'lesson_script_auto_improvement'].includes(phase)
      ? 'improving'
      : 'writing'
  return {
    title: t(`courseWorkbench.scriptDocument.progress.${state}Title`),
    detail: t(`courseWorkbench.scriptDocument.progress.${state}Detail`),
  }
}

export function readableScriptTitle(value: unknown, internalIds: string[] = [], moduleId = ''): string {
  const title = String(value || '').trim()
  if (!title || internalIds.includes(title) || /^tsb-[a-f\d]+$/i.test(title)) return ''
  return teacherFacingTeachingLabel(title, moduleId)
}
