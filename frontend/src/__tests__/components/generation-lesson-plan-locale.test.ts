import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GenerationLessonPlan from '@/components/GenerationLessonPlan.vue'
import { initializeI18n, setLocale } from '@/shared/i18n'
import type { Node } from '@/stores/types'

const nodes: Node[] = [{
  node_id: 'section-1', node_name: '第一章第一节 矩阵复合', node_level: 2,
  parent_node_id: 'chapter-1', node_content: '', learning_objective: '理解斜率',
  node_type: 'original', generation_status: 'completed', generated_chars: 0,
}]
const plan: any = {
  schema_version: 'course_teaching_plan_projection_v1', status: 'completed',
  revision_id: 'r1', strategy: 'batched', section_count: 1,
  knowledge_point_count: 1, teaching_module_count: 1,
  overall: {
    course_title: '线性代数', positioning: '定位', target_audience: '大一',
    learning_objectives: ['能复合矩阵'], prerequisites: ['矩阵乘法'],
    teaching_strategy: { primary_mode: 'conceptual', secondary_mode: 'math_formal', rationale: '先几何后代数' },
    assessment_methods: ['出口题'], chapters: [], knowledge_tags: [],
  },
  sections: [{ node_id: 'section-1', key_points: ['复合'], reused_knowledge_names: [],
    knowledge_relations: [], teaching_modules: [], knowledge_structure: [] }],
}

async function mountWith(lang: 'zh' | 'en') {
  const dict = JSON.parse(readFileSync(resolve(process.cwd(), `public/locales/${lang}/translation.json`), 'utf8'))
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => dict }))
  setLocale(lang)
  await initializeI18n()
  return mount(GenerationLessonPlan, { props: { nodes, plan, activeNodeId: 'section-1' } })
}

describe('真实渲染：中英文教案页面', () => {
  beforeEach(() => { setActivePinia(createPinia()); vi.unstubAllGlobals() })

  it('中文模式显示教学大纲/教学设计/教学目标/前置知识', async () => {
    const w = await mountWith('zh')
    const text = w.text()
    console.log('--- ZH tabs:', w.findAll('.generation-lesson-plan__view-switch strong').map(n => n.text()))
    console.log('--- ZH eyebrows:', w.findAll('.generation-lesson-plan__overview small').slice(0,6).map(n => n.text()))
    expect(text).toContain('教学大纲')
    expect(text).toContain('教学设计')
    expect(text).toContain('教学目标')
    expect(text).toContain('前置知识')
    expect(text).not.toContain('math formal')
    expect(text).not.toContain('math_formal')
    // 小节标题里的章节编号是内容，不受术语改名影响
    // 切到教学设计 tab：小节标题里的章节编号是课程内容，不受术语改名影响
    await w.findAll('.generation-lesson-plan__view-switch button')[1]!.trigger('click')
    expect(w.text()).toContain('第一章第一节 矩阵复合')
  })

  it('英文模式无中文残留、无原始 key', async () => {
    const w = await mountWith('en')
    const text = w.text()
    console.log('--- EN tabs:', w.findAll('.generation-lesson-plan__view-switch strong').map(n => n.text()))
    expect(text).toContain('Syllabus')
    expect(text).toContain('Lesson design')
    expect(text).toContain('Learning objectives')
    expect(text).toContain('Prerequisites')
    expect(text).not.toContain('math formal')
    expect(text).not.toContain('math_formal')
    expect(text).not.toContain('courseGeneration.lessonPlan')
    // 课程内容本身是中文（课名、目标、前置），那是数据不是界面文案。
    // 只检查界面 chrome：tab、眉标、按钮、区块标题。
    const chrome = [
      ...w.findAll('.generation-lesson-plan__view-switch strong'),
      ...w.findAll('.generation-lesson-plan__view-switch small'),
      ...w.findAll('.generation-lesson-plan__overview small'),
      ...w.findAll('.generation-lesson-plan__overview h4'),
      ...w.findAll('button'),
    ].map(n => n.text())
    console.log('--- EN chrome:', chrome)
    const cjk = chrome.filter(item => /[一-鿿]/.test(item))
    expect(cjk).toEqual([])
  })
})
