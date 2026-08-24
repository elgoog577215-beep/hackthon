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
import {
  assessTeacherProductionRequest,
  buildTeacherProductionAiInstruction,
} from '@/composables/useTeacherProductionAiCollaboration'

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

describe('教师课程生产 AI 领域适配', () => {
  it('在共享状态机前使用大纲和讲稿各自的意图边界', () => {
    expect(assessTeacherProductionRequest('outline', '优化一下')).toBe('clarify')
    expect(assessTeacherProductionRequest('outline', '把网络安全章前移到工程实践之前')).toBe('generate')
    expect(assessTeacherProductionRequest('script', '这段不太好')).toBe('clarify')
    expect(assessTeacherProductionRequest('script', '压缩重复表达，加入一个课堂案例')).toBe('generate')
  })

  it('为大纲和讲稿构建不同的后端候选约束', () => {
    const messages = [{ id: '1', role: 'user' as const, kind: 'text' as const, text: '合并两个重复小节' }]
    const outlinePrompt = buildTeacherProductionAiInstruction(messages, {
      domain: 'outline', courseTitle: '测试课程', primaryTitle: '测试课程', secondaryTitle: '课程大纲', referenceCount: 2,
    })
    const scriptPrompt = buildTeacherProductionAiInstruction(messages, {
      domain: 'script', courseTitle: '测试课程', primaryTitle: '第一讲', secondaryTitle: '导入', referenceCount: 1,
    })
    expect(outlinePrompt).toContain('结构调整候选')
    expect(outlinePrompt).toContain('章节增删、顺序')
    expect(scriptPrompt).toContain('表达修改候选')
    expect(scriptPrompt).toContain('保持已确认教案')
    expect(scriptPrompt).toContain('不确认、不发布')
  })
})
