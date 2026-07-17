import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import CourseNode from '@/components/CourseNode.vue'
import { useCourseWorkspaceStore } from '@/stores/courseWorkspace'
import { useLearningProgressStore } from '@/stores/learningProgress'
import type { Node as CourseNodeModel } from '@/stores/types'

const node: CourseNodeModel = {
  node_id: 'node-1',
  parent_node_id: 'chapter-1',
  node_name: '1.1 向量空间',
  node_level: 2,
  node_content: '正文',
  node_type: 'original',
  generation_status: 'completed',
  generated_chars: 2,
}

const mountNode = () => mount(CourseNode, {
  props: { node, index: 0, fontSize: 16, fontFamily: 'sans', lineHeight: 1.8 },
  global: {
    stubs: {
      CourseBlockStream: { template: '<div class="block-stream" />' },
    },
  },
})

describe('CourseNode 正式练习入口', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('没有正式题目资产时不显示练习入口', () => {
    const workspace = useCourseWorkspaceStore()
    workspace.assets = {
      course_id: 'course-1',
      plan: {},
      quality_report: {},
      course_availability: { schema_version: 'course_learning_availability_v1', mode: 'compatibility', reason_code: 'legacy', capabilities: {} },
      assets: { questions: [] },
    }

    expect(mountNode().find('.task-launcher').exists()).toBe(false)
  })

  it('只对当前节点的正式题目显示入口并发出打开事件', async () => {
    const workspace = useCourseWorkspaceStore()
    workspace.assets = {
      course_id: 'course-1',
      plan: {},
      quality_report: {},
      course_availability: { schema_version: 'course_learning_availability_v1', mode: 'standard', reason_code: 'ready', capabilities: {} },
      assets: {
        questions: [
          { asset_id: 'q1', revision_id: 'qr1', node_id: node.node_id, prompt: '为什么线性组合仍然属于这个向量空间？' },
          { asset_id: 'q2', revision_id: 'qr2', node_id: node.node_id, prompt: '判断给定集合是否构成子空间。' },
        ],
      },
    }
    const wrapper = mountNode()

    expect(wrapper.get('.task-launcher').attributes('aria-haspopup')).toBe('dialog')
    expect(wrapper.get('.task-launcher').attributes('id')).toBe('practice-block-node-1')
    expect(wrapper.get('.task-launcher').text()).toContain('2 道正式题')
    expect(wrapper.get('.task-launcher').text()).toContain('为什么线性组合仍然属于这个向量空间？')
    await wrapper.find('.task-launcher').trigger('click')
    expect(wrapper.emitted('startPractice')?.[0]?.[0]).toMatchObject({ node_id: node.node_id })
  })

  it('个人理解检查复用同一正式练习弹窗', async () => {
    const workspace = useCourseWorkspaceStore()
    workspace.assets = {
      course_id: 'course-1',
      plan: {},
      quality_report: {},
      course_availability: { schema_version: 'course_learning_availability_v1', mode: 'standard', reason_code: 'ready', capabilities: {} },
      assets: {
        questions: [{ asset_id: 'q1', revision_id: 'qr1', node_id: node.node_id, prompt: '解释复合顺序。' }],
      },
    }
    useLearningProgressStore().runtime = {
      adaptive_blocks: [{
        adaptive_block_id: 'check-1',
        anchor: { node_id: node.node_id },
        status: 'active',
      }],
    } as any
    const wrapper = mount(CourseNode, {
      props: { node, index: 0, fontSize: 16, fontFamily: 'sans', lineHeight: 1.8 },
      global: {
        stubs: {
          CourseBlockStream: { template: '<div class="block-stream" />' },
          AdaptiveLearningBlock: {
            emits: ['verify'],
            template: '<button class="formal-verify" @click="$emit(\'verify\')">复验</button>',
          },
        },
      },
    })

    await wrapper.get('.formal-verify').trigger('click')
    expect(wrapper.emitted('startPractice')?.[0]?.[0]).toMatchObject({ node_id: node.node_id })
  })

  it('章节正文会应用阅读字号、字体和行高', () => {
    const wrapper = mount(CourseNode, {
      props: { node, index: 0, fontSize: 21, fontFamily: 'serif', lineHeight: 1.9 },
      global: {
        stubs: {
          CourseBlockStream: { template: '<div class="block-stream" />' },
        },
      },
    })

    const style = wrapper.find('.chapter-content').attributes('style')
    expect(style).toContain('--content-font-size: 21px')
    expect(style).toContain('--content-line-height: 1.9')
    expect(style).toContain('font-size: 21px')
    expect(style).toContain('Noto Serif SC')
  })

  it('课程开篇正文也会应用阅读设置', () => {
    const wrapper = mount(CourseNode, {
      props: { node: { ...node, node_level: 1 }, index: 0, fontSize: 19, fontFamily: 'mono', lineHeight: 1.6 },
      global: {
        stubs: {
          CourseBlockStream: { template: '<div class="block-stream" />' },
        },
      },
    })

    const style = wrapper.find('.opening-content').attributes('style')
    expect(style).toContain('font-size: 19px')
    expect(style).toContain('ui-monospace')
  })
})
