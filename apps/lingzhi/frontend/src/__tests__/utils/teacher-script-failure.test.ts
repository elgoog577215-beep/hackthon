import { describe, expect, it, vi } from 'vitest'
import type { TeacherLessonJob } from '@/stores/teacherLessonAuthoring'
import { scriptFailurePresentation, scriptGenerationPresentation } from '@/utils/teacher-script-presentation'

vi.mock('@/shared/i18n', () => ({ t: (_key: string, fallback?: string) => fallback || _key }))
const failed = (extra: Partial<TeacherLessonJob> = {}): TeacherLessonJob => ({
  id: 'job', course_id: 'course', lesson_unit_id: 'lecture', type: 'teacher_lesson_script_generation',
  status: 'failed', progress: 5, phase: 'lesson_script_failed', message: 'internal task message', warnings: [],
  total_blocks: 1, completed_blocks: 0, attempt_number: 3,
  error: { code: 'lesson_script_generation_failed', category: 'provider', message: '模型连续 90 秒没有内容输出，已保留收到的片段。' },
  ...extra,
})

describe('plain-language handout failures', () => {
  it('explains repeated first-content timeouts without claiming nonexistent saved text', () => {
    const result = scriptFailurePresentation(failed())!
    expect(result.reason).toContain('90 秒')
    expect(result.reason).toContain('没有返回新的讲义正文')
    expect(result.retained).toContain('尚未生成可保存的正文')
    expect(result.repeated).toContain('3 次')
    expect(result.actions.join(' ')).toContain('相同条件')
    expect(result.actions.join(' ')).toContain('教案')
    expect(result.retained).not.toContain('已保留')
    expect(scriptGenerationPresentation(failed()).detail).not.toContain('internal')
  })
  it('reports real completed parts and partial text separately', () => {
    expect(scriptFailurePresentation(failed({ completed_blocks: 1, total_blocks: 2 }))!.retained).toContain('1/2')
    expect(scriptFailurePresentation(failed({ streamed_block_content: { part: '已经收到的文字' } }))!.retained).toContain('正文片段')
    expect(scriptFailurePresentation(failed({ unassigned_fragment: '还未解析完成的文字' }))!.retained).toContain('正文片段')
  })
  it.each([
    ['storage', 'PermissionError: C:/private/file.json', '保存'],
    ['conflict', 'source_revision_changed qpr_123', '已变化'],
    ['missing_input', 'missing_fields: lesson_plan_revision_id', '教案'],
    ['structure', 'JSONDecodeError at line 18', '结构'],
    ['unknown', 'Traceback: KeyError secret https://internal.example', '系统异常'],
  ])('explains %s without exposing internal strings', (category, message, expected) => {
    const result = scriptFailurePresentation(failed({ error: { code: 'internal_code', category, message } }))!
    const visible = JSON.stringify(result)
    expect(visible).toContain(expected)
    expect(visible).not.toContain(message)
    expect(visible).not.toMatch(/Traceback|KeyError|internal_code|https:\/\/|C:\//)
    expect(result.actions.length).toBeGreaterThan(0)
  })
  it('does not tell users to edit lesson content to resolve service authorization', () => {
    const result = scriptFailurePresentation(failed({ error: { code: 'provider_auth', category: 'provider', message: 'HTTP 401 invalid API key' } }))!
    expect(result.reason).toContain('授权')
    expect(result.actions.join(' ')).toContain('维护人员')
    expect(result.actions.join(' ')).not.toContain('缩小')
  })
  it('does not diagnose pauses or successful jobs as errors', () => {
    expect(scriptFailurePresentation(failed({ status: 'paused' }))).toBeNull()
    expect(scriptFailurePresentation(failed({ status: 'completed' }))).toBeNull()
  })
})
