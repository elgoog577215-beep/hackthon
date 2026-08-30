import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
const rebuildMock = vi.hoisted(() => vi.fn(async () => ({ status: 'completed' })))
vi.mock('@/utils/http', () => ({
  default: httpMock,
  getTeacherIdentity: () => 'teacher-test',
  teacherRequestConfig: (config = {}) => config,
}))
vi.mock('@/utils/question-bank-rebuild', () => ({ runQuestionBankRebuild: rebuildMock }))

import TeacherCourseSpaceView from '@/views/TeacherCourseSpaceView.vue'
import { setLocale } from '@/shared/i18n'
import { useCourseStore } from '@/stores/course'
import { useTeacherLessonAuthoringStore } from '@/stores/teacherLessonAuthoring'
import { useTeachingCalendarStore } from '@/stores/teachingCalendar'
import zhMessages from '../../../public/locales/zh/translation.json'

const coursePackage = {
  package_id: 'package-1', course_id: 'course-1', course_name: '数据结构', academic_year: '2026-2027', term: '秋季', asset_count: 0,
  assets: [], entries: [], preparation_status: 'completed',
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
      if (url === '/api/courses/course-1/companion-documents') return Promise.resolve({ data: { templates: [], documents: [] } })
      return Promise.resolve({ data: coursePackage })
    })
    httpMock.post.mockReset()
    httpMock.patch.mockReset().mockResolvedValue({ data: coursePackage })
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
    expect(wrapper.findAll('.file-row').map(row => row.text())).toEqual(expect.arrayContaining([
      expect.stringContaining('教学大纲'),
      expect.stringContaining('分讲教案'),
      expect.stringContaining('讲义'),
      expect.stringContaining('PPT'),
      expect.stringContaining('其他课程文件'),
      expect.stringContaining('课程资料'),
      expect.stringContaining('回收站'),
    ]))
    expect(wrapper.findAll('.file-row')).toHaveLength(7)
    expect(wrapper.get('.folder-navigation')).toBeTruthy()
    expect(wrapper.get('.folder-navigation').attributes('aria-label')).toBe('课程文件夹')
    expect(wrapper.get('.file-table__head').text()).toContain('修改时间')
    expect(wrapper.get('.file-table__head').text()).toContain('大小')
    expect(wrapper.findAll('.sort-button')).toHaveLength(5)
    expect(wrapper.findAll('[role="columnheader"]')[1]!.attributes('aria-sort')).toBe('ascending')
    await wrapper.findAll('.sort-button')[0]!.trigger('click')
    expect(wrapper.findAll('[role="columnheader"]')[1]!.attributes('aria-sort')).toBe('descending')
    expect(wrapper.findAll('.file-name small')).toHaveLength(1)
    expect(wrapper.get('.file-inspector').text()).toContain('全课文件')
    expect(wrapper.get('.inspector-overview').text()).toContain('修改时间')
    expect(wrapper.get('.inspector-actions').text()).toContain('导出整课文件')
    expect(wrapper.find('.course-assembly-note').exists()).toBe(false)
    await wrapper.findAll('.file-row').find(row => row.text().includes('教学大纲'))!.trigger('click')
    await wrapper.findAll('.file-row').find(row => row.text().includes('大纲'))!.trigger('click')
    expect(wrapper.get('.inspector-overview').text()).toContain('母文件')
    expect(wrapper.get('.inspector-overview').text()).toContain('参考原始文件')
    expect(wrapper.get('.inspector-overview').text()).not.toContain('生成文件')
    expect(wrapper.get('.inspector-overview').text()).not.toContain('文件大小')
    expect(wrapper.get('.inspector-overview').text()).not.toContain('修改时间')
    expect(wrapper.get('.inspector-actions').text()).not.toContain('可执行操作')
    expect(wrapper.get('.inspector-actions').text()).not.toContain('删除')
    expect(wrapper.emitted('createOutline')).toBeFalsy()
    await wrapper.get('.inspector-actions .primary').trigger('click')
    expect(wrapper.emitted('createOutline')).toBeTruthy()

    await wrapper.get('.list-toolbar nav button').trigger('click')
    await wrapper.findAll('.file-row').find(row => row.text().includes('其他课程文件'))!.trigger('click')
    const calendarRow = wrapper.findAll('.file-row').find(row => row.text().includes('教学日历文件'))!
    expect(calendarRow.text()).toContain('未生成')
    await calendarRow.trigger('click')
    expect(wrapper.get('.file-inspector').text()).toContain('母文件')
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
    expect(wrapper.get('.category-navigation').text()).toContain('大纲')
    expect(wrapper.get('.category-navigation').text()).not.toContain('教学日历')
    expect(wrapper.get('.category-navigation').text()).toContain('教案')
    expect(wrapper.get('.category-navigation').text()).toContain('讲义')
    expect(wrapper.get('.category-navigation').text()).toContain('PPT')
    expect(wrapper.get('.category-navigation').text()).not.toContain('练习')
    expect(wrapper.find('.category-table').exists()).toBe(false)
    expect(wrapper.get('.category-detail-pane')).toBeTruthy()
    expect(wrapper.get('.category-navigation').text()).toContain('课程生产')
    expect(wrapper.get('.category-progress').text()).toContain('备课进度')
    expect(wrapper.get('.workbench-brief-bar').text()).toContain('课程定调')
    expect(wrapper.get('.category-console').text()).toContain('开始生成大纲')
    expect(wrapper.get('.category-navigation').text()).not.toContain('0/0')
    await wrapper.get('.workbench-settings-button').trigger('click')
    expect(wrapper.emitted('openAssistant')).toBeTruthy()
  })

  it('待准备的新课程仍显示正常文件系统，不再替换成整页导入界面', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const pendingPackage = { ...coursePackage, preparation_status: 'pending' }
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [pendingPackage] })
      if (url === '/api/teacher-course-spaces/package-1') return Promise.resolve({ data: pendingPackage })
      if (url === '/api/courses/course-1/teaching-calendar') return Promise.resolve({ data: emptyTeachingCalendar })
      if (url === '/api/teacher/courses/course-1/lesson-authoring') return Promise.resolve({ data: { outline_revision_id: '', lessons: [], jobs: [] } })
      if (url === '/api/courses/course-1/question-bank') return Promise.resolve({ data: { items: [] } })
      if (url === '/api/courses/course-1/companion-documents') return Promise.resolve({ data: { templates: [], documents: [] } })
      return Promise.resolve({ data: {} })
    })
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: { plugins: [pinia, router], stubs: { ElDialog: true } },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    expect(wrapper.find('.material-preparation').exists()).toBe(false)
    expect(wrapper.get('.file-layout')).toBeTruthy()
  })

  it('按对象类型提供文件夹、固定资产和上传文件的安全操作', async () => {
    const pinia = createPinia()
    const packageWithAsset = {
      ...coursePackage,
      updated_at: '2026-08-22T08:00:00Z',
      asset_count: 2,
      assets: [{
        asset_id: 'asset-1', filename: '课堂案例.pdf', relative_path: '参考资料/课堂案例.pdf', extension: '.pdf', size_bytes: 2048,
        category: 'reference', document_type: 'lesson_plan', document_type_reason: 'AI 根据正文判断', classification_source: 'ai', classification_confidence: 0.86,
        course_alignment: { match: 'matched', confidence: 0.9, reason: '属于当前课程' }, structure_matches: [{ node_id: 'lesson-1', title: '第一讲 线性表', confidence: 0.9, reason: '内容对应第一讲' }],
        version_role: 'reference', version_reason: '案例资料', related_asset_ids: ['asset-2'], uploaded_at: '2026-08-22T08:00:00Z', updated_at: '2026-08-22T08:00:00Z',
      }, {
        asset_id: 'asset-2', filename: '第一讲课件.pptx', relative_path: '参考资料/第一讲课件.pptx', extension: '.pptx', size_bytes: 4096,
        category: 'reference', document_type: 'ppt', classification_source: 'hybrid', classification_confidence: 0.99, related_asset_ids: ['asset-1'], uploaded_at: '2026-08-22T08:00:00Z', updated_at: '2026-08-22T08:00:00Z',
      }],
      material_understanding: { status: 'ai_completed', missing_document_types: ['outline', 'script', 'question_bank'] },
      relationships: [{
        link_id: 'link-1', source_asset_id: 'asset-1', source_label: '课堂案例.pdf', target_id: 'managed:outline', target_type: 'outline', target_label: '课程大纲', role: 'reference',
      }],
    }
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [packageWithAsset] })
      if (url === '/api/teacher-course-spaces/package-1') return Promise.resolve({ data: packageWithAsset })
      if (url === '/api/courses/course-1/teaching-calendar') return Promise.resolve({ data: emptyTeachingCalendar })
      if (url === '/api/teacher/courses/course-1/lesson-authoring') return Promise.resolve({ data: { outline_revision_id: '', lessons: [], jobs: [] } })
      if (url === '/api/courses/course-1/question-bank') return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: {} })
    })
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: { plugins: [pinia, router], stubs: { ElDialog: true } },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    await wrapper.findAll('.file-row').find(row => row.text().includes('辅助资料'))!.trigger('click')
    await wrapper.findAll('.file-row').find(row => row.text().includes('其他资料'))!.trigger('click')
    expect(wrapper.find('.inspector-actions').exists()).toBe(false)
    const toolbarActions = wrapper.get('.folder-title__actions')
    expect(toolbarActions.findAll('button')).toHaveLength(2)
    expect(toolbarActions.text()).toContain('导入资料')
    expect(toolbarActions.text()).toContain('新建文件夹')
    await toolbarActions.get('.batch-import-button').trigger('click')
    expect(toolbarActions.get('.file-import-menu').text()).toContain('选择本地文件')
    expect(toolbarActions.get('.file-import-menu').text()).toContain('导入文件夹')

    const assetRow = wrapper.findAll('.file-row').find(row => row.text().includes('课堂案例.pdf'))!
    expect(assetRow.text()).toContain('教案')
    await assetRow.trigger('click')
    const actions = wrapper.get('.inspector-actions').text()
    expect(actions).toContain('预览')
    expect(actions).toContain('下载')
    expect(actions).not.toContain('移入回收站')
    expect(wrapper.get('.inspector-overview').text()).toContain('用于')
    expect(wrapper.get('.inspector-overview').text()).toContain('课程大纲')
    expect(wrapper.get('.inspector-overview').text()).not.toContain('文件大小')
    expect(wrapper.get('.inspector-overview').text()).not.toContain('修改时间')
    expect(wrapper.get('.inspector-overview').text()).toContain('AI 判断 · 86%')
    expect(wrapper.get('.inspector-overview').text()).toContain('第一讲 线性表')
    expect(wrapper.get('.inspector-overview').text()).toContain('参考资料')
    expect(wrapper.get('.relationship-list').text()).toContain('第一讲课件.pptx')
    expect((wrapper.get('.asset-type-select').element as HTMLSelectElement).value).toBe('lesson_plan')
    await wrapper.get('.asset-type-select').setValue('ppt')
    await flushPromises()
    expect(httpMock.patch).toHaveBeenCalledWith('/api/teacher-course-spaces/package-1/assets/asset-1', { document_type: 'ppt' }, {})

    await assetRow.trigger('contextmenu', { clientX: 420, clientY: 260 })
    await flushPromises()
    const contextMenu = document.body.querySelector<HTMLElement>('.file-context-menu')
    expect(contextMenu?.textContent).toContain('预览')
    expect(contextMenu?.textContent).toContain('下载')
    expect(contextMenu?.textContent).toContain('重命名')
    expect(contextMenu?.textContent).toContain('移动')
    expect(contextMenu?.textContent).toContain('移入回收站')
  })

  it('选中文件后才显示批量操作，并通过统一接口移动', async () => {
    const pinia = createPinia()
    const managedPackage = {
      ...coursePackage,
      asset_count: 2,
      assets: [
        { asset_id: 'asset-1', filename: '课堂案例.pdf', relative_path: '辅助资料/其他资料/课堂案例.pdf', extension: '.pdf', size_bytes: 2048, category: 'reference', document_type: 'other' },
        { asset_id: 'asset-2', filename: '课外阅读.pdf', relative_path: '辅助资料/其他资料/课外阅读.pdf', extension: '.pdf', size_bytes: 4096, category: 'reference', document_type: 'other' },
      ],
      entries: [{ kind: 'folder', path: '辅助资料/其他资料/课堂资料', name: '课堂资料', created_at: '2026-08-22T08:00:00Z' }],
      trash: [],
      trash_count: 0,
    }
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [managedPackage] })
      if (url === '/api/teacher-course-spaces/package-1') return Promise.resolve({ data: managedPackage })
      if (url === '/api/courses/course-1/teaching-calendar') return Promise.resolve({ data: emptyTeachingCalendar })
      if (url === '/api/teacher/courses/course-1/lesson-authoring') return Promise.resolve({ data: { outline_revision_id: '', lessons: [], jobs: [] } })
      if (url === '/api/courses/course-1/question-bank') return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: {} })
    })
    httpMock.post.mockResolvedValue({ data: managedPackage })
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: { plugins: [pinia, router], stubs: { ElDialog: true, Teleport: true } },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    await wrapper.findAll('.file-row').find(row => row.text().includes('辅助资料'))!.trigger('click')
    await wrapper.findAll('.file-row').find(row => row.text().includes('其他资料'))!.trigger('click')
    expect(wrapper.find('.selection-toolbar').exists()).toBe(false)
    const checkboxes = wrapper.findAll('.file-row input[type="checkbox"]')
    await checkboxes[0]!.setValue(true)
    await checkboxes[1]!.setValue(true)
    expect(wrapper.get('.selection-toolbar').text()).toContain('已选 2 项')
    expect(wrapper.get('.selection-toolbar').text()).toContain('移动')
    expect(wrapper.get('.selection-toolbar').text()).toContain('移入回收站')

    await wrapper.findAll('.selection-toolbar button').find(button => button.text().includes('移动'))!.trigger('click')
    await wrapper.get('.file-operation-dialog select').setValue('辅助资料/其他资料/课堂资料')
    await wrapper.get('.file-operation-dialog button.primary').trigger('click')
    await flushPromises()
    expect(httpMock.post).toHaveBeenCalledWith('/api/teacher-course-spaces/package-1/batch', {
      action: 'move',
      ids: ['asset-1', 'asset-2'],
      destination_path: '辅助资料/其他资料/课堂资料',
    }, {})
  })

  it('回收站按需出现，并支持批量还原', async () => {
    const pinia = createPinia()
    const packageWithTrash = {
      ...coursePackage,
      trash_count: 1,
      trash: [{
        trash_id: 'trash-1', kind: 'asset', original_path: '辅助资料/其他资料/旧讲义.pdf', name: '旧讲义.pdf',
        extension: '.pdf', size_bytes: 2048, item_count: 1, deleted_at: '2026-08-22T08:00:00Z',
      }],
    }
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [packageWithTrash] })
      if (url === '/api/teacher-course-spaces/package-1') return Promise.resolve({ data: packageWithTrash })
      if (url === '/api/courses/course-1/teaching-calendar') return Promise.resolve({ data: emptyTeachingCalendar })
      if (url === '/api/teacher/courses/course-1/lesson-authoring') return Promise.resolve({ data: { outline_revision_id: '', lessons: [], jobs: [] } })
      if (url === '/api/courses/course-1/question-bank') return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: {} })
    })
    httpMock.post.mockResolvedValue({ data: { ...coursePackage, trash: [], trash_count: 0 } })
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: { plugins: [pinia, router], stubs: { ElDialog: true } },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    expect(wrapper.get('.recycle-bin-button').text()).toContain('回收站')
    await wrapper.get('.recycle-bin-button').trigger('click')
    expect(wrapper.get('.folder-title h2').text()).toBe('回收站')
    expect(wrapper.get('.file-row').text()).toContain('旧讲义.pdf')
    await wrapper.get('.file-row').trigger('click')
    expect(wrapper.get('.file-inspector').text()).toContain('原位置')
    await wrapper.get('.file-row input[type="checkbox"]').setValue(true)
    await wrapper.findAll('.selection-toolbar button').find(button => button.text().includes('还原'))!.trigger('click')
    await flushPromises()
    expect(httpMock.post).toHaveBeenCalledWith('/api/teacher-course-spaces/package-1/batch', { action: 'restore', ids: ['trash-1'] }, {})
  })

  it('在文件系统中继续批量导入，并把整批资料交给同一识别接口', async () => {
    const pinia = createPinia()
    const importedPackage = {
      ...coursePackage,
      asset_count: 2,
      assets: [
        { asset_id: 'asset-plan', filename: '第一讲教案.docx', relative_path: '第一讲教案.docx', extension: '.docx', size_bytes: 1200, category: 'reference', document_type: 'lesson_plan' },
        { asset_id: 'asset-ppt', filename: '第一讲课件.pptx', relative_path: '第一讲课件.pptx', extension: '.pptx', size_bytes: 3200, category: 'reference', document_type: 'ppt' },
      ],
    }
    httpMock.post.mockResolvedValueOnce({
      data: {
        package: importedPackage,
        outcomes: [
          { asset_id: 'asset-plan', relative_path: '第一讲教案.docx', outcome: 'imported' },
          { asset_id: 'asset-ppt', relative_path: '第一讲课件.pptx', outcome: 'imported' },
        ],
      },
    })
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: { plugins: [pinia, router], stubs: { ElDialog: true } },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    expect(wrapper.get('.batch-import-button').text()).toContain('导入资料')
    expect(wrapper.get('input[webkitdirectory]').attributes('multiple')).toBeDefined()
    const input = wrapper.get('input[type="file"][multiple]:not([webkitdirectory])')
    const files = [
      new File(['plan'], '第一讲教案.docx'),
      new File(['ppt'], '第一讲课件.pptx'),
    ]
    Object.defineProperty(input.element, 'files', { configurable: true, value: files })
    await input.trigger('change')
    await flushPromises()

    expect(httpMock.post).toHaveBeenCalledTimes(1)
    expect(httpMock.post.mock.calls[0]?.[0]).toBe('/api/teacher-course-spaces/package-1/imports')
    const data = httpMock.post.mock.calls[0]?.[1] as FormData
    expect(data.getAll('files')).toHaveLength(2)
    expect(data.getAll('relative_paths')).toEqual(['第一讲教案.docx', '第一讲课件.pptx'])
  })

  it('教学日历保存后回写文件状态，并可从文件视图导出 DOCX', async () => {
    const pinia = createPinia()
    setActivePinia(pinia)
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: {
        plugins: [pinia, router],
        stubs: { ElDialog: true },
      },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    await wrapper.findAll('.file-row').find(row => row.text().includes('其他课程文件'))!.trigger('click')
    const calendarRow = wrapper.findAll('.file-row').find(row => row.text().includes('教学日历文件'))!
    expect(calendarRow.text()).toContain('未生成')
    await calendarRow.trigger('click')

    const readyCalendar = {
      ...emptyTeachingCalendar,
      revision: 3,
      status: 'ready',
      updated_at: '2026-08-22T08:00:00Z',
      sessions: [{
        session_id: 'session-1', lesson_unit_id: 'lesson-1', sequence: 1,
        date: '2026-09-01', start_time: '08:00', end_time: '09:40',
        content_summary: '第一讲', requirements: '', location: '教学楼 101', teacher_name: '张老师',
        teaching_type: '讲授', group_code: '1 班', credit_hours: 2, notes: '', status: 'scheduled', source: 'outline',
      }],
    }
    useTeachingCalendarStore(pinia).calendar = readyCalendar as any
    await flushPromises()

    expect(wrapper.get('.inspector-status').text()).toContain('已就绪')
    const exportButton = wrapper.findAll('.inspector-actions button').find(button => button.text() === '导出')!
    expect(exportButton).toBeTruthy()

    const nativeUrl = URL
    const createObjectUrl = vi.fn(() => 'blob:teaching-calendar')
    const revokeObjectUrl = vi.fn()
    vi.stubGlobal('URL', { createObjectURL: createObjectUrl, revokeObjectURL: revokeObjectUrl })
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined)
    httpMock.get.mockResolvedValueOnce({ data: new Blob(['calendar']) })
    vi.useFakeTimers()
    await exportButton.trigger('click')
    await flushPromises()
    vi.runAllTimers()

    expect(httpMock.get).toHaveBeenLastCalledWith('/api/courses/course-1/teaching-calendar/export', {
      params: { format: 'docx', revision: 3 },
      responseType: 'blob',
    })
    expect(createObjectUrl).toHaveBeenCalledOnce()
    expect(revokeObjectUrl).toHaveBeenCalledWith('blob:teaching-calendar')
    expect(anchorClick).toHaveBeenCalledOnce()
    vi.useRealTimers()
    vi.stubGlobal('URL', nativeUrl)
    anchorClick.mockRestore()
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

    const outline = wrapper.findAll('.category-group__button').find(button => button.text().includes('大纲'))!
    expect(outline.text()).toContain('0/1')
    expect(outline.text()).not.toContain('已完成')
    expect(wrapper.get('.category-console').text()).toContain('开始生成大纲')
    await wrapper.get('.category-console__actions .primary').trigger('click')
    expect(wrapper.emitted('createOutline')).toBeTruthy()
  })

  it('把固定课程资产直接作为入口，教师资料统一从导入菜单进入', () => {
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
    expect(source).toContain('class="file-import-menu"')
    expect(source).not.toContain("t('courseFiles.addMaterial')")
    expect(source).toContain(':data-role="assetRole(node)"')
    expect(source).toContain('function toggleSort(key: SortKey)')
    expect(source).not.toContain('<small>{{ displaySubtitle')
    expect(source).toContain('function handleNodeClick(node: WorkspaceNode, event?: MouseEvent)')
    expect(source).toContain('function selectNode(node: WorkspaceNode)')
    expect(source).toContain("@dblclick=\"node.kind !== 'folder' && !node.trashItem && primaryAction(node)\"")
    expect(source).toContain("node.status === 'missing' ? t('courseFiles.createContent')")
    expect(source).toContain("? emit('openTasks')")
    expect(source).toContain("id: `ppt:${lesson.lesson_unit_id}`")
    expect(source).toContain("id: 'managed:teaching-calendar'")
    expect(source).not.toContain('ppt || !uploadedPpts.length')
    expect(source).toContain("if (type === 'folder' && targetFolder?.kind !== 'folder') return")
    expect(source).toContain('@click="handleNodeClick(node, $event)"')
    expect(source).toContain("t('courseFiles.noSearchResults')")
    expect(source).toContain("emit('createOutline')")
    expect(source).toContain("pptImportAction: 'derive_plan'")
    expect(storeSource).toContain('source_package_id: source?.packageId')
    expect(zhMessages.courseFiles.status.missing).toBe('未生成')
    expect(zhMessages.courseFiles.assetRole.deliverable).toBe('教务材料')
    expect(zhMessages.courseFiles.assetRole.logic).toBe('课程逻辑文件')
    expect(zhMessages.courseFiles.assetRole.auxiliary).toBe('辅助资料原件')
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
    const handoutLessons = [{
      lesson_unit_id: 'lesson-1', number: 1, title: '内存管理', duration_minutes: 45, sections: [],
      arrangement: { blocks: [], confirmed: true, source_state: 'current' },
      script: {
        current_revision_id: 'handout-1', confirmed_revision_id: 'handout-1',
        source_lesson_plan_revision_id: 'plan-1', source_state: 'current',
        ready: true, confirmed: true, confirmed_at: '2026-08-30T00:00:00Z', sections: [],
      },
      plan: {
        lesson_unit_id: 'lesson-1', working_revision_id: 'plan-1', confirmed_revision_id: 'plan-1',
        source_state: 'current', revisions: [], ppt_assets: [],
      },
    }] as any
    useTeacherLessonAuthoringStore().lessons = handoutLessons
    httpMock.get.mockImplementation((url: string) => {
      if (url === '/api/teacher-course-spaces') return Promise.resolve({ data: [coursePackage] })
      if (url === '/api/teacher-course-spaces/package-1') return Promise.resolve({ data: coursePackage })
      if (url === '/api/teacher/courses/course-1/lesson-authoring') return Promise.resolve({ data: { outline_revision_id: 'revision-1', lessons: handoutLessons, jobs: [] } })
      if (url === '/api/courses/course-1/teaching-calendar') return Promise.resolve({ data: emptyTeachingCalendar })
      if (url === '/api/courses/course-1/question-bank') return Promise.resolve({ data: { items: [] } })
      return Promise.resolve({ data: {} })
    })
    const wrapper = mount(TeacherCourseSpaceView, {
      props: { courseId: 'course-1', courseTitle: '数据结构' },
      global: {
        plugins: [pinia, router],
        stubs: { ElDialog: true },
      },
    })
    mountedWrappers.push(wrapper)
    await flushPromises()

    await wrapper.findAll('.file-row').find(row => row.text().includes('讲义'))!.trigger('click')
    const contentRow = wrapper.findAll('.file-row').find(row => row.text().includes('内存管理'))
    expect(contentRow?.text()).toContain('讲义')
    expect(contentRow?.text()).toContain('已就绪')
    await contentRow!.trigger('click')
    expect(router.currentRoute.value.name).toBe('course-workspace')
    await wrapper.get('.inspector-actions .primary').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('openScript')?.[0]).toEqual(['lesson-1'])
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

    await wrapper.findAll('.file-row').find(row => row.text().includes('其他课程文件'))!.trigger('click')
    await wrapper.findAll('.file-row').find(row => row.text().includes('题库'))!.trigger('click')
    await wrapper.findAll('.file-row').find(row => row.text().includes('分讲练习'))!.trigger('click')
    await wrapper.findAll('.file-row').find(row => row.text().includes('内存管理'))!.trigger('click')
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
