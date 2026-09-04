import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ScriptVisualStudio from '@/components/ScriptVisualStudio.vue'
import StructuredScenePlayer from '@/components/StructuredScenePlayer.vue'
import { setLocale } from '@/shared/i18n'
import {
  type ScriptVisualItem,
  useTeacherScriptVisualStore,
} from '@/stores/teacherScriptVisuals'
import zhMessages from '../../../public/locales/zh/translation.json'

const source = {
  lesson_unit_id: 'lesson-1',
  script_revision_id: 'script-r1',
  section_node_id: 'section-1',
  block_id: 'block-1',
  block_content_fingerprint: 'cbf-1',
  title: '处理过程',
}

function item(overrides: Partial<ScriptVisualItem> = {}): ScriptVisualItem {
  return {
    representation_id: 'visual-1',
    representation_type: 'diagram',
    status: 'candidate',
    revision: 'visual-r1',
    source,
    content: {
      schema_version: 'diagram_spec_v1',
      title: '处理过程图解',
      units: [{
        unit_id: 'unit-1', diagram_kind: 'concept_map', title: '处理过程图解',
        nodes: [
          { node_id: 'n1', label: '输入', kind: 'objective' },
          { node_id: 'n2', label: '输出', kind: 'knowledge' },
        ],
        edges: [{ edge_id: 'e1', source_node_id: 'n1', target_node_id: 'n2', relation: 'supports' }],
      }],
    },
    artifact_ids: [],
    stale_reasons: [],
    created_at: '2026-09-04T00:00:00Z',
    updated_at: '2026-09-04T00:00:00Z',
    ...overrides,
  }
}

