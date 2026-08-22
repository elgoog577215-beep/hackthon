import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
const rebuildMock = vi.hoisted(() => vi.fn(async () => ({ status: 'completed' })))
vi.mock('@/utils/http', () => ({ default: httpMock, getTeacherIdentity: () => 'teacher-test' }))
vi.mock('@/utils/question-bank-rebuild', () => ({ runQuestionBankRebuild: rebuildMock }))

import TeacherCourseSpaceView from '@/views/TeacherCourseSpaceView.vue'
import { setLocale } from '@/shared/i18n'
import { useCourseStore } from '@/stores/course'
import { useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'
import zhMessages from '../../../public/locales/zh/translation.json'

const coursePackage = {
  package_id: 'package-1', course_id: 'course-1', course_name: '数据结构', academic_year: '2026-2027', term: '秋季', asset_count: 0,
  assets: [], entries: [],
}
const emptyTeachingCalendar = {
  schema_version: 'teaching_calendar_v1', course_id: 'course-1', course_title: '数据结构', academic_year: '2026-2027', term: '秋季', timezone: 'Asia/Shanghai',
  status: 'draft', source_outline_revision: '', revision: 0, sessions: [], created_at: '', updated_at: '',
}
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/courses', name: 'course-library', component: { template: '<div />' } },
    { path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: { template: '<div />' } },
    { path: '/course/:courseId/ppt', name: 'ppt-workspace', component: { template: '<div />' } },
    { path: '/course/:courseId/workspace/:mode', name: 'course-workspace', component: { template: '<div />' } },
  ],
})
const mountedWrappers: Array<ReturnType<typeof mount>> = []

