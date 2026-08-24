import { describe, expect, it } from 'vitest'
import {
  assessTeacherLessonRequest,
  buildTeacherLessonAiInstruction,
  changedTeacherLessonFields,
  teacherLessonAiBusy,
  transitionTeacherLessonAiPhase,
  type TeacherLessonAiMessage,
  type TeacherLessonAiPhase,
} from '@/composables/useTeacherLessonAiCollaboration'

describe('教师教案 AI 协作状态机', () => {
  it('覆盖澄清、生成、审阅、采用和失败恢复的合法状态', () => {
    let phase: TeacherLessonAiPhase = 'ready'
    phase = transitionTeacherLessonAiPhase(phase, { type: 'ASK_CLARIFICATION' })
    expect(phase).toBe('clarifying')
    phase = transitionTeacherLessonAiPhase(phase, { type: 'GENERATE' })
    expect(phase).toBe('generating')
    expect(teacherLessonAiBusy(phase)).toBe(true)
    phase = transitionTeacherLessonAiPhase(phase, { type: 'CANDIDATE_READY' })
    expect(phase).toBe('review')
    phase = transitionTeacherLessonAiPhase(phase, { type: 'ACCEPT' })
    expect(phase).toBe('accepting')
    phase = transitionTeacherLessonAiPhase(phase, { type: 'RESOLVED' })
    expect(phase).toBe('success')
    phase = transitionTeacherLessonAiPhase(phase, { type: 'FAIL' })
    expect(phase).toBe('error')
    phase = transitionTeacherLessonAiPhase(phase, { type: 'GENERATE' })
    expect(phase).toBe('generating')
  })

  it('模糊要求先澄清，明确的教学修改直接生成', () => {
    expect(assessTeacherLessonRequest('帮我改好一点')).toBe('clarify')
    expect(assessTeacherLessonRequest('你觉得应该怎么改？')).toBe('clarify')
    expect(assessTeacherLessonRequest('增加课堂互动与形成性检查')).toBe('generate')
    expect(assessTeacherLessonRequest('把教学目标改成学生能独立完成流程图')).toBe('generate')
  })

  it('提示词保留最新要求并约束最小修改与教师确认边界', () => {
    const messages: TeacherLessonAiMessage[] = Array.from({ length: 10 }, (_, index) => ({
      id: String(index), role: 'user', kind: 'text', text: `${index}：${'要求'.repeat(90)}`,
    }))
    const prompt = buildTeacherLessonAiInstruction(messages, {
      courseTitle: '人工智能通识课', lessonTitle: '第一讲', sectionTitle: '1.1 基础概念', referenceCount: 3,
    })
    expect(prompt).toContain('9：')
    expect(prompt).not.toContain('0：')
    expect(prompt).toContain('只修改实现教师要求所必需的字段')
    expect(prompt).toContain('保持原有总时长')
    expect(prompt).toContain('只生成候选，不确认、不发布')
    expect(prompt.length).toBeLessThanOrEqual(1900)
  })

  it('只汇总当前小节真实变化的字段', () => {
    const base = { sections: [{ node_id: 's1', learning_objective: '原目标', homework: ['原作业'], teaching_notes: [] }] }
    const candidate = { sections: [{ node_id: 's1', learning_objective: '新目标', homework: ['原作业'], teaching_notes: ['课前准备'] }] }
    expect(changedTeacherLessonFields(base, candidate, 's1')).toEqual(['learning_objective', 'teaching_notes'])
  })
})