describe('讲义块视觉表达工作区', () => {
  beforeEach(async () => {
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })

  function mountStudio(items: ScriptVisualItem[]) {
    const store = useTeacherScriptVisualStore()
    store.views['course-1\u0000lesson-1'] = {
      schema_version: 'teacher_script_visual_view_v1',
      course_id: 'course-1',
      lesson_unit_id: 'lesson-1',
      script_revision_id: 'script-r1',
      available_types: ['diagram', 'image'],
      animation_runtime: 'gray_disabled',
      recommendations: [{
        block_id: 'block-1',
        recommended_types: ['diagram'],
        reason: '这一段包含公式、概念或过程关系，适合用结构图解讲清。',
        reason_code: 'process_or_change',
      }],
      items,
      representation_sets: [],
    }
    return {
      store,
      wrapper: mount(ScriptVisualStudio, {
        props: {
          courseId: 'course-1',
          lessonUnitId: 'lesson-1',
          scriptRevisionId: 'script-r1',
          sectionNodeId: 'section-1',
          blockId: 'block-1',
          blockTitle: '处理过程',
        },
      }),
    }
  }

  it('默认折叠，展开后只提供正式运行的图解和 AI 插图入口', async () => {
    const historicalAnimation = item({
      representation_id: 'animation-1',
      representation_type: 'animation',
      content: { schema_version: 'scene_spec_v2' },
    })
    const { wrapper } = mountStudio([historicalAnimation])

    expect(wrapper.get('.script-visual-toggle').attributes('aria-expanded')).toBe('false')
    await wrapper.get('.script-visual-toggle').trigger('click')

    expect(wrapper.get('.script-visual-toggle').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.script-visual-create').text()).toContain('适合用结构图解讲清')
    expect(wrapper.findAll('.script-visual-create button').map(button => button.text())).toEqual([
      '生成图解', '生成 AI 插图',
    ])
    expect(wrapper.find('[data-type="animation"]').exists()).toBe(false)
  })

  it('图片服务未配置时保留提示词并只提供放弃或重试', async () => {
    const unavailableImage = item({
      representation_id: 'image-1',
      representation_type: 'image',
      content: {
        schema_version: 'script_image_spec_v1',
        generation_status: 'provider_unavailable',
        provenance_label: 'AI 生成插图',
        prompt: 'A visual explanation of input and output',
      },
    })
    const { wrapper } = mountStudio([unavailableImage])
    await wrapper.get('.script-visual-toggle').trigger('click')

    const image = wrapper.get('.script-visual-item[data-type="image"]')
    expect(image.text()).toContain('AI 插图')
    expect(image.text()).toContain('图片服务未配置')
    expect(image.text()).toContain('生成提示词已经保存')
    expect(image.findAll('footer button').map(button => button.text())).toEqual(['放弃', '重新生成'])
    expect(image.text()).not.toContain('采用')
  })

  it('教师采用图解后才进入共享表达集', async () => {
    const candidate = item()
    const { store, wrapper } = mountStudio([candidate])
    const resolve = vi.spyOn(store, 'resolve').mockResolvedValue({ ...candidate, status: 'accepted' })
    await wrapper.get('.script-visual-toggle').trigger('click')
    await wrapper.get('.script-visual-item footer .primary').trigger('click')
    await flushPromises()

    expect(resolve).toHaveBeenCalledWith('course-1', 'lesson-1', 'script-r1', 'visual-1', true)
  })

  it('已采用表达明确说明由讲义、PPT 和学生端共享', async () => {
    const { wrapper } = mountStudio([item({ status: 'accepted' })])
    await wrapper.get('.script-visual-toggle').trigger('click')

    expect(wrapper.get('.accepted-note').text()).toContain('讲义、PPT 和学生端复用')
  })
})

describe('结构化动画播放器', () => {
  const scene = {
    schema_version: 'scene_spec_v1',
    title: '输入到输出',
    duration_ms: 3000,
    objects: [
      { object_id: 'input', label: '输入', kind: 'source', x: 10, y: 50 },
      { object_id: 'output', label: '输出', kind: 'result', x: 85, y: 50 },
    ],
    actions: [
      { action_id: 'r1', action_type: 'reveal', target_ids: ['input'], start_ms: 0, duration_ms: 400 },
      { action_id: 'r2', action_type: 'reveal', target_ids: ['output'], start_ms: 1200, duration_ms: 400 },
      { action_id: 'c1', action_type: 'connect', target_ids: ['input', 'output'], start_ms: 1200, duration_ms: 400 },
    ],
    checkpoints: [
      { checkpoint_id: 's1', label: '先看输入', at_ms: 0 },
      { checkpoint_id: 's2', label: '再看输出', at_ms: 1200 },
    ],
    static_fallback: {},
  }

  const motionScene = {
    schema_version: 'scene_spec_v2',
    title: '小球沿斜面滚下',
    scene_kind: 'physical_motion',
    learning_focus: '观察小球的位置、转动和速度变化。',
    assumptions: [],
    duration_ms: 6200,
    generation_mode: 'ai_planned',
    objects: [
      {
        object_id: 'ramp', kind: 'polygon', label: '斜面', x: 0, y: 0, width: 0, height: 0,
        radius: 0, points: [{ x: 14, y: 75 }, { x: 82, y: 75 }, { x: 14, y: 22 }],
        fill: 'muted', stroke: 'ink', stroke_width: 1.5, visible: true,
      },
      {
        object_id: 'ball', kind: 'circle', label: '小球', x: 20, y: 22.5, width: 0, height: 0,
        radius: 4, points: [], fill: 'warm', stroke: 'ink', stroke_width: 2, visible: true,
      },
      {
        object_id: 'trajectory', kind: 'path', label: '轨迹', x: 0, y: 0, width: 0, height: 0,
        radius: 0, points: [{ x: 20, y: 22.5 }, { x: 76, y: 66.5 }],
        fill: 'muted', stroke: 'accent', stroke_width: 1.5, visible: false,
      },
    ],
    actions: [
      {
        action_id: 'move', action_type: 'move', target_id: 'ball', start_ms: 1200, duration_ms: 4200,
        easing: 'accelerate', path: [{ x: 20, y: 22.5 }, { x: 76, y: 66.5 }],
        from_rotation: 0, to_rotation: 0,
      },
      {
        action_id: 'rotate', action_type: 'rotate', target_id: 'ball', start_ms: 1200, duration_ms: 4200,
        easing: 'accelerate', path: [], from_rotation: 0, to_rotation: 1080,
      },
      {
        action_id: 'trace', action_type: 'trace', target_id: 'trajectory', start_ms: 1200, duration_ms: 4200,
        easing: 'accelerate', path: [], from_rotation: 0, to_rotation: 0,
      },
    ],
    checkpoints: [
      { checkpoint_id: 's1', label: '观察初始位置', at_ms: 0 },
      { checkpoint_id: 's2', label: '释放小球', at_ms: 1200 },
      { checkpoint_id: 's3', label: '观察加速滚动', at_ms: 3300 },
      { checkpoint_id: 's4', label: '到达底端', at_ms: 5400 },
    ],
    static_fallback: {},
  }

  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    await setLocale('zh')
  })

  it('支持逐步前进和后退', async () => {
    const wrapper = mount(StructuredScenePlayer, { props: { scene } })
    expect(wrapper.get('.scene-progress').text()).toContain('1/2')

    const buttons = wrapper.findAll('.scene-controls button')
    await buttons.find(button => button.text().includes('下一步'))!.trigger('click')
    expect(wrapper.get('.scene-progress').text()).toContain('再看输出')
    expect(wrapper.get('.scene-progress').text()).toContain('2/2')

    await wrapper.findAll('.scene-controls button').find(button => button.text().includes('上一步'))!.trigger('click')
    expect(wrapper.get('.scene-progress').text()).toContain('先看输入')
  })

  it('系统要求减少动态效果时，播放直接展示最终检查点', async () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: true })))
    const wrapper = mount(StructuredScenePlayer, { props: { scene } })
    await wrapper.findAll('.scene-controls button').find(button => button.text().includes('播放'))!.trigger('click')

    expect(wrapper.get('.scene-progress').text()).toContain('2/2')
    expect(wrapper.get('.scene-player').attributes('data-playing')).toBe('false')
  })

  it('能渲染斜面、小球和轨迹，并在时间轴上连续改变位置与转角', async () => {
    const wrapper = mount(StructuredScenePlayer, { props: { scene: motionScene } })
    const ball = wrapper.get('[data-object-id="ball"]')
    const initialTransform = ball.attributes('transform')

    expect(wrapper.get('.scene-player').attributes('data-scene-version')).toBe('scene_spec_v2')
    expect(wrapper.find('[data-object-id="ramp"] polygon').exists()).toBe(true)
    expect(wrapper.find('[data-object-id="ball"] circle').exists()).toBe(true)
    expect(wrapper.get('.scene-purpose').text()).toContain('AI 场景动画')

    const nextButton = () => wrapper.findAll('.scene-controls button')
      .find(button => button.text().includes('下一步'))!
    await nextButton().trigger('click')
    await nextButton().trigger('click')

    expect(wrapper.get('.scene-progress').text()).toContain('观察加速滚动')
    expect(ball.attributes('transform')).not.toBe(initialTransform)
    expect(ball.attributes('transform')).toContain('rotate(270)')
    expect(wrapper.get('[data-object-id="trajectory"] polyline').attributes('style')).toContain('stroke-dashoffset: 75')
  })
})
