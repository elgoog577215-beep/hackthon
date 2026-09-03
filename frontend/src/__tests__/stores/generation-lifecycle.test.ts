import { flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'
import { setLocale } from '@/shared/i18n'
import http, { setActiveRequestIdentityScope } from '@/utils/http'
import enMessages from '../../../public/locales/en/translation.json'
import zhMessages from '../../../public/locales/zh/translation.json'


describe('course generation lifecycle reconciliation', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
    localStorage.clear()
    setActiveRequestIdentityScope('learner')
    setActivePinia(createPinia())
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => ({
      ok: true,
      json: async () => String(input).includes('/en/') ? enMessages : zhMessages,
    })))
  })

  it('创建与恢复生成任务时保留课程类型', () => {
    const generation = useGenerationStore()
    const task = generation.createTask('job-project', 'course-project', '玻璃杯设计', {
      course_type: 'project',
    })

    expect(task.courseType).toBe('project')
    generation.persistGenerationState()

    setActivePinia(createPinia())
    const restoredGeneration = useGenerationStore()
    restoredGeneration.restoreGenerationState()
    expect(restoredGeneration.getTask('course-project')?.courseType).toBe('project')
  })

  it('目标草稿所有者不一致时退出生成态并保留唯一真实原因', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    const backendError = {
      response: {
        status: 404,
        data: {
          detail: {
            code: 'teacher_course_draft_unavailable',
            message: '课程草稿不存在或不属于当前教师',
          },
        },
      },
    }
    const post = vi.spyOn(http, 'post').mockRejectedValue(backendError)
    const genericToast = vi.spyOn(ElMessage, 'error')

    const result = await generation.startSmartGeneration(
      '理论力学',
      { target_course_id: 'course-1' },
      'teacher',
    )

    expect(result).toBeNull()
    expect(post).toHaveBeenCalledWith(
      '/api/course-generation/generate',
      expect.objectContaining({ subject: '理论力学', target_course_id: 'course-1' }),
      { identityScope: 'teacher', silentError: true },
    )
    expect(generation.isGenerating).toBe(false)
    expect(generation.generationStatus).toBe('error')
    expect(generation.failureReport?.failed_nodes[0]).toMatchObject({
      error: '课程草稿不存在或不属于当前教师',
      error_code: 'teacher_course_draft_unavailable',
      retryable: false,
    })
    expect(courses.loading).toBe(false)
    expect(genericToast).not.toHaveBeenCalled()
  })

  it('教师大纲任务启动后立即切换到教师检查点投影', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    vi.spyOn(http, 'post').mockResolvedValue({ data: {
      job_id: 'job-teacher-outline',
      course_id: 'course-teacher-outline',
      course_name: '程序设计',
      status: 'pending',
      phase: 'queued',
    } })
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    const refreshPreview = vi.spyOn(courses, 'refreshGenerationPreview').mockResolvedValue(true)
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)

    const result = await generation.startSmartGeneration(
      '程序设计',
      {
        target_course_id: 'course-teacher-outline',
        teacher_authoring_mode: 'lesson_assets_v1',
      },
      'teacher',
    )

    expect(result?.jobId).toBe('job-teacher-outline')
    expect(generation.getTask('course-teacher-outline')?.taskType).toBe('teacher_outline_generation')
    expect(refreshPreview).toHaveBeenCalledWith('course-teacher-outline', 'teacher')
  })

  it('轮询能恢复在 WebSocket 订阅前快速失败的教师大纲任务', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-fast-failure'
    const localTask = generation.createTask(
      'job-fast-failure',
      'course-fast-failure',
      '热力学',
    )
    localTask.status = 'pending'
    localTask.taskType = 'teacher_outline_generation'
    generation.generationStatus = 'generating'
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(http, 'get').mockResolvedValue({ data: [{
      id: 'job-fast-failure',
      course_id: 'course-fast-failure',
      course_name: '热力学',
      type: 'teacher_outline_generation',
      status: 'failed',
      progress: 32,
      phase: 'outline_generation',
      message: '正在生成轻量章节骨架',
      error: 'AI provider unavailable: authentication_failed',
      error_code: 'provider_auth_failed',
    }] })

    await generation.fetchGlobalTasks()

    expect(localTask.status).toBe('error')
    expect(localTask.error).toContain('authentication_failed')
    expect(generation.generationStatus).toBe('error')
    expect(refreshList).not.toHaveBeenCalled()
  })

  it('全局轮询发现教师大纲任务时不用学生身份覆盖课程列表', async () => {
    setActiveRequestIdentityScope('teacher')
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-teacher-discovered'
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)
    vi.spyOn(http, 'get').mockResolvedValue({ data: [{
      id: 'job-teacher-discovered',
      course_id: 'course-teacher-discovered',
      course_name: '数据结构',
      type: 'teacher_outline_generation',
      status: 'waiting_for_review',
      progress: 35,
      phase: 'outline_ready',
    }] })

    await generation.fetchGlobalTasks()

    expect(generation.getTask('course-teacher-discovered')?.taskType).toBe('teacher_outline_generation')
    expect(refreshList).toHaveBeenCalledWith({ surface: 'teacher' })
  })

  it('教师大纲完成只刷新教师投影而不伪装成学生课程发布', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-teacher-complete'
    courses.currentCourseProjection = 'generation_preview'
    const localTask = generation.createTask('job-teacher-complete', 'course-teacher-complete', '数据结构')
    localTask.status = 'running'
    localTask.taskType = 'teacher_outline_generation'
    vi.spyOn(http, 'get').mockResolvedValue({ data: [{
      id: 'job-teacher-complete', course_id: 'course-teacher-complete', course_name: '数据结构',
      type: 'teacher_outline_generation', status: 'completed', progress: 100, phase: 'completed',
    }] })
    const refreshPreview = vi.spyOn(courses, 'refreshGenerationPreview').mockResolvedValue(true)
    const refreshDocument = vi.spyOn(courses, 'refreshCourseData').mockResolvedValue(undefined)
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.fetchGlobalTasks()

    expect(refreshList).toHaveBeenCalledWith({ surface: 'teacher' })
    expect(refreshPreview).toHaveBeenCalledWith('course-teacher-complete', 'teacher')
    expect(refreshDocument).not.toHaveBeenCalled()
  })

  it('发布完成后同步正式正文、课程库摘要和当前生成状态', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-1'
    const localTask = generation.createTask('job-1', 'course-1', '线性代数')
    localTask.status = 'running'
    generation.isGenerating = true
    generation.generationStatus = 'generating'

    vi.spyOn(http, 'get').mockResolvedValue({
      data: [{
        id: 'job-1', course_id: 'course-1', course_name: '线性代数', status: 'completed',
        progress: 100, phase: 'completed', message: '课程生成完成', completed_nodes: 2, total_nodes: 2,
        recovery: { state: 'completed', can_resume: false, reason_code: 'already_published', reason: 'done', checkpoint: {} },
      }],
    })
    const refreshDocument = vi.spyOn(courses, 'refreshCourseData').mockResolvedValue(undefined)
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.fetchGlobalTasks()

    expect(refreshDocument).toHaveBeenCalledWith('course-1', 'student')
    expect(refreshList).toHaveBeenCalledTimes(1)
    expect(generation.isGenerating).toBe(false)
    expect(generation.generationStatus).toBe('idle')
    expect(generation.generationProgress).toBe(100)
  })

  it('WebSocket 完成事件复用同一发布后对账动作', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-1'
    const localTask = generation.createTask('job-1', 'course-1', '线性代数')
    localTask.status = 'running'
    generation.isGenerating = true
    generation.generationStatus = 'generating'

    const refreshDocument = vi.spyOn(courses, 'refreshCourseData').mockResolvedValue(undefined)
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    generation.handleWSMessage({
      type: 'task_completed',
      course_id: 'course-1',
      task_id: 'job-1',
      payload: { status: 'completed', progress: 100 },
    })

    await vi.waitFor(() => {
      expect(refreshList).toHaveBeenCalledTimes(1)
      expect(refreshDocument).toHaveBeenCalledWith('course-1', 'student')
    })
    expect(localTask.status).toBe('completed')
    expect(generation.isGenerating).toBe(false)
    expect(generation.generationStatus).toBe('idle')
  })

  it('忽略同一课程旧任务迟到的 WebSocket 状态', () => {
    const generation = useGenerationStore()
    const localTask = generation.createTask('job-new', 'course-1', '线性代数')
    localTask.status = 'running'
    localTask.progress = 42
    const reconcile = vi.spyOn(generation, 'reconcilePublishedCourses')

    generation.handleWSMessage({
      type: 'task_completed',
      course_id: 'course-1',
      task_id: 'job-old',
      payload: { status: 'completed', progress: 100 },
    })

    expect(generation.getTask('course-1')?.id).toBe('job-new')
    expect(generation.getTask('course-1')?.status).toBe('running')
    expect(generation.getTask('course-1')?.progress).toBe(42)
    expect(generation.taskProgress['course-1']).toBeUndefined()
    expect(reconcile).not.toHaveBeenCalled()
  })

  it('活动任务进入学习页时读取生成工作区而不是空正式文档', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    const get = vi.spyOn(http, 'get').mockImplementation(async (url: string) => {
      if (url === '/api/courses/course-live/task') {
        return { data: { id: 'job-live', status: 'running', progress: 48, phase: 'content_generation' } } as never
      }
      if (url === '/api/courses/course-live/generation-preview') {
        return { data: {
          schema_version: 'generation_preview_v1', projection: 'generation_workspace',
          course_id: 'course-live', course_name: '线性代数', workspace_id: 'job-live', workspace_status: 'active',
          task: {
            id: 'job-live', status: 'running', progress: 48, phase: 'content_generation',
            message: '正在生成：向量空间', current_nodes: [{ node_id: 'L2-1-1', node_name: '向量空间', action: '生成中', type: 'content' }],
          },
          nodes: [{
            node_id: 'L2-1-1', parent_node_id: 'root', node_name: '向量空间', node_level: 2,
            node_content: '# 向量空间\n\n正在形成的正文', node_type: 'original', generation_status: 'generating',
            content_state: 'draft', generated_chars: 20,
          }],
        } } as never
      }
      throw new Error(`unexpected request: ${url}`)
    })

    await courses.loadCourse('course-live')

    expect(courses.currentCourseProjection).toBe('generation_preview')
    expect(courses.nodes[0]?.node_content).toContain('正在形成的正文')
    expect(courses.currentNode?.node_id).toBe('L2-1-1')
    expect(get).not.toHaveBeenCalledWith('/api/courses/course-live/document')
  })

  it('教师只读预览加载正式课程时不触发学习记录迁移', async () => {
    const courses = useCourseStore()
    const fetchCourseAnnotations = vi.spyOn(courses, 'fetchCourseAnnotations').mockResolvedValue(undefined)
    vi.spyOn(courses, 'refreshGenerationPreview').mockResolvedValue(false)
    vi.spyOn(http, 'get').mockImplementation(async (url: string) => {
      if (url === '/api/courses/course-teacher-preview/task') {
        return { data: { status: 'none' } } as never
      }
      if (url === '/api/courses/course-teacher-preview/document') {
        return { data: {
          course_id: 'course-teacher-preview', course_name: '教师预览课程', current_course_version_id: 'v1',
          source_format: 'canonical', migration: { required: false },
          document: {
            schema_version: 'course_document_v1', course_id: 'course-teacher-preview', title: '教师预览课程',
            document_revision: 'r1', sections: [], blocks: [],
          },
        } } as never
      }
      throw new Error(`unexpected request: ${url}`)
    })

    await courses.loadCourse('course-teacher-preview', { includeLearningRecords: false })

    expect(courses.currentCourseProjection).toBe('published')
    expect(fetchCourseAnnotations).not.toHaveBeenCalled()
  })

  it('教师预览即使大纲任务已完成也优先读取当前教案讲稿投影', async () => {
    const courses = useCourseStore()
    const get = vi.spyOn(http, 'get').mockImplementation(async (url: string) => {
      if (url === '/api/courses/course-teacher-current/task?task_type=teacher_outline_generation') {
        return { data: { id: 'job-outline', type: 'teacher_outline_generation', status: 'completed', progress: 100 } } as never
      }
      if (url === '/api/teacher/courses/course-teacher-current/generation-preview') {
        return { data: {
          schema_version: 'generation_preview_v2', projection: 'teacher_lesson_authoring',
          course_id: 'course-teacher-current', course_name: '教师当前课程', workspace_id: 'job-outline', workspace_status: 'active',
          task: { id: 'job-outline', status: 'completed', progress: 100, phase: 'teacher_outline_confirmed' },
          nodes: [{
            node_id: 'L2-1-1', parent_node_id: 'L1-1', node_name: '当前讲稿', node_level: 2,
            node_content: '当前已确认讲稿正文', content_blocks: [], generation_status: 'completed', content_state: 'finalized',
          }],
        } } as never
      }
      throw new Error(`unexpected request: ${url}`)
    })

    await courses.loadCourse('course-teacher-current', {
      includeLearningRecords: false,
      taskType: 'teacher_outline_generation',
      monitorTask: false,
      previewSurface: 'teacher',
    })

    expect(courses.currentCourseProjection).toBe('generation_preview')
    expect(courses.nodes[0]?.node_content).toBe('当前已确认讲稿正文')
    expect(get).not.toHaveBeenCalledWith('/api/courses/course-teacher-current/document')
  })

  it('刷新后保留大纲等待继续状态并读取可编辑投影', async () => {
    const courses = useCourseStore()
    const generation = useGenerationStore()
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    const get = vi.spyOn(http, 'get').mockImplementation(async (url: string) => {
      if (url === '/api/courses/course-outline-waiting/task?task_type=teacher_outline_generation') {
        return { data: {
          id: 'job-outline-waiting', type: 'teacher_outline_generation', status: 'waiting_for_input',
          progress: 35, phase: 'outline_shape_ready', updated_at: '2026-09-04T10:00:00Z',
        } } as never
      }
      if (url === '/api/teacher/courses/course-outline-waiting/generation-preview') {
        return { data: {
          schema_version: 'generation_preview_v2', projection: 'generation_workspace',
          course_id: 'course-outline-waiting', course_name: 'UI 设计', workspace_id: 'job-outline-waiting', workspace_status: 'active',
          task: { id: 'job-outline-waiting', status: 'waiting_for_input', progress: 35, phase: 'outline_shape_ready' },
          nodes: [{
            node_id: 'L1-1', parent_node_id: 'root', node_name: '第1讲 设计导论', node_level: 1,
            node_content: '', content_blocks: [], generation_status: 'completed', content_state: 'draft',
          }],
        } } as never
      }
      throw new Error(`unexpected request: ${url}`)
    })

    await courses.loadCourse('course-outline-waiting', {
      includeLearningRecords: false,
      taskType: 'teacher_outline_generation',
      previewSurface: 'teacher',
    })

    expect(courses.currentCourseProjection).toBe('generation_preview')
    expect(courses.nodes[0]?.node_name).toBe('第1讲 设计导论')
    expect(generation.getTask('course-outline-waiting')?.status).toBe('waiting_for_input')
    expect(get).not.toHaveBeenCalledWith('/api/courses/course-outline-waiting/document')
  })

  it('任务轮询暂时失败时仍从空发布壳恢复失败任务现场', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    vi.spyOn(generation, 'startGlobalMonitor').mockImplementation(() => undefined)
    vi.spyOn(http, 'get').mockImplementation(async (url: string) => {
      if (url === '/api/courses/course-failed/task') {
        throw new Error('task polling timeout')
      }
      if (url === '/api/courses/course-failed/document') {
        return { data: {
          course_id: 'course-failed', course_name: '恢复课程', current_course_version_id: '',
          source_format: 'canonical', migration: { required: false },
          document: {
            schema_version: 'course_document_v1', course_id: 'course-failed', title: '恢复课程',
            document_revision: '', sections: [], blocks: [],
          },
        } } as never
      }
      if (url === '/api/courses/course-failed/generation-preview') {
        return { data: {
          schema_version: 'generation_preview_v2', projection: 'generation_workspace',
          course_id: 'course-failed', course_name: '恢复课程', workspace_id: 'job-failed', workspace_status: 'failed',
          task: {
            id: 'job-failed', status: 'failed', progress: 36, phase: 'content_generation',
            error: 'provider unavailable',
            recovery: {
              state: 'manual_resume', can_resume: true, reason_code: 'checkpoint_available', reason: 'saved',
              checkpoint: { phase: 'content_generation', completed_nodes: 0, total_nodes: 1, draft_node_ids: [], failed_node_ids: [], interrupted_node_ids: [] },
            },
          },
          nodes: [{
            node_id: 'L2-1-1', parent_node_id: 'root', node_name: '待恢复小节', node_level: 2,
            node_content: '', node_type: 'original', generation_status: 'error', content_state: 'failed',
            error_summary: 'provider unavailable',
          }],
        } } as never
      }
      throw new Error(`unexpected request: ${url}`)
    })

    await courses.loadCourse('course-failed')

    expect(courses.currentCourseProjection).toBe('generation_preview')
    expect(courses.nodes[0]?.node_name).toBe('待恢复小节')
    expect(generation.getTask('course-failed')?.status).toBe('error')
    expect(generation.getTask('course-failed')?.recovery?.can_resume).toBe(true)
  })

  it('服务端草稿检查点较旧时不覆盖浏览器已经收到的正文增量', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-live'
    courses.currentCourseProjection = 'generation_preview'
    courses.nodes = [{
      node_id: 'L2-1-1', parent_node_id: 'root', node_name: '向量空间', node_level: 2,
      node_content: '已检查点正文 + 刚收到的增量', node_type: 'original', generation_status: 'generating',
      content_state: 'draft', generated_chars: 15,
    }]
    generation.createTask('job-live', 'course-live', '线性代数')
    vi.spyOn(http, 'get').mockResolvedValue({ data: {
      schema_version: 'generation_preview_v1', projection: 'generation_workspace',
      course_id: 'course-live', course_name: '线性代数', workspace_id: 'job-live', workspace_status: 'active',
      task: { id: 'job-live', status: 'running', progress: 50, phase: 'content_generation' },
      nodes: [{
        node_id: 'L2-1-1', parent_node_id: 'root', node_name: '向量空间', node_level: 2,
        node_content: '已检查点正文', node_type: 'original', generation_status: 'generating',
        content_state: 'draft', generated_chars: 7,
      }],
    } })

    await courses.refreshGenerationPreview('course-live')

    expect(courses.nodes[0]?.node_content).toBe('已检查点正文 + 刚收到的增量')
  })

  it('较旧大纲投影不覆盖已到达的等待继续状态和讲次方案', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-outline-preview-race'
    courses.currentCourseProjection = 'generation_preview'
    courses.currentGenerationPreviewUpdatedAt = '2026-09-04T10:00:05Z'
    courses.nodes = [{
      node_id: 'L1-1', parent_node_id: 'root', node_name: '第1讲 最新讲次方案', node_level: 1,
      node_content: '', node_type: 'original', generation_status: 'completed', generated_chars: 0,
    }]
    const task = generation.createTask('job-outline-preview-race', 'course-outline-preview-race', 'UI 设计')
    task.status = 'waiting_for_input'
    task.progress = 35
    task.updatedAt = '2026-09-04T10:00:05Z'
    vi.spyOn(http, 'get').mockResolvedValue({ data: {
      schema_version: 'generation_preview_v2', projection: 'generation_workspace',
      course_id: 'course-outline-preview-race', course_name: 'UI 设计',
      workspace_id: 'job-outline-preview-race', workspace_status: 'active',
      updated_at: '2026-09-04T10:00:01Z',
      task: { id: 'job-outline-preview-race', status: 'running', progress: 30, updated_at: '2026-09-04T10:00:01Z' },
      nodes: [{
        node_id: 'L1-1', parent_node_id: 'root', node_name: '旧的生成中方案', node_level: 1,
        node_content: '', node_type: 'original', generation_status: 'generating', generated_chars: 0,
      }],
    } })

    await courses.refreshGenerationPreview('course-outline-preview-race', 'teacher')

    expect(courses.nodes[0]?.node_name).toBe('第1讲 最新讲次方案')
    expect(task).toMatchObject({ status: 'waiting_for_input', progress: 35 })
  })

  it('带质量建议发布后也从草稿投影切换到正式课程', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-warning'
    courses.currentCourseProjection = 'generation_preview'
    const localTask = generation.createTask('job-warning', 'course-warning', '建议课程')
    localTask.status = 'running'
    vi.spyOn(http, 'get').mockResolvedValue({ data: [{
      id: 'job-warning', course_id: 'course-warning', course_name: '建议课程',
      status: 'completed_with_warnings', progress: 100, phase: 'completed', publication_allowed: true,
    }] })
    const refreshDocument = vi.spyOn(courses, 'refreshCourseData').mockResolvedValue(undefined)
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.fetchGlobalTasks()

    expect(refreshDocument).toHaveBeenCalledWith('course-warning', 'student')
  })

  it('后端确认任务不存在时清理失效的本地活动状态', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-stale'
    const localTask = generation.createTask('job-stale', 'course-stale', '世界模型')
    localTask.status = 'running'
    localTask.progress = 32
    generation.isGenerating = true
    generation.generationStatus = 'generating'
    generation.generationProgress = 32

    vi.spyOn(http, 'get')
      .mockResolvedValueOnce({ data: [] })
      .mockRejectedValueOnce({ response: { status: 404 } })
    const warning = vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.fetchGlobalTasks()

    expect(http.get).toHaveBeenNthCalledWith(2, '/api/tasks/job-stale', { silentError: true })
    expect(generation.getTask('course-stale')).toBeUndefined()
    expect(generation.isGenerating).toBe(false)
    expect(generation.generationStatus).toBe('idle')
    expect(generation.generationProgress).toBe(0)
    expect(warning).toHaveBeenCalledTimes(1)
    expect(refreshList).toHaveBeenCalledTimes(1)
  })

  it('列表未包含但单任务仍存在时保留并同步活动任务', async () => {
    const generation = useGenerationStore()
    const localTask = generation.createTask('job-active', 'course-active', '世界模型')
    localTask.status = 'running'
    localTask.progress = 32

    vi.spyOn(http, 'get')
      .mockResolvedValueOnce({ data: [] })
      .mockResolvedValueOnce({
        data: {
          id: 'job-active', course_id: 'course-active', course_name: '世界模型', status: 'running',
          progress: 48, phase: 'blueprint_generation', message: '正在生成课程蓝图',
        },
      })

    await generation.fetchGlobalTasks()

    expect(generation.getTask('course-active')?.status).toBe('running')
    expect(generation.getTask('course-active')?.progress).toBe(48)
    expect(generation.globalTasks).toHaveLength(1)
  })

  it('同一课程存在多条历史时只把当前活动任务投影到学习页', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    vi.spyOn(http, 'get').mockResolvedValue({
      data: [
        {
          id: 'job-new', course_id: 'course-1', course_name: '线性代数',
          status: 'running', progress: 42, phase: 'content_generation',
          updated_at: '2026-07-19T10:00:00Z',
        },
        {
          id: 'job-old', course_id: 'course-1', course_name: '线性代数',
          status: 'completed', progress: 100, phase: 'completed',
          updated_at: '2026-07-18T10:00:00Z',
        },
      ],
    })
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.fetchGlobalTasks()

    expect(generation.globalTasks.map(task => task.id)).toEqual(['job-new', 'job-old'])
    expect(generation.getTask('course-1')?.id).toBe('job-new')
    expect(generation.getTask('course-1')?.status).toBe('running')
    expect(generation.getTask('course-1')?.progress).toBe(42)
  })

  it('单任务核对遇到临时网络错误时保留本地活动状态', async () => {
    const generation = useGenerationStore()
    const localTask = generation.createTask('job-offline', 'course-offline', '世界模型')
    localTask.status = 'running'
    localTask.progress = 32

    vi.spyOn(http, 'get')
      .mockResolvedValueOnce({ data: [] })
      .mockRejectedValueOnce(new Error('offline'))

    await generation.fetchGlobalTasks()

    expect(generation.getTask('course-offline')?.status).toBe('running')
    expect(generation.getTask('course-offline')?.progress).toBe(32)
  })

  it('暂停动作只控制显式选中的后端任务', async () => {
    const generation = useGenerationStore()
    const localTask = generation.createTask('job-new', 'course-1', '线性代数')
    localTask.status = 'running'
    generation.globalTasks = [
      { id: 'job-new', course_id: 'course-1', status: 'running', progress: 42 },
      { id: 'job-old', course_id: 'course-1', status: 'completed', progress: 100 },
    ]
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: { status: 'paused' } })

    await generation.pauseTask('course-1', 'job-new')

    expect(post).toHaveBeenCalledWith('/api/tasks/job-new/pause')
    expect(generation.globalTasks.find(task => task.id === 'job-new')?.status).toBe('paused')
    expect(generation.globalTasks.find(task => task.id === 'job-old')?.status).toBe('completed')
    expect(generation.getTask('course-1')?.status).toBe('paused')
  })

  it('找不到后端任务 ID 时暂停失败且不伪造本地成功', async () => {
    const generation = useGenerationStore()
    const localTask = generation.createTask('', 'course-local', '本地残留任务')
    localTask.status = 'running'
    vi.spyOn(http, 'get').mockResolvedValue({ data: { status: 'none' } })
    const post = vi.spyOn(http, 'post')
    vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
    vi.spyOn(console, 'error').mockImplementation(() => undefined)

    await expect(generation.pauseTask('course-local')).rejects.toThrow('backend_task_not_found')

    expect(post).not.toHaveBeenCalled()
    expect(generation.getTask('course-local')?.status).toBe('running')
    expect(generation.getTask('course-local')?.shouldStop).toBe(false)
  })

  it('取消任务后清理本地投影并重新读取课程列表', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    generation.createTask('job-cancel', 'course-cancel', '待取消课程')
    generation.taskProgress['course-cancel'] = {
      percentage: 20, currentNodeName: '第一节', completedNodes: 1, totalNodes: 5,
      estimatedTimeRemaining: 0, bytesGenerated: 200, updatedAt: new Date(),
      etaSampleCount: 0, secondsPerNode: 0,
    }
    vi.spyOn(http, 'delete').mockResolvedValue({ data: { status: 'deleted' } })
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.cancelTask('course-cancel')

    expect(http.delete).toHaveBeenCalledWith('/api/tasks/job-cancel')
    expect(generation.getTask('course-cancel')).toBeUndefined()
    expect(generation.taskProgress['course-cancel']).toBeUndefined()
    expect(refreshList).toHaveBeenCalledTimes(1)
  })

  it('删除同课程旧任务时保留当前任务投影与其他历史', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    const localTask = generation.createTask('job-new', 'course-1', '线性代数')
    localTask.status = 'running'
    generation.globalTasks = [
      { id: 'job-new', course_id: 'course-1', status: 'running', progress: 42 },
      { id: 'job-old', course_id: 'course-1', status: 'completed', progress: 100 },
    ]
    vi.spyOn(http, 'delete').mockResolvedValue({ data: { status: 'deleted' } })
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.deleteTask('course-1', 'job-old')

    expect(http.delete).toHaveBeenCalledWith('/api/tasks/job-old')
    expect(generation.globalTasks.map(task => task.id)).toEqual(['job-new'])
    expect(generation.getTask('course-1')?.id).toBe('job-new')
    expect(generation.getTask('course-1')?.status).toBe('running')
  })

  it('没有本地投影时也能清除后端终态任务', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    generation.globalTasks = [{
      id: 'job-completed', course_id: 'course-completed', course_name: '已发布课程',
      status: 'completed', progress: 100,
    }]
    vi.spyOn(generation, 'ensureJobId').mockResolvedValue('job-completed')
    vi.spyOn(http, 'delete').mockResolvedValue({ data: { status: 'deleted' } })
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.deleteTask('course-completed')

    expect(http.delete).toHaveBeenCalledWith('/api/tasks/job-completed')
    expect(generation.globalTasks).toHaveLength(0)
    expect(refreshList).toHaveBeenCalledTimes(1)
  })

  it('批量清理后按后端返回 ID 立即移除任务', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    generation.createTask('job-failed', 'course-1', '线性代数').status = 'error'
    generation.createTask('job-running', 'course-2', '微积分').status = 'running'
    generation.globalTasks = [
      { id: 'job-failed', course_id: 'course-1', status: 'failed', progress: 30 },
      { id: 'job-running', course_id: 'course-2', status: 'running', progress: 40 },
    ]
    vi.spyOn(http, 'delete').mockResolvedValue({
      data: { status: 'success', removed: 1, task_ids: ['job-failed'] },
    })
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    const removed = await generation.clearTaskRecords('invalid', 'course-1')

    expect(http.delete).toHaveBeenCalledWith('/api/tasks', {
      params: { scope: 'invalid', course_id: 'course-1' },
    })
    expect(removed).toBe(1)
    expect(generation.globalTasks.map(task => task.id)).toEqual(['job-running'])
    expect(generation.getTask('course-1')).toBeUndefined()
    expect(generation.getTask('course-2')?.id).toBe('job-running')
    expect(refreshList).toHaveBeenCalledWith({ surface: 'teacher' })
  })

  it('发现其他标签页创建的新任务时自动补读课程列表', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    vi.spyOn(http, 'get').mockResolvedValue({
      data: [{
        id: 'job-remote', course_id: 'course-remote', course_name: '远端课程', status: 'running',
        course_type: 'project', progress: 18, phase: 'blueprint_generation', completed_nodes: 0, total_nodes: 0,
      }],
    })
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.fetchGlobalTasks()

    expect(generation.getTask('course-remote')?.id).toBe('job-remote')
    expect(generation.getTask('course-remote')?.courseType).toBe('project')
    expect(refreshList).toHaveBeenCalledTimes(1)
  })

  it('把已发布的质量建议与阻断任务分开保存', async () => {
    const generation = useGenerationStore()
    vi.spyOn(http, 'get').mockResolvedValue({
      data: [{
        id: 'job-warning', course_id: 'course-warning', course_name: '建议课程',
        status: 'completed_with_warnings', progress: 100, phase: 'completed',
        publication_allowed: true, quality_status: 'completed_with_warnings',
        recovery: { state: 'completed', can_resume: false, reason_code: 'already_published', reason: 'done', checkpoint: {} },
      }],
    })

    await generation.fetchGlobalTasks()

    const task = generation.getTask('course-warning')
    expect(task?.publicationAllowed).toBe(true)
    expect(task?.qualityStatus).toBe('completed_with_warnings')
    expect(task?.recovery?.state).toBe('completed')
  })

  it('剩余时间至少积累两个真实节点间隔后才显示', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-15T00:00:00Z'))
    const generation = useGenerationStore()
    generation.createTask('job-eta', 'course-eta', '估时课程')

    const progress = (completed: number) => generation.handleWSProgressUpdate({
      type: 'progress_update', course_id: 'course-eta', task_id: 'job-eta',
      payload: { status: 'running', progress: completed * 10, completed_nodes: completed, total_nodes: 10 },
    })

    progress(1)
    vi.advanceTimersByTime(60_000)
    progress(2)
    expect(generation.taskProgress['course-eta']?.estimatedTimeRemaining).toBe(0)

    vi.advanceTimersByTime(60_000)
    progress(3)
    expect(generation.taskProgress['course-eta']?.estimatedTimeRemaining).toBe(420)
  })

  it('删除课程统一清理任务和进度投影', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.courseList = [{ course_id: 'course-delete', course_name: '删除验收', node_count: 0 }]
    generation.createTask('job-delete', 'course-delete', '删除验收')
    generation.taskProgress['course-delete'] = {
      percentage: 12, currentNodeName: '', completedNodes: 0, totalNodes: 0,
      estimatedTimeRemaining: 0, bytesGenerated: 0, updatedAt: new Date(),
      etaSampleCount: 0, secondsPerNode: 0,
    }
    vi.spyOn(http, 'delete').mockResolvedValue({ data: { status: 'success' } })
    vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await courses.deleteCourse('course-delete')

    expect(http.delete).toHaveBeenCalledWith('/api/courses/course-delete')
    expect(generation.getTask('course-delete')).toBeUndefined()
    expect(generation.taskProgress['course-delete']).toBeUndefined()
  })

  it('WebSocket 进度事件保留后端心跳与更新时间，供停滞判断使用', () => {
    const generation = useGenerationStore()
    generation.createTask('job-beat', 'course-beat', '世界模型')

    generation.handleWSMessage({
      type: 'progress_update',
      course_id: 'course-beat',
      task_id: 'job-beat',
      payload: {
        status: 'running',
        progress: 40,
        current_phase: 'course_teaching_plan_batch',
        heartbeat_at: '2026-08-05T10:00:00',
        updated_at: '2026-08-05T10:00:05',
      },
    } as any)

    const task = generation.getTask('course-beat')
    expect(task?.heartbeatAt).toBe('2026-08-05T10:00:00')
    expect(task?.updatedAt).toBe('2026-08-05T10:00:05')
  })

  it('较旧轮询快照不会把大纲等待继续覆盖回生成中', async () => {
    const generation = useGenerationStore()
    const localTask = generation.createTask('job-outline-race', 'course-outline-race', 'UI 设计')
    localTask.taskType = 'teacher_outline_generation'
    localTask.status = 'waiting_for_input'
    localTask.progress = 35
    localTask.updatedAt = '2026-09-04T10:00:05Z'
    generation.globalTasks = [{
      id: 'job-outline-race', course_id: 'course-outline-race', type: 'teacher_outline_generation',
      status: 'waiting_for_input', progress: 35, updated_at: '2026-09-04T10:00:05Z',
    }]
    vi.spyOn(http, 'get').mockResolvedValue({ data: [{
      id: 'job-outline-race', course_id: 'course-outline-race', type: 'teacher_outline_generation',
      status: 'running', progress: 30, updated_at: '2026-09-04T10:00:01Z',
    }] })

    await generation.fetchGlobalTasks()

    expect(generation.getTask('course-outline-race')).toMatchObject({ status: 'waiting_for_input', progress: 35 })
    expect(generation.globalTasks[0]).toMatchObject({ status: 'waiting_for_input', progress: 35 })
  })

  it('同一更新时间下也不接受从等待操作倒退到生成中', () => {
    const generation = useGenerationStore()
    const localTask = generation.createTask('job-outline-same-time', 'course-outline-same-time', 'UI 设计')
    localTask.status = 'waiting_for_input'
    localTask.progress = 35
    localTask.updatedAt = '2026-09-04T10:00:05Z'

    generation.handleWSProgressUpdate({
      type: 'progress_update', course_id: 'course-outline-same-time', task_id: 'job-outline-same-time',
      payload: { status: 'running', progress: 30, updated_at: '2026-09-04T10:00:05Z' },
    } as any)

    expect(localTask).toMatchObject({ status: 'waiting_for_input', progress: 35 })
  })

  it('更晚的恢复快照可以让大纲任务重新进入运行', async () => {
    const generation = useGenerationStore()
    const localTask = generation.createTask('job-outline-resume', 'course-outline-resume', 'UI 设计')
    localTask.taskType = 'teacher_outline_generation'
    localTask.status = 'waiting_for_input'
    localTask.progress = 35
    localTask.updatedAt = '2026-09-04T10:00:01Z'
    vi.spyOn(http, 'get').mockResolvedValue({ data: [{
      id: 'job-outline-resume', course_id: 'course-outline-resume', type: 'teacher_outline_generation',
      status: 'running', progress: 36, updated_at: '2026-09-04T10:00:05Z',
    }] })

    await generation.fetchGlobalTasks()

    expect(generation.getTask('course-outline-resume')).toMatchObject({ status: 'running', progress: 36 })
  })

  it('刷新后仍能恢复已取消任务并显示为错误而不是等待', async () => {
    const generation = useGenerationStore()
    vi.spyOn(http, 'get').mockResolvedValue({ data: [{
      id: 'job-cancelled', course_id: 'course-cancelled', type: 'teacher_outline_generation',
      status: 'cancelled', progress: 35, updated_at: '2026-09-04T10:00:05Z',
    }] })

    await generation.fetchGlobalTasks()

    expect(generation.getTask('course-cancelled')).toMatchObject({ status: 'error', progress: 35 })
  })

  it('任务错误事件保留后端错误码与可读原因，不只留技术堆栈', () => {
    const generation = useGenerationStore()
    generation.createTask('job-fail', 'course-fail', '世界模型')

    generation.handleWSMessage({
      type: 'task_error',
      course_id: 'course-fail',
      task_id: 'job-fail',
      payload: {
        error: 'RateLimitError: 429 too_many_requests',
        error_code: 'provider_rate_limited',
        error_user_message: '服务请求过于频繁，已保留当前进度。',
      },
    } as any)

    const task = generation.getTask('course-fail')
    expect(task?.status).toBe('error')
    expect(task?.errorCode).toBe('provider_rate_limited')
    expect(task?.errorUserMessage).toBe('服务请求过于频繁，已保留当前进度。')
    expect(task?.error).toBe('RateLimitError: 429 too_many_requests')
  })

  it('HTTP 对账同样接通错误码、可读原因与心跳', async () => {
    const generation = useGenerationStore()
    const localTask = generation.createTask('job-poll', 'course-poll', '世界模型')
    localTask.status = 'running'

    vi.spyOn(http, 'get').mockResolvedValue({
      data: [{
        id: 'job-poll', course_id: 'course-poll', course_name: '世界模型', status: 'error',
        progress: 62, phase: 'content_generation', current_phase: 'content_generation',
        error: 'ProviderTimeout: upstream timed out',
        error_code: 'provider_timeout',
        error_user_message: 'AI 服务响应超时，已完成正文不会丢失。',
        heartbeat_at: '2026-08-05T10:00:00',
        updated_at: '2026-08-05T10:00:05',
      }],
    })

    await generation.fetchGlobalTasks()

    const task = generation.getTask('course-poll')
    expect(task?.errorCode).toBe('provider_timeout')
    expect(task?.errorUserMessage).toBe('AI 服务响应超时，已完成正文不会丢失。')
    expect(task?.heartbeatAt).toBe('2026-08-05T10:00:00')
    expect(task?.updatedAt).toBe('2026-08-05T10:00:05')
  })

  it('正在生成的节点提示走 i18n，英文模式不残留中文', async () => {
    const generation = useGenerationStore()
    generation.createTask('job-i18n', 'course-i18n', '线性代数')

    const emit = () => generation.handleWSMessage({
      type: 'progress_update',
      course_id: 'course-i18n',
      task_id: 'job-i18n',
      payload: { status: 'running', progress: 20, current_node_name: '向量空间' },
    } as any)

    emit()
    expect(generation.getTask('course-i18n')?.currentStep).toBe('正在生成：向量空间')

    await setLocale('en')
    emit()
    const englishStep = generation.getTask('course-i18n')?.currentStep || ''
    expect(englishStep).toBe('Generating: 向量空间')
    expect(englishStep).not.toContain('正在生成')
    await setLocale('zh')
  })

  it('节点失败事件保留错误码与可重试标志，不只留截断的原始串', () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-node'
    courses.nodes = [{
      node_id: 'L2-1-1', parent_node_id: 'root', node_name: '波函数', node_level: 2,
      node_content: '', node_type: 'original', generation_status: 'generating',
      generated_chars: 0,
    }] as any
    generation.createTask('job-node', 'course-node', '量子力学')

    generation.handleWSMessage({
      type: 'task_error',
      course_id: 'course-node',
      task_id: 'job-node',
      payload: {
        node_id: 'L2-1-1',
        node_name: '波函数',
        error: 'RateLimitError: 429 too_many_requests',
        error_code: 'provider_rate_limited',
        retryable: true,
        retry_count: 3,
      },
    } as any)

    const node = courses.nodes[0] as any
    expect(node.generation_status).toBe('error')
    expect(node.error_code).toBe('provider_rate_limited')
    expect(node.error_retryable).toBe(true)
    expect(node.error_summary).toBe('RateLimitError: 429 too_many_requests')
  })
})

