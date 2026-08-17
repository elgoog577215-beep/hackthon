import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import GenerationLessonPlan from '@/components/GenerationLessonPlan.vue'
import LessonDossierSheet from '@/components/LessonDossierSheet.vue'
import { setLocale } from '@/shared/i18n'
import type {
  CourseLessonDossier,
  CourseLessonDossierConsistency,
  Node,
} from '@/stores/types'
import fixture from '../fixtures/lesson-dossier.json'

// fixture 由后端 `build_lesson_dossier` 真实产出（见
// backend/tests/test_course_lesson_dossier.py），不是手写的形状猜测。
const rich = fixture.rich as unknown as CourseLessonDossier
const sparse = fixture.sparse as unknown as CourseLessonDossier
const consistency = fixture.consistency as unknown as CourseLessonDossierConsistency

const nodes: Node[] = [
  {
    node_id: 'chapter-1',
    node_name: '第一章 向量',
    node_level: 1,
    parent_node_id: '',
    node_content: '',
    node_type: 'original',
    generation_status: 'completed',
    generated_chars: 0,
  },
  {
    node_id: 'section-1',
    node_name: '向量的线性组合',
    node_level: 2,
    parent_node_id: 'chapter-1',
    node_content: '',
    learning_objective: '能用线性组合解释生成关系',
    node_type: 'original',
    generation_status: 'completed',
    generated_chars: 0,
  },
  {
    node_id: 'section-2',
    node_name: '张成空间',
    node_level: 2,
    parent_node_id: 'chapter-1',
    node_content: '',
    learning_objective: '能判断张成范围',
    node_type: 'original',
    generation_status: 'completed',
    generated_chars: 0,
  },
]

function plan() {
  return {
    schema_version: 'course_teaching_plan_projection_v1' as const,
    status: 'completed',
    revision_id: 'teaching-1',
    strategy: 'batched',
    section_count: 2,
    knowledge_point_count: 2,
    teaching_module_count: 5,
    dossier_consistency: consistency,
    overall: {
      course_title: '线性代数',
      positioning: '从几何直觉进入线性变换',
      target_audience: '大一学生',
      learning_objectives: ['理解线性组合'],
      prerequisites: ['向量加法'],
      teaching_strategy: { primary_mode: 'conceptual', secondary_mode: '', rationale: '' },
      assessment_methods: ['出口题'],
      classroom: { lesson_duration_minutes: 45 },
      chapters: [{
        chapter_id: 'chapter-1',
        chapter_number: '1',
        title: '第一章 向量',
        learning_focus: '建立向量直觉',
        section_count: 2,
        section_ids: ['section-1', 'section-2'],
      }],
      knowledge_tags: [],
    },
    sections: [
      { node_id: 'section-1', key_points: ['线性组合'], reused_knowledge_names: [], knowledge_relations: [], knowledge_structure: [], teaching_modules: [], dossier: rich },
      { node_id: 'section-2', key_points: ['张成空间'], reused_knowledge_names: [], knowledge_relations: [], knowledge_structure: [], teaching_modules: [], dossier: sparse },
    ],
  } as any
}

function mountSection(activeNodeId: string) {
  const wrapper = mount(GenerationLessonPlan, {
    props: { nodes, plan: plan(), activeNodeId, preferSectionView: true },
  })
  return wrapper
}