describe('TeacherCourseSpaceView', () => {
  afterEach(() => {
    mountedWrappers.splice(0).forEach(wrapper => wrapper.unmount())
  })

  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    const pinia = createPinia()
    setActivePinia(pinia)
    httpMock.get.mockReset().mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [coursePackage] })
      if (url === '/api/courses/course-1/teaching-calendar') return Promise.resolve({ data: emptyTeachingCalendar })
      if (url === '/api/teacher/courses/course-1/lesson-authoring') return Promise.resolve({ data: { outline_revision_id: '', lessons: [], jobs: [] } })
      if (url === '/api/courses/course-1/question-bank') return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: coursePackage })
    })
    rebuildMock.mockClear()
    await router.push('/courses')
    await router.isReady()
    await setLocale('zh')
  })

  it('以文件树、文件列表和右侧状态栏组成单一课程空间', async () => {
    const pinia = createPinia()
    const wrapper = mount(TeacherCourseSpaceView, {
      global: {
        plugins: [pinia, router],
        stubs: { ElDialog: true },
      },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    expect(wrapper.get('.file-layout')).toBeTruthy()
    expect(wrapper.get('.file-tree-pane').text()).toContain('课程文件夹')
    expect(wrapper.get('.file-tree-pane').text()).not.toContain('数据结构')
    expect(wrapper.get('.file-list-pane').text()).toContain('课程大纲')
    expect(wrapper.get('.folder-navigation')).toBeTruthy()
    expect(wrapper.get('.folder-navigation').attributes('aria-label')).toBe('课程文件夹')
    expect(wrapper.get('.file-table__head').text()).toContain('修改时间')
    expect(wrapper.get('.file-table__head').text()).toContain('大小')
    expect(wrapper.findAll('.sort-button')).toHaveLength(5)
    expect(wrapper.findAll('[role="columnheader"]')[0]!.attributes('aria-sort')).toBe('ascending')
    await wrapper.findAll('.sort-button')[0]!.trigger('click')
    expect(wrapper.findAll('[role="columnheader"]')[0]!.attributes('aria-sort')).toBe('descending')
    expect(wrapper.find('.file-name small').exists()).toBe(false)
    expect(wrapper.get('.file-inspector').text()).toContain('全课文件')
    expect(wrapper.find('.course-assembly-note').exists()).toBe(false)
    await wrapper.findAll('.file-row').find(row => row.text().includes('课程大纲'))!.trigger('click')
    expect(wrapper.get('.inspector-overview').text()).toContain('来源')
    expect(wrapper.get('.inspector-overview').text()).toContain('用于')
    expect(wrapper.get('.inspector-overview').text()).not.toContain('文件大小')
    expect(wrapper.get('.inspector-overview').text()).not.toContain('修改时间')
    expect(wrapper.emitted('createOutline')).toBeFalsy()
    await wrapper.get('.inspector-actions .primary').trigger('click')
    expect(wrapper.emitted('createOutline')).toBeTruthy()

    const calendarRow = wrapper.findAll('.file-row').find(row => row.text().includes('教学日历'))!
    expect(calendarRow.text()).toContain('未生成')
    await calendarRow.trigger('click')
    expect(wrapper.get('.file-inspector').text()).toContain('学校排课、课次同步与正式文件导出')
    await wrapper.get('.inspector-actions .primary').trigger('click')
    expect(wrapper.emitted('openTeachingCalendar')).toBeTruthy()

    await wrapper.get('.list-search input').setValue('__missing_file__')
    expect(wrapper.get('.file-empty').text()).toContain('没有找到匹配文件')
    expect(wrapper.get('.file-empty').text()).not.toContain('这个文件夹还是空的')
    await wrapper.get('.file-empty button').trigger('click')
    expect((wrapper.get('.list-search input').element as HTMLInputElement).value).toBe('')

    expect(wrapper.find('.workspace-viewbar').exists()).toBe(false)
    expect(wrapper.get('.standalone-header').find('.workspace-view-switch').exists()).toBe(true)
    await wrapper.findAll('.workspace-view-switch button')[0]!.trigger('click')
    expect(wrapper.get('.category-layout')).toBeTruthy()
    expect(wrapper.findAll('.category-navigation nav button')).toHaveLength(4)
    expect(wrapper.get('.category-navigation').text()).toContain('课程大纲')
    expect(wrapper.get('.category-navigation').text()).not.toContain('教学日历')
    expect(wrapper.get('.category-navigation').text()).toContain('教案')
    expect(wrapper.get('.category-navigation').text()).toContain('正文')
    expect(wrapper.get('.category-navigation').text()).toContain('PPT')
    expect(wrapper.get('.category-navigation').text()).not.toContain('练习')
    expect(wrapper.find('.category-table').exists()).toBe(false)
    expect(wrapper.get('.category-detail-pane')).toBeTruthy()
    expect(wrapper.get('.category-navigation').text()).toContain('课程生产')
    expect(wrapper.get('.category-progress').text()).toContain('备课进度')
    expect(wrapper.get('.workbench-brief-bar').text()).toContain('课程定调')
    expect(wrapper.get('.category-console').text()).toContain('开始生成课程大纲')
    expect(wrapper.get('.category-navigation').text()).not.toContain('0/0')
    await wrapper.get('.workbench-settings-button').trigger('click')
    expect(wrapper.emitted('openAssistant')).toBeTruthy()
  })

  it('分类视图在左侧展开课次，并在右侧直接显示所选内容', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    await router.push('/course/course-1/workspace/setup')
    const courseStore = useCourseStore()
    courseStore.currentDocumentRevision = 'document-revision-1'
    courseStore.nodes = [
      { node_id: 'lesson-1', parent_node_id: 'root', node_name: '第一讲 内存管理', node_level: 1, node_content: '内存管理正文', node_type: 'original' },
      { node_id: 'lesson-2', parent_node_id: 'root', node_name: '第二讲 垃圾回收', node_level: 1, node_content: '垃圾回收正文', node_type: 'original' },
    ] as any
    const lessons = [
      {
        lesson_unit_id: 'lesson-1', number: 1, title: '内存管理', duration_minutes: 45, sections: [],
        plan: {
          lesson_unit_id: 'lesson-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1', source_state: 'current', ppt_assets: [],
          revisions: [{ revision_id: 'plan-1', lesson_unit_id: 'lesson-1', source_outline_revision_id: 'outline-1', generation_source: 'ai', status: 'confirmed', warnings: [], plan: { objectives: ['理解引用计数'] }, actor: 'teacher', created_at: '2026-08-22T00:00:00Z' }],
        },
      },
      {
        lesson_unit_id: 'lesson-2', number: 2, title: '垃圾回收', duration_minutes: 45, sections: [],
        plan: {
          lesson_unit_id: 'lesson-2', working_revision_id: 'plan-2', confirmed_revision_id: 'plan-2', source_state: 'current', ppt_assets: [],
          revisions: [{ revision_id: 'plan-2', lesson_unit_id: 'lesson-2', source_outline_revision_id: 'outline-1', generation_source: 'ai', status: 'confirmed', warnings: [], plan: { teaching_process: ['讲解标记清除'] }, actor: 'teacher', created_at: '2026-08-22T00:00:00Z' }],
        },
      },
    ]
    useTeacherLessonAuthoringStore().lessons = lessons as any
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [coursePackage] })
      if (url === '/api/teacher-course-spaces/package-1') return Promise.resolve({ data: coursePackage })
      if (url === '/api/teacher/courses/course-1/lesson-authoring') return Promise.resolve({ data: { outline_revision_id: 'outline-1', lessons, jobs: [] } })
      if (url === '/api/courses/course-1/teaching-calendar') return Promise.resolve({ data: emptyTeachingCalendar })
      if (url === '/api/courses/course-1/question-bank') return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: {} })
    })

    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseTitle: '数据结构', workspaceView: 'categories' },
      global: {
        plugins: [pinia, router],
        stubs: {
          ElDialog: true,
          MarkdownRenderer: { props: ['content'], template: '<div class="markdown-renderer">{{ content }}</div>' },
        },
      },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    const lessonPlanCategory = wrapper.findAll('.category-group__button').find(button => button.text().includes('教案'))
    await lessonPlanCategory!.trigger('click')
    await flushPromises()
    expect(lessonPlanCategory!.attributes('aria-expanded')).toBe('true')
    expect(wrapper.findAll('.category-child')).toHaveLength(2)
    expect(wrapper.get('.category-detail-header h2').text()).toContain('内存管理')
    expect(wrapper.get('.category-document').text()).toContain('理解引用计数')
    expect(wrapper.find('.category-table').exists()).toBe(false)

    await wrapper.findAll('.category-child')[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.get('.category-detail-header h2').text()).toContain('垃圾回收')
    expect(wrapper.get('.category-document').text()).toContain('讲解标记清除')
  })

  it('空文档不能仅凭修订号伪装成大纲已完成', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const courseStore = useCourseStore()
    courseStore.currentDocumentRevision = 'empty-document-revision'
    courseStore.nodes = []
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseTitle: '物理', workspaceView: 'categories' },
      global: { plugins: [pinia, router], stubs: { ElDialog: true } },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    const outline = wrapper.findAll('.category-group__button').find(button => button.text().includes('课程大纲'))!
    expect(outline.text()).toContain('0/1')
    expect(outline.text()).not.toContain('已完成')
    expect(wrapper.get('.category-console').text()).toContain('开始生成课程大纲')
    await wrapper.get('.category-console__actions .primary').trigger('click')
    expect(wrapper.emitted('createOutline')).toBeTruthy()
  })

  it('把固定课程资产直接作为入口，教师文件只在资料目录添加', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/TeacherCourseSpaceView.vue'), 'utf8')
    const storeSource = readFileSync(resolve(process.cwd(), 'src/stores/teacherLessonAuthoring.ts'), 'utf8')
    expect(source).toContain("type CreateType = 'outline' | 'lesson_plan' | 'material' | 'ppt' | 'practice' | 'folder'")
    expect(source).toContain("createType === 'lesson_plan'")
    expect(source).toContain("createType === 'ppt'")
    expect(source).toContain("createType === 'practice'")
    expect(source).toContain('class="source-picker"')
    expect(source).toContain('class="ppt-origin-picker"')
    expect(source).not.toContain('class="new-button"')
    expect(source).not.toContain('<el-dropdown')
    expect(source).toContain('const canAddTeacherFiles = computed')
    expect(source).toContain("t('courseFiles.addMaterial')")
    expect(source).toContain(':data-role="assetRole(node)"')
    expect(source).toContain('function toggleSort(key: SortKey)')
    expect(source).not.toContain('<small>{{ displaySubtitle')
    expect(source).toContain('function handleNodeClick(node: WorkspaceNode)')
    expect(source).toContain('function selectNode(node: WorkspaceNode)')
    expect(source).toContain("@dblclick=\"node.kind !== 'folder' && primaryAction(node)\"")
    expect(source).toContain("node.status === 'missing' ? t('courseFiles.createContent')")
    expect(source).toContain("? emit('openTasks')")
    expect(source).toContain("id: `ppt:${lesson.lesson_unit_id}`")
    expect(source).toContain("id: 'managed:teaching-calendar'")
    expect(source).not.toContain('ppt || !uploadedPpts.length')
    expect(source).toContain("if (type === 'folder' && targetFolder?.kind !== 'folder') return")
    expect(source).toContain('@click="handleNodeClick(node)"')
    expect(source).toContain("t('courseFiles.noSearchResults')")
    expect(source).toContain("emit('createOutline')")
    expect(source).toContain("pptImportAction: 'derive_plan'")
    expect(storeSource).toContain('source_package_id: source?.packageId')
    expect(zhMessages.courseFiles.status.missing).toBe('未生成')
    expect(zhMessages.courseFiles.assetRole.required).toBe('课程必备')
    expect(zhMessages.courseFiles.assetRole.teacher).toBe('教师文件')
    expect(zhMessages.courseFiles.form.derivePlanFromPpt).toContain('生成教案草稿')
    expect(zhMessages.courseFiles.relationship.pptUploaded).toContain('保留原件')
  })

  it('把结构化正文投影为可打开和导出的课程资产', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    await router.push('/course/course-1/workspace/setup')
    const courseStore = useCourseStore()
    courseStore.currentDocumentRevision = 'revision-1'
    courseStore.nodes = [{
      node_id: 'lesson-1', parent_node_id: 'root', node_name: '第一讲 内存管理', node_level: 1,
      node_content: '# 引用计数\n\n正文内容', node_type: 'original',
      generation_status: 'completed', generated_chars: 15,
    }]
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: {
        plugins: [pinia, router],
        stubs: { ElDialog: true },
      },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    const lessonRow = wrapper.findAll('.file-row').find(row => row.text().includes('内存管理'))
    await lessonRow!.trigger('click')
    const contentRow = wrapper.findAll('.file-row').find(row => row.text().includes('正文'))
    expect(contentRow?.text()).toContain('正文')
    expect(contentRow?.text()).toContain('已就绪')
    await contentRow!.trigger('click')
    expect(router.currentRoute.value.name).toBe('course-workspace')
    await wrapper.get('.inspector-actions .primary').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('learning')
    expect(router.currentRoute.value.params.nodeId).toBe('lesson-1')
    expect(router.currentRoute.value.query.teacherPreview).toBe('1')
    expect(String(router.currentRoute.value.query.returnTo)).toContain('/workspace/setup')
    const source = readFileSync(resolve(process.cwd(), 'src/views/TeacherCourseSpaceView.vue'), 'utf8')
    expect(source).toContain('async function exportManagedNode')
    expect(zhMessages.courseFiles.relationship.content).toContain('不要求先生成实体文件')
  })

  it('课次练习文件只把范围交给学生预览题库本，不在教师文件区直接出题', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    await router.push('/course/course-1/workspace/setup')
    const courseStore = useCourseStore()
    courseStore.currentDocumentRevision = 'revision-1'
    courseStore.nodes = [
      { node_id: 'lesson-1', parent_node_id: 'root', node_name: '第一讲 内存管理', node_level: 1, node_content: '', node_type: 'original' },
      { node_id: 'section-1', parent_node_id: 'lesson-1', node_name: '1.1 引用计数', node_level: 2, node_content: '正文', node_type: 'original' },
    ] as any
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: { plugins: [pinia, router], stubs: { ElDialog: true } },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    await wrapper.findAll('.file-row').find(row => row.text().includes('内存管理'))!.trigger('click')
    await wrapper.findAll('.file-row').find(row => row.text().includes('练习'))!.trigger('click')
    await wrapper.get('.inspector-actions .primary').trigger('click')
    await flushPromises()
    const form = document.body.querySelector<HTMLFormElement>('.asset-form')
    expect(form).toBeTruthy()
    form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    expect(rebuildMock).not.toHaveBeenCalled()
    expect(wrapper.emitted('openPractice')?.[0]).toEqual(['lesson-1'])
  })
})