describe('L3b 真实渲染校验接进发布链路', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    setActivePinia(createPinia())
  })

  it('节点定稿后对正文实跑渲染，并把结果回报后端', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-x'
    courses.nodes = [{
      node_id: 'L2-1-1', parent_node_id: 'root', node_name: '波函数', node_level: 2,
      node_content: '', node_type: 'original', generation_status: 'generating',
      generated_chars: 0,
    }] as any
    generation.createTask('job-x', 'course-x', '量子力学')
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: { status: 'recorded' } })

    generation.handleWSMessage({
      type: 'node_finalized',
      course_id: 'course-x',
      task_id: 'job-x',
      payload: { node_id: 'L2-1-1', node_content: '坏公式 $\\frac{}{$ 收尾' },
    } as any)
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(1)
    const [url, body] = post.mock.calls[0]!
    expect(url).toBe('/api/courses/course-x/nodes/L2-1-1/render-diagnostics')
    expect((body as any).math_failure_count).toBeGreaterThan(0)
  })

  it('正文渲染正常时也回报，让修好的节点能清掉旧问题', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-y'
    courses.nodes = [{
      node_id: 'L2-2-1', parent_node_id: 'root', node_name: '正常节', node_level: 2,
      node_content: '', node_type: 'original', generation_status: 'generating',
      generated_chars: 0,
    }] as any
    generation.createTask('job-y', 'course-y', '量子力学')
    const post = vi.spyOn(http, 'post').mockResolvedValue({ data: { status: 'recorded' } })

    generation.handleWSMessage({
      type: 'node_finalized',
      course_id: 'course-y',
      task_id: 'job-y',
      payload: { node_id: 'L2-2-1', node_content: '正常公式 $x^2 + y^2 = z^2$ 结束' },
    } as any)
    await flushPromises()

    expect(post).toHaveBeenCalledTimes(1)
    expect((post.mock.calls[0]![1] as any)).toEqual({
      math_failure_count: 0,
      block_failure_count: 0,
    })
  })

  it('回报失败不能影响生成流程', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    courses.currentCourseId = 'course-z'
    courses.nodes = [{
      node_id: 'L2-3-1', parent_node_id: 'root', node_name: '节点', node_level: 2,
      node_content: '', node_type: 'original', generation_status: 'generating',
      generated_chars: 0,
    }] as any
    generation.createTask('job-z', 'course-z', '量子力学')
    vi.spyOn(http, 'post').mockRejectedValue(new Error('404 no active task'))

    expect(() => generation.handleWSMessage({
      type: 'node_finalized',
      course_id: 'course-z',
      task_id: 'job-z',
      payload: { node_id: 'L2-3-1', node_content: '内容 $x$' },
    } as any)).not.toThrow()
    await flushPromises()

    // The node still finalizes normally.
    expect((courses.nodes[0] as any).generation_status).toBe('completed')
  })
})
