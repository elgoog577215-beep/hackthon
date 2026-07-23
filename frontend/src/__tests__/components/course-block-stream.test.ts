import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia } from 'pinia'
import CourseBlockStream from '@/components/CourseBlockStream.vue'
import { useCourseStore } from '@/stores/course'
import { useCourseEvolutionStore } from '@/stores/courseEvolution'
import { useLearningProgressStore } from '@/stores/learningProgress'
import { PPT_SAME_SOURCE_STORAGE_KEY, PPT_SAME_SOURCE_TTL_MS } from '@/utils/ppt-same-source'
import type { Node as CourseNode, Note } from '@/stores/types'

const componentSource = readFileSync(resolve(process.cwd(), 'src/components/CourseBlockStream.vue'), 'utf8')
const desktopStyles = componentSource.slice(0, componentSource.indexOf('@media (max-width:880px)'))

const baseNode: CourseNode = {
  node_id: 'node-1',
  parent_node_id: 'root',
  node_name: '向量空间',
  node_level: 2,
  node_content: '旧版完整 Markdown',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 0,
}

const pinia = createPinia()
const global = {
  plugins: [pinia],
  stubs: {
    MarkdownRenderer: {
      props: ['content'],
      template: '<div class="markdown-renderer">{{ content }}</div>',
    },
    FeedbackReviewBlock: {
      name: 'FeedbackReviewBlock',
      props: ['content', 'structure', 'searchWords'],
      template: '<div class="feedback-review-stub">{{ content }}</div>',
    },
    MarkdownDocumentEditor: {
      props: ['content'],
      template: '<div class="legacy-markdown">{{ content }}</div>',
    },
    InlineCourseBlockAI: {
      name: 'InlineCourseBlockAI',
      props: ['node', 'block', 'active', 'regenerationRequest'],
      emits: ['activate', 'recordPersisted', 'recordReleased'],
      template: '<div><button class="inline-block-ai-stub" :data-block-id="block.block_id" @click="$emit(\'activate\', block.block_id)">AI</button><button class="persist-record-stub" @click="$emit(\'recordPersisted\', \'ai-note-1\')">persist</button><button class="release-record-stub" @click="$emit(\'recordReleased\', \'ai-note-1\')">release</button></div>',
    },
  },
}

beforeEach(() => {
  sessionStorage.clear()
})

