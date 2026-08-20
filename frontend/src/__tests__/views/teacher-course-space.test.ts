import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const httpMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: httpMock }))

import TeacherCourseSpaceView from '@/views/TeacherCourseSpaceView.vue'
import { setLocale } from '@/shared/i18n'
import zhMessages from '../../../public/locales/zh/translation.json'

const coursePackage = {
  package_id: 'package-1', course_id: '', course_name: '数据结构', academic_year: '2026-2027', term: '秋季', asset_count: 0,
  assets: [], entries: [],
}
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/courses', name: 'course-library', component: { template: '<div />' } },
    { path: '/course/:courseId/learn/:nodeId?', name: 'learning', component: { template: '<div />' } },
    { path: '/course/:courseId/ppt', name: 'ppt-workspace', component: { template: '<div />' } },
  ],
})

describe('TeacherCourseSpaceView', () => {
  beforeEach(async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => zhMessages })))
    const pinia = createPinia()
    setActivePinia(pinia)
    httpMock.get.mockReset().mockImplementation((url: string) => Promise.resolve({ data: url === '/api/teacher-course-spaces' ? [coursePackage] : coursePackage }))
    await router.push('/courses')
    await router.isReady()
    await setLocale('zh')
  })

  it('以文件树、文件列表和右侧状态栏组成单一课程空间', async () => {
    const pinia = createPinia()
    const wrapper = mount(TeacherCourseSpaceView, {
      global: {
        plugins: [pinia, router],
        stubs: { ElDialog: true, ElTree: { template: '<div class="workspace-tree" />' }, ElDropdown: true, ElDropdownMenu: true, ElDropdownItem: true },
      },
    })
    await flushPromises()

    expect(wrapper.get('.file-layout')).toBeTruthy()
    expect(wrapper.get('.file-tree-pane').text()).toContain('课程文件夹')
    expect(wrapper.get('.file-tree-pane').text()).not.toContain('数据结构')
    expect(wrapper.get('.file-list-pane').text()).toContain('课程大纲')
    expect(wrapper.get('.folder-navigation')).toBeTruthy()
    expect(wrapper.find('.course-assembly-note').exists()).toBe(false)
    await wrapper.findAll('.file-row')[0]!.trigger('click')
    expect(wrapper.get('.file-inspector').text()).toContain('内容来源')
    expect(wrapper.get('.file-inspector').text()).not.toContain('结构化同源')
  })

  it('为五类教学资产提供不同的新建表单', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/TeacherCourseSpaceView.vue'), 'utf8')
    const storeSource = readFileSync(resolve(process.cwd(), 'src/stores/teacherLessonAuthoring.ts'), 'utf8')
    expect(source).toContain("type CreateType = 'outline' | 'lesson_plan' | 'material' | 'ppt' | 'practice' | 'folder'")
    expect(source).toContain("createType === 'lesson_plan'")
    expect(source).toContain("createType === 'ppt'")
    expect(source).toContain("createType === 'practice'")
    expect(source).toContain('class="source-picker"')
    expect(source).toContain('class="ppt-origin-picker"')
    expect(source).toContain('@command="handleCreateCommand"')
    expect(source).toContain('function handleCreateCommand(command: unknown)')
    expect(source).toContain("pptImportAction: 'derive_plan'")
    expect(storeSource).toContain('source_package_id: source?.packageId')
    expect(zhMessages.courseFiles.form.derivePlanFromPpt).toContain('生成教案草稿')
    expect(zhMessages.courseFiles.relationship.pptUploaded).toContain('保留原件')
  })
})