describe('教案统一模板：栏目恒定', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('内容丰富的一节与几乎空白的一节使用完全相同的栏目与顺序', () => {
    const richSheet = mount(LessonDossierSheet, { props: { dossier: rich } })
    const sparseSheet = mount(LessonDossierSheet, { props: { dossier: sparse } })

    const rubricsOf = (wrapper: ReturnType<typeof mount>) => wrapper
      .findAll('.lesson-dossier__rubric')
      .map(item => item.attributes('data-rubric'))

    // 这是本条验收的直接证据：两节栏目键、顺序、数量完全一致。
    expect(rubricsOf(richSheet)).toEqual(rubricsOf(sparseSheet))
    expect(rubricsOf(richSheet)).toEqual([
      'objectives', 'focus', 'knowledge', 'timeline', 'alignment',
      'misconceptions', 'assessment', 'homework', 'resources', 'notes',
    ])

    const headings = (wrapper: ReturnType<typeof mount>) => wrapper
      .findAll('.lesson-dossier__rubric h4')
      .map(item => item.text())
    expect(headings(richSheet)).toEqual(headings(sparseSheet))

    // 空栏目不消失，而是留位并写明待补充——这样翻页时排版不会跳。
    const sparseStatuses = sparseSheet
      .findAll('.lesson-dossier__rubric')
      .map(item => item.attributes('data-status'))
    expect(sparseStatuses).toContain('empty')
    expect(sparseSheet.find('[data-rubric="homework"]').text()).toContain('待补充')
    expect(richSheet.find('[data-rubric="homework"][data-status="filled"]').exists()).toBe(true)
  })

  it('课堂时序按时刻成表，摊分出来的分钟明确标注', () => {
    const sheet = mount(LessonDossierSheet, { props: { dossier: rich } })
    const rows = sheet.findAll('[data-rubric="timeline"] tbody tr')

    expect(rows).toHaveLength(3)
    // 教师只给了「学习者行动」15 分钟，其余 30 分钟按环节角色摊完，首尾相接到 45。
    expect(rows[0]!.text()).toContain('0–8')
    expect(rows[0]!.text()).toContain('本节任务')
    expect(rows[2]!.text()).toContain('30–45')
    expect(rows[2]!.text()).toContain('学习者行动')
    // 教师填的 15 分钟不标注，摊出来的要标注，教师能区分哪些是自己定的。
    expect(rows[2]!.text()).not.toContain('按课时摊分')
    expect(rows[0]!.text()).toContain('按课时摊分')
    expect(sheet.find('[data-rubric="timeline"] thead').text()).toContain('教师动作')
  })

  it('对照矩阵把知识点连到环节、能力、掌握标准与课堂证据，缺口单独点名', () => {
    const richRow = mount(LessonDossierSheet, { props: { dossier: rich } })
      .find('[data-rubric="alignment"] tbody tr')
    expect(richRow.text()).toContain('线性组合')
    expect(richRow.text()).toContain('核心教学')
    expect(richRow.text()).toContain('能写出目标向量的系数组合')
    expect(richRow.text()).toContain('独立完成两组分解')
    expect(richRow.attributes('data-gap')).toBe('false')

    const sparseRow = mount(LessonDossierSheet, { props: { dossier: sparse } })
      .find('[data-rubric="alignment"] tbody tr')
    // 缺口用「没有落点」措辞，而不是「待补充」——后者会被当成排版占位读过去。
    expect(sparseRow.attributes('data-gap')).toBe('true')
    expect(sparseRow.text()).toContain('无教学环节承载')
    expect(sparseRow.text()).toContain('未写掌握标准')
    expect(sparseRow.text()).toContain('无课堂证据')
  })

  it('知识点可点开知识库，未编译的知识点不可点', () => {
    const sheet = mount(LessonDossierSheet, { props: { dossier: rich } })
    const button = sheet.get('[data-rubric="knowledge"] tbody th button')
    expect(button.attributes('disabled')).toBeUndefined()
    button.trigger('click')
    expect(sheet.emitted('open-knowledge')?.[0]).toEqual(['k-1'])

    const pending = mount(LessonDossierSheet, { props: { dossier: sparse } })
      .get('[data-rubric="knowledge"] tbody th button')
    expect(pending.attributes('disabled')).toBeDefined()
  })
})

describe('教案统一模板：接入教案页面', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('读态用统一模板替代分块视图，并提供打印入口', async () => {
    const wrapper = mountSection('section-1')

    expect(wrapper.find('.lesson-dossier').exists()).toBe(true)
    // 分块视图只在编辑态或拿不到 dossier 时出现，避免同一份内容渲染两遍。
    expect(wrapper.find('.generation-lesson-plan__flow').exists()).toBe(false)

    const print = vi.fn()
    vi.stubGlobal('print', print)
    await wrapper.get('.generation-lesson-plan__print-button').trigger('click')
    expect(print).toHaveBeenCalledTimes(1)
    vi.unstubAllGlobals()
  })

  it('切到下一节仍是同一张表，栏目标题逐字相同', async () => {
    const first = mountSection('section-1')
    const second = mountSection('section-2')

    const headings = (wrapper: ReturnType<typeof mountSection>) => wrapper
      .findAll('.lesson-dossier__rubric h4')
      .map(item => item.text())

    expect(headings(first)).toEqual(headings(second))
    expect(first.find('.lesson-dossier__title h3').text()).toBe('向量的线性组合')
    expect(second.find('.lesson-dossier__title h3').text()).toBe('张成空间')
  })

  it('全课视图给出各节颗粒度对照，异常节被点名', async () => {
    const wrapper = mount(GenerationLessonPlan, {
      props: { nodes, plan: plan(), activeNodeId: 'section-1' },
    })

    const panel = wrapper.get('.generation-lesson-plan__consistency')
    expect(panel.text()).toContain('各节栏目结构与颗粒度对照')
    expect(panel.text()).toContain('全部小节栏目结构一致')

    const rows = panel.findAll('.generation-lesson-plan__consistency-table tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0]!.text()).toContain('向量的线性组合')
    // 已填栏目数并排显示，教师一眼能看出哪一节内容缺得多。
    expect(rows[0]!.text()).toContain('11/11')
    expect(rows[1]!.text()).toContain('7/11')

    const coverage = panel.findAll('.generation-lesson-plan__consistency-coverage li')
    expect(coverage.map(item => item.text())).toContain('课堂时序2/2')
    expect(coverage.map(item => item.text())).toContain('课后作业1/2')
  })
})

describe('教案统一模板：英文模式', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('英文模式下模板骨架没有中文残留，也没有原始 key', async () => {
    const messages = await import('../../../public/locales/en/translation.json')
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => messages.default,
    }) as never
    await setLocale('en')

    const sheet = mount(LessonDossierSheet, { props: { dossier: sparse } })
    const chrome = [
      ...sheet.findAll('.lesson-dossier__rubric h4'),
      ...sheet.findAll('.lesson-dossier__rubric > header p'),
      ...sheet.findAll('.lesson-dossier__table thead th'),
      ...sheet.findAll('.lesson-dossier__facts dt'),
      ...sheet.findAll('.lesson-dossier__empty'),
    ].map(item => item.text())

    expect(chrome.length).toBeGreaterThan(10)
    expect(chrome.filter(text => /[一-鿿]/.test(text))).toEqual([])
    expect(chrome.filter(text => text.includes('courseGeneration'))).toEqual([])

    await setLocale('zh')
  })
})