describe('CourseBlockStream', () => {
  it('优先渲染正式课程文档块，而不是旧内容块副本', () => {
    const node: CourseNode = {
      ...baseNode,
      content_blocks: [
        { block_id: 'legacy', block_revision_id: 'old', type: 'concept', title: '旧块', content: '不应显示', order: 0 },
      ],
      course_blocks: [
        {
          block_id: 'canonical', section_id: 'node-1', position: 0, kind: 'rich_text', role: 'reasoning',
          payload: { title: '推导', markdown: '正式课程文档内容' }, asset_refs: [], objective_refs: [],
          concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-new', status: 'final',
        },
      ],
    }
    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })

    expect(wrapper.get('.course-content-block').attributes('data-content-block-id')).toBe('canonical')
    expect(wrapper.get('.markdown-renderer').text()).toBe('正式课程文档内容')
    expect(wrapper.text()).not.toContain('不应显示')
  })

  it('显示正式教学角色，并隐藏没有正文的最终空块', () => {
    const node: CourseNode = {
      ...baseNode,
      course_blocks: [
        {
          block_id: 'empty', section_id: 'node-1', position: 0, kind: 'rich_text', role: 'orientation',
          payload: { title: '向量空间', markdown: '' }, asset_refs: [], objective_refs: [], concept_refs: [],
          evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-empty', status: 'final',
        },
        {
          block_id: 'objective', section_id: 'node-1', position: 1, kind: 'rich_text', role: 'objective',
          payload: { title: '本节任务', markdown: '建立可验证的学习目标。' }, asset_refs: [], objective_refs: [],
          concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-objective', status: 'final',
        },
        {
          block_id: 'activity', section_id: 'node-1', position: 2, kind: 'rich_text', role: 'activity',
          payload: { title: '学习者行动', markdown: '请独立完成任务。' }, asset_refs: [], objective_refs: [],
          concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-activity', status: 'final',
        },
      ],
    }

    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })

    expect(wrapper.findAll('.course-content-block')).toHaveLength(2)
    expect(wrapper.text()).toContain('任务')
    expect(wrapper.text()).toContain('行动')
    expect(wrapper.text()).not.toContain('向量空间')
  })

  it('把正式反馈块交给核对视图，并透传后端编译结构', () => {
    const feedbackStructure = {
      schema_version: 'course_feedback_v1',
      mode: 'static_reference',
      sections: [{ section_id: 'task-1', title: '任务 1', markdown: '参考结论', collapsed_by_default: true }],
    }
    const node: CourseNode = {
      ...baseNode,
      course_blocks: [
        {
          block_id: 'feedback', section_id: 'node-1', position: 0, kind: 'review_checkpoint', role: 'feedback',
          payload: { title: '检查与反馈', markdown: '参考正文', feedback_structure: feedbackStructure },
          asset_refs: [], objective_refs: [], concept_refs: [], evidence_refs: [], visibility_rule: {},
          internal_revision: 'cbr-feedback', status: 'final',
        },
      ],
    }

    const wrapper = mount(CourseBlockStream, {
      props: { node, content: node.node_content, searchWords: ['结论'] },
      global,
    })
    const review = wrapper.findComponent({ name: 'FeedbackReviewBlock' })

    expect(wrapper.get('.course-content-block').attributes('data-content-block-kind')).toBe('review_checkpoint')
    expect(review.props('content')).toBe('参考正文')
    expect(review.props('structure')).toEqual(feedbackStructure)
    expect(review.props('searchWords')).toEqual(['结论'])
    expect(wrapper.find('.markdown-renderer').exists()).toBe(false)
  })

  it('把复合顺序证据渲染为可逐步操作的二维变换，而不是文字轮播', async () => {
    useCourseStore(pinia).currentCourseId = 'course-1'
    const interactionSpy = vi.spyOn(
      useLearningProgressStore(pinia),
      'recordAdaptiveBlockInteraction',
    ).mockResolvedValue(true)
    const node: CourseNode = {
      ...baseNode,
      course_blocks: [{
        block_id: 'growth-1', section_id: 'node-1', position: 0, kind: 'diagram', role: 'reasoning',
        payload: {
          title: '分步演示',
          markdown: '先观察对象，再比较变换前后的状态。',
          course_evolution: {
            schema_version: 'course_evolution_block_v1',
            change_set_id: 'plan-1',
            operation_id: 'operation-1',
            evidence_ids: ['evidence-1'],
          },
          animation_spec: {
            schema_version: 'animation_spec_v1',
            animation_id: 'animation-1',
            title: '复合变换顺序：为什么先做右边',
            accessibility_text: '依次展示原始图形、右侧变换 B 和左侧变换 A。',
            scene: {
              kind: 'linear_transform_composition',
              renderer: 'linear_transform_composition_v1',
              composition: 'ABv = A(Bv)',
            },
            keyframes: [
              {
                index: 1,
                label: '从原始图形 v 开始',
                state: {
                  description: '尚未执行变换。',
                  formula: 'v',
                  shape_points: '0,0 35,0 0,-25',
                  vector_x: '35',
                  vector_y: '0',
                },
                duration_ms: 500,
              },
              {
                index: 2,
                label: '先应用右侧变换 B',
                state: {
                  description: '先得到中间状态 Bv。',
                  formula: 'Bv',
                  shape_points: '0,0 0,-35 -25,0',
                  vector_x: '0',
                  vector_y: '-35',
                },
                duration_ms: 500,
              },
            ],
          },
        },
        asset_refs: [], objective_refs: [], concept_refs: [], evidence_refs: ['evidence-1'],
        visibility_rule: {}, internal_revision: 'cbr-growth', status: 'final',
      }],
    }

    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })

    expect(wrapper.get('.course-evolution-content').text()).toContain('先观察对象')
    expect(wrapper.find('.composition-stage').exists()).toBe(true)
    expect(wrapper.get('.composition-shape').attributes('points')).toBe('0,0 35,0 0,-25')
    await wrapper.findAll('.course-evolution-animation__timeline button')[1]!.trigger('click')
    expect(wrapper.get('.composition-shape').attributes('points')).toBe('0,0 0,-35 -25,0')
    expect(wrapper.get('.composition-copy').text()).toContain('先应用右侧变换 B')
    expect(interactionSpy).toHaveBeenCalledWith(
      'course-1',
      expect.objectContaining({ adaptive_block_id: 'operation-1' }),
      'animation_played',
      {},
    )
    expect(wrapper.text()).toContain('先判断，再验证')
    await wrapper.findAll('.composition-check button')[1]!.trigger('click')
    expect(wrapper.text()).toContain('顺序反了')
    expect(interactionSpy).toHaveBeenCalledWith(
      'course-1',
      expect.objectContaining({ adaptive_block_id: 'operation-1' }),
      'animation_answered',
      expect.objectContaining({
        answer: 'left_then_right',
        correct: false,
        frame_index: 1,
      }),
    )
    await wrapper.findAll('.composition-check button')[0]!.trigger('click')
    expect(wrapper.text()).toContain('右侧 B 先作用于 v')
    expect(interactionSpy).toHaveBeenCalledWith(
      'course-1',
      expect.objectContaining({ adaptive_block_id: 'operation-1' }),
      'animation_answered',
      expect.objectContaining({
        answer: 'right_then_left',
        correct: true,
        frame_index: 1,
      }),
    )
    expect(wrapper.text()).toContain('学习证据形成的课程版本')
    expect(wrapper.get('.course-content-block').attributes('data-content-block-id')).toBe('growth-1')
    const evolutionStore = useCourseEvolutionStore(pinia)
    const visualToken = evolutionStore.beginApplicationVisual({
      planId: 'plan-1',
      affectedSectionIds: ['node-1'],
      appliedBlockIds: ['growth-1'],
      operationIds: ['operation-1'],
      targetSectionId: 'node-1',
      targetBlockId: 'growth-1',
      targetOperationId: 'operation-1',
    })
    evolutionStore.setApplicationVisualPhase(visualToken, 'content')
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.course-content-block').classes()).toContain('is-ai-evolved-block')
    expect(wrapper.get('.course-content-block').classes()).toContain('is-ai-growth-highlight')
    expect(wrapper.get('.course-content-block').classes()).toContain('is-ai-growth-primary')
    expect(wrapper.get('.course-content-block').attributes('data-course-evolution-operation-id')).toBe('operation-1')
    expect(wrapper.get('.ai-evolution-block-badge').text()).toContain('AI 个体化补充')

    evolutionStore.setApplicationVisualPhase(visualToken, 'settled')
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.course-content-block').classes()).not.toContain('is-ai-growth-highlight')
    expect(wrapper.get('.course-content-block').classes()).toContain('is-ai-growth-primary')
    evolutionStore.clearApplicationVisual()
  })

  it('确认后的针对性练习正文块打开后端指定的正式题目', async () => {
    useCourseStore(pinia).currentCourseId = 'course-1'
    const interactionSpy = vi.spyOn(
      useLearningProgressStore(pinia),
      'recordAdaptiveBlockInteraction',
    ).mockResolvedValue(true)
    const node: CourseNode = {
      ...baseNode,
      course_blocks: [{
        block_id: 'targeted-practice-1', section_id: 'node-1', position: 0, kind: 'practice_ref', role: 'checkpoint',
        payload: {
          title: '针对性练习',
          markdown: '完成与当前能力缺口对应的独立检查。',
          practice_task_id: 'question-revision-targeted',
          practice_intent: 'targeted_retry',
          course_evolution: {
            schema_version: 'course_evolution_block_v1',
            change_set_id: 'plan-1',
            operation_id: 'operation-practice',
            evidence_ids: ['evidence-1'],
          },
        },
        asset_refs: ['question-revision-targeted'], objective_refs: [], concept_refs: [],
        evidence_refs: ['evidence-1'], visibility_rule: {}, internal_revision: 'cbr-practice', status: 'final',
      }],
    }

    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })
    expect(wrapper.get('.course-evolution-practice').text()).toContain('针对性练习')
    await wrapper.get('.course-evolution-practice button').trigger('click')
    expect(wrapper.emitted('startPractice')).toEqual([['question-revision-targeted']])
    expect(interactionSpy).toHaveBeenCalledWith(
      'course-1',
      expect.objectContaining({ adaptive_block_id: 'operation-practice' }),
      'validation_started',
      {},
    )
  })

  it('canonical 正文块只保留一个正式个性化入口并带出稳定块引用', async () => {
    const block = {
      block_id: 'canonical', section_id: 'node-1', position: 0, kind: 'rich_text' as const, role: 'concept' as const,
      payload: { title: '向量定义', markdown: '向量具有大小和方向。' }, asset_refs: [], objective_refs: ['lo-1'],
      concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'cbr-current', status: 'final' as const,
    }
    const node: CourseNode = { ...baseNode, course_blocks: [block] }
    const wrapper = mount(CourseBlockStream, {
      props: { node, content: node.node_content, canImproveBlocks: true },
      global,
    })

    expect(wrapper.find('.inline-block-ai-stub').exists()).toBe(false)
    expect(wrapper.findAll('.block-formal-improvement')).toHaveLength(1)
    const entry = wrapper.get('.block-formal-improvement')
    expect(entry.text()).toContain('调整这段')
    expect(desktopStyles).toMatch(/\.block-formal-improvement\s*\{[^}]*color:#1e293b;/s)
    expect(desktopStyles).toMatch(/\.block-formal-improvement\s*\{[^}]*opacity:\.68;[^}]*pointer-events:auto;/s)
    expect(desktopStyles).toMatch(/\.block-formal-improvement:hover,\s*\.block-formal-improvement:focus-visible,\s*\.course-content-block:hover > \.block-formal-improvement\s*\{[^}]*opacity:1;/s)
    await entry.trigger('click')
    expect(wrapper.emitted('improveBlock')).toEqual([[
      expect.objectContaining({ nodeId: 'node-1', block: expect.objectContaining({ block_id: 'canonical' }) }),
    ]])
  })

  it('旧结构化课程块也保留原位 AI 协作能力，但不冒充正式课程改写', () => {
    const node: CourseNode = {
      ...baseNode,
      content_blocks: [{ block_id: 'legacy', block_revision_id: 'old', type: 'concept', title: '旧块', content: '旧内容', order: 0 }],
    }
    const wrapper = mount(CourseBlockStream, {
      props: { node, content: node.node_content, canImproveBlocks: true },
      global,
    })

    expect(wrapper.find('.inline-block-ai-stub').exists()).toBe(true)
    expect(wrapper.find('.block-formal-improvement').exists()).toBe(false)
  })

  it('按正式顺序渲染结构化课程块和稳定锚点', () => {
    const node: CourseNode = {
      ...baseNode,
      content_blocks: [
        { block_id: 'b2', block_revision_id: 'r2', type: 'example', title: '例子', content: '第二块', order: 2 },
        { block_id: 'b1', block_revision_id: 'r1', type: 'concept', title: '定义', content: '第一块', order: 1 },
      ],
    }
    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })
    const blocks = wrapper.findAll('.course-content-block')

    expect(blocks).toHaveLength(2)
    expect(blocks[0]?.attributes('data-content-block-id')).toBe('b1')
    expect(blocks[0]?.attributes('data-content-block-revision-id')).toBe('r1')
    expect(blocks.map(block => block.find('.markdown-renderer').text())).toEqual(['第一块', '第二块'])
  })

  it('旧课程没有结构化块时无损回退到完整 Markdown', () => {
    const wrapper = mount(CourseBlockStream, { props: { node: baseNode, content: baseNode.node_content }, global })

    expect(wrapper.find('.legacy-markdown').text()).toBe('旧版完整 Markdown')
    expect(wrapper.find('.course-content-block').exists()).toBe(false)
  })

  it('把同一真源的学习记录投影到所属内容块之后', () => {
    const node: CourseNode = {
      ...baseNode,
      content_blocks: [
        { block_id: 'b1', block_revision_id: 'r1', type: 'concept', title: '定义', content: '向量空间的定义', order: 1 },
        { block_id: 'b2', block_revision_id: 'r2', type: 'example', title: '例子', content: '一个具体例子', order: 2 },
      ],
    }
    const record: Note = {
      id: 'note-1', nodeId: 'node-1', highlightId: 'hl-1', quote: '向量空间', content: '这里要区分集合和运算。',
      color: 'amber', createdAt: Date.now(), sourceType: 'user', recordType: 'note', status: 'active',
      anchor: { block_id: 'b1', block_revision_id: 'r1' }, migrationStatus: 'current', syncState: 'saved',
    }
    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content, records: [record] }, global })
    const children = wrapper.get('.course-block-stream').element.children

    expect(children[0]?.getAttribute('data-content-block-id')).toBe('b1')
    expect(children[1]?.classList.contains('inline-learning-record')).toBe(true)
    expect(children[1]?.textContent).toContain('这里要区分集合和运算。')
    expect(children[2]?.getAttribute('data-content-block-id')).toBe('b2')
  })

  it('已沉淀的 AI 讲解可从正文原位重做，展开结果时不重复投影旧记录', async () => {
    const node: CourseNode = {
      ...baseNode,
      content_blocks: [
        { block_id: 'b1', block_revision_id: 'r1', type: 'concept', title: '定义', content: '向量空间的定义', order: 1 },
      ],
    }
    const record: Note = {
      id: 'ai-note-1', nodeId: 'node-1', highlightId: 'hl-ai-note-1', quote: '向量空间的定义',
      content: '### 问题 / 请求\n为什么？\n\n### AI 讲解\n因为它满足封闭性。',
      color: 'purple', createdAt: Date.now(), sourceType: 'ai', recordType: 'note', status: 'active',
      anchor: { block_id: 'b1', block_revision_id: 'r1' }, migrationStatus: 'current', syncState: 'saved',
      metadata: { record_subtype: 'anchored_ai_qa', ai_prompt: '为什么？', inline_ai_action: 'ask' },
    }
    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content, records: [record] }, global })

    await wrapper.get('.record-actions button').trigger('click')
    const blockAi = wrapper.findComponent({ name: 'InlineCourseBlockAI' })
    expect(blockAi.props('active')).toBe(true)
    expect(blockAi.props('regenerationRequest')).toEqual(expect.objectContaining({
      token: 1,
      prompt: '为什么？',
      action: 'ask',
    }))

    await wrapper.get('.persist-record-stub').trigger('click')
    expect(wrapper.find('.inline-learning-record').exists()).toBe(false)
    await wrapper.get('.release-record-stub').trigger('click')
    expect(wrapper.find('.inline-learning-record').exists()).toBe(true)

  })
  it('只在目标课程正文块显示 PPT 同源黄色高亮，并保留 AI 生长块的紫色语义', async () => {
    useCourseStore(pinia).currentCourseId = 'course-1'
    sessionStorage.setItem(PPT_SAME_SOURCE_STORAGE_KEY, JSON.stringify({
      courseId: 'course-1',
      sectionId: 'node-1',
      blockIds: ['objective', 'growth'],
      primaryBlockId: 'objective',
      beforeText: '掌握矩阵乘法的计算规则',
      afterText: '理解矩阵乘法为什么表示线性变换的复合，并能解释运算顺序',
      createdAt: Date.now(),
      animationPlayed: false,
    }))
    const node: CourseNode = {
      ...baseNode,
      course_blocks: [
        {
          block_id: 'objective', section_id: 'node-1', position: 0, kind: 'callout', role: 'objective',
          payload: { title: '本节目标', markdown: '理解复合顺序。' }, asset_refs: [], objective_refs: [],
          concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'objective-r1', status: 'final',
        },
        {
          block_id: 'reasoning', section_id: 'node-1', position: 1, kind: 'rich_text', role: 'reasoning',
          payload: { title: '未受影响', markdown: '保持正式课程蓝色语义。' }, asset_refs: [], objective_refs: [],
          concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'reasoning-r1', status: 'final',
        },
        {
          block_id: 'growth', section_id: 'node-1', position: 2, kind: 'rich_text', role: 'reasoning',
          payload: {
            title: 'AI 新增',
            markdown: '保持个体化生长语义。',
            course_evolution: { change_set_id: 'plan-1', operation_id: 'operation-1' },
          },
          asset_refs: [], objective_refs: [], concept_refs: [], evidence_refs: [],
          visibility_rule: {}, internal_revision: 'growth-r1', status: 'final',
        },
      ],
    }

    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })
    await wrapper.vm.$nextTick()
    const blocks = wrapper.findAll('.course-content-block')

    expect(blocks[0]!.classes()).toContain('is-ppt-same-source-highlight')
    expect(blocks[0]!.classes()).toContain('is-ppt-same-source-primary')
    expect(blocks[0]!.text()).toContain('课程正文已同步更新')
    expect(blocks[0]!.text()).toContain('PPT 的修改已经联动到这里')
    expect(blocks[0]!.text()).toContain('由 PPT 学习目标修改触发 · 以下为真实前后差异')
    expect(blocks[0]!.text()).toContain('掌握矩阵乘法的计算规则')
    expect(blocks[0]!.text()).toContain('理解矩阵乘法为什么表示线性变换的复合')
    expect(blocks[1]!.classes()).not.toContain('is-ppt-same-source-highlight')
    expect(blocks[2]!.classes()).toContain('is-ai-evolved-block')
    expect(blocks[2]!.classes()).not.toContain('is-ppt-same-source-highlight')
    expect(JSON.parse(sessionStorage.getItem(PPT_SAME_SOURCE_STORAGE_KEY) || '{}').animationPlayed).toBe(true)
    wrapper.unmount()
  })

  it('忽略并清理超过十分钟的 PPT 同源高亮状态', async () => {
    useCourseStore(pinia).currentCourseId = 'course-1'
    sessionStorage.setItem(PPT_SAME_SOURCE_STORAGE_KEY, JSON.stringify({
      courseId: 'course-1',
      sectionId: 'node-1',
      blockIds: ['objective'],
      primaryBlockId: 'objective',
      beforeText: '旧目标',
      afterText: '新目标',
      createdAt: Date.now() - PPT_SAME_SOURCE_TTL_MS - 1,
    }))
    const node: CourseNode = {
      ...baseNode,
      course_blocks: [{
        block_id: 'objective', section_id: 'node-1', position: 0, kind: 'callout', role: 'objective',
        payload: { title: '本节目标', markdown: '正式正文。' }, asset_refs: [], objective_refs: [],
        concept_refs: [], evidence_refs: [], visibility_rule: {}, internal_revision: 'objective-r1', status: 'final',
      }],
    }

    const wrapper = mount(CourseBlockStream, { props: { node, content: node.node_content }, global })
    await wrapper.vm.$nextTick()

    expect(wrapper.get('.course-content-block').classes()).not.toContain('is-ppt-same-source-highlight')
    expect(wrapper.find('.ppt-same-source-badge').exists()).toBe(false)
    expect(sessionStorage.getItem(PPT_SAME_SOURCE_STORAGE_KEY)).toBeNull()
  })
})
