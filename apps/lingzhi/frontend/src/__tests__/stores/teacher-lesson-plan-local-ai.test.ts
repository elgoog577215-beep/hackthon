import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const { generationMock } = vi.hoisted(() => ({ generationMock: vi.fn() }))

vi.mock('@/shared/generation-stream', () => ({
  postGenerationStream: generationMock,
}))

import { useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'

describe('教师教案局部 AI 请求', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    generationMock.mockReset()
  })

  it('发送精确对象、选区和修订身份，并消费流式进度', async () => {
    const progress = vi.fn()
    generationMock.mockImplementation(async (_url, _body, options) => {
      options.onProgress({ status: 'running', message: '正在生成', elapsed_ms: 2000 })
      return {
        candidate: {
          candidate_id: 'candidate-1',
          lesson_unit_id: 'lesson-1',
          base_revision_id: 'revision-1',
          instruction: '增加预测活动',
          section_node_id: 'section-1',
          target_field: 'teacher_activity',
          target_item_id: 'module-1',
          selected_text: '原教师活动',
          plan: { sections: [] },
          status: 'pending',
          created_at: '',
        },
      }
    })
    const store = useTeacherLessonAuthoringStore()

    await store.createAiCandidate(
      'course-1',
      'lesson-1',
      'revision-1',
      '增加预测活动',
      'section-1',
      ['material-1'],
      {
        sectionNodeId: 'section-1',
        field: 'teacher_activity',
        itemId: 'module-1',
        selectedText: '原教师活动',
      },
      progress,
    )

    expect(generationMock).toHaveBeenCalledWith(
      '/api/teacher/courses/course-1/lessons/lesson-1/plan/ai-candidates',
      {
        instruction: '增加预测活动',
        section_node_id: 'section-1',
        target_field: 'teacher_activity',
        target_item_id: 'module-1',
        selected_text: '原教师活动',
        base_revision_id: 'revision-1',
        material_asset_ids: ['material-1'],
      },
      expect.objectContaining({ onProgress: progress }),
    )
    expect(progress).toHaveBeenCalledWith(expect.objectContaining({ elapsed_ms: 2000 }))
  })
})
