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
  buildTeacherCourseChangeInstruction,
  buildTeacherProductionAiInstruction,
  projectTeacherCoursePlan,
  routeTeacherProductionRequest,
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
  it('在共享状态机前使用各生产对象自己的意图边界', () => {
    expect(assessTeacherProductionRequest('outline', '优化一下')).toBe('clarify')
    expect(assessTeacherProductionRequest('outline', '把网络安全章前移到工程实践之前')).toBe('generate')
    expect(assessTeacherProductionRequest('script', '这段不太好')).toBe('clarify')
    expect(assessTeacherProductionRequest('script', '压缩重复表达，加入一个课堂案例')).toBe('generate')
    expect(assessTeacherProductionRequest('question-bank', '重新弄一下')).toBe('clarify')
    expect(assessTeacherProductionRequest('question-bank', '增加两道应用题并保持原难度')).toBe('generate')
    expect(assessTeacherProductionRequest('ppt', '这页不好')).toBe('clarify')
    expect(assessTeacherProductionRequest('ppt', '压缩当前页标题并强化关键内容')).toBe('generate')
  })

  it('把局部候选、批量修改和结构调整送入各自唯一的正式链路', () => {
    expect(routeTeacherProductionRequest('lesson', '把教学目标改成学生能独立完成流程图')).toMatchObject({
      capability: 'edit_active_asset', reason: 'active_asset',
    })
    expect(routeTeacherProductionRequest('script', '压缩重复表达，加入一个课堂案例')).toMatchObject({
      capability: 'edit_active_asset', reason: 'active_asset',
    })
    expect(routeTeacherProductionRequest('outline', '把第2、第5、第7小节删除，第8和第9合并，再与第10交换位置')).toMatchObject({
      capability: 'plan_course_change', reason: 'structural_change',
    })
    expect(routeTeacherProductionRequest('lesson', '把大纲、教案和讲稿里的 A 术语统一替换成 B')).toMatchObject({
      capability: 'plan_course_change', reason: 'cross_asset',
    })
    expect(routeTeacherProductionRequest('lesson', '把 A 这个名词永远都替换成 B')).toMatchObject({
      capability: 'plan_course_change', reason: 'batch_change',
    })
    expect(routeTeacherProductionRequest('lesson', '你觉得整门课应该怎么改')).toMatchObject({
      capability: 'clarify_request', reason: 'unclear',
    })
    expect(routeTeacherProductionRequest('ppt', '统一修改讲稿和 PPT 中的导数定义')).toMatchObject({
      capability: 'plan_course_change', reason: 'cross_asset',
    })
  })

  it('整课请求只传递教师连续要求和发起位置，不冒充已经执行', () => {
    const prompt = buildTeacherCourseChangeInstruction([
      { id: '1', role: 'user', kind: 'text', text: '把第二章和第三章合并' },
      { id: '2', role: 'user', kind: 'text', text: '同时更新教案和讲稿' },
    ], {
      domain: 'outline', courseTitle: '微积分', primaryTitle: '课程大纲', secondaryTitle: '第 2 章', referenceCount: 0,
    })
    expect(prompt).toContain('课程：微积分')
    expect(prompt).toContain('把第二章和第三章合并')
    expect(prompt).toContain('同时更新教案和讲稿')
    expect(prompt).toContain('不要写入正式课程')
  })

  it('用同一个轻量投影向主工作台和 PPT 工作区呈现整课方案', () => {
    expect(projectTeacherCoursePlan({
      change_set_id: 'plan-1',
      impact_summary: {
        request_id: 'request-1',
        affected_units: [{ asset_type: 'ppt' }, { asset_type: 'script' }, { asset_type: 'ppt' }],
      },
      teacher_change_planning: {
        status: 'needs_clarification',
        structural_operations: [{ operation_id: 'move-1' }],
        intent: { blocking_questions: ['需要保留哪些页面？'] },
      },
    })).toEqual({
      planId: 'plan-1', requestId: 'request-1', status: 'needs_clarification',
      affectedUnitCount: 3, structuralOperationCount: 1,
      assetTypes: ['ppt', 'script'], blockingQuestionCount: 1,
    })
  })

  it('为不同生产对象构建各自的后端候选约束和精确资料范围', () => {
    const messages = [{ id: '1', role: 'user' as const, kind: 'text' as const, text: '合并两个重复小节' }]
    const outlinePrompt = buildTeacherProductionAiInstruction(messages, {
      domain: 'outline', courseTitle: '测试课程', primaryTitle: '测试课程', secondaryTitle: '课程大纲', referenceCount: 2,
    })
    const scriptPrompt = buildTeacherProductionAiInstruction(messages, {
      domain: 'script', courseTitle: '测试课程', primaryTitle: '第一讲', secondaryTitle: '导入', referenceCount: 1,
      selectionText: '这段定义重复了两次',
    })
    const questionPrompt = buildTeacherProductionAiInstruction(messages, {
      domain: 'question-bank', courseTitle: '测试课程', primaryTitle: '测试课程', secondaryTitle: '整门课程题库', referenceCount: 1,
      references: [{ id: 'material-1', label: '课程讲义', role: 'primary', origin: 'material' }],
    })
    const pptPrompt = buildTeacherProductionAiInstruction(messages, {
      domain: 'ppt', courseTitle: '测试课程', primaryTitle: '并发的基本概念', secondaryTitle: '第 3 页', referenceCount: 1,
      references: [{ id: 'block-7', label: '课程源 1', role: 'primary' }],
    })
    expect(outlinePrompt).toContain('结构调整候选')
    expect(outlinePrompt).toContain('章节增删、顺序')
    expect(scriptPrompt).toContain('表达修改候选')
    expect(scriptPrompt).toContain('保持已确认教案')
    expect(scriptPrompt).toContain('不确认、不发布')
    expect(scriptPrompt).toContain('本轮只围绕此内容修改')
    expect(scriptPrompt).toContain('这段定义重复了两次')
    expect(questionPrompt).toContain('重建任务候选')
    expect(questionPrompt).toContain('整门课程题库')
    expect(questionPrompt).toContain('保持已确认的课程范围')
    expect(questionPrompt).not.toContain('当前讲次')
    expect(questionPrompt).not.toContain('当前节点')
    expect(questionPrompt).toContain('答案事实、验证器和质量门')
    expect(questionPrompt).toContain('课程讲义 (material-1)')
    expect(pptPrompt).toContain('V6 PPT 页面')
    expect(pptPrompt).toContain('课程源 1 (block-7)')
    expect(pptPrompt).toContain('保持页面身份、顺序、来源绑定')
  })
})
