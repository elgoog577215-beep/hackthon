import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ElMessage } from 'element-plus'
import { useCourseStore } from '@/stores/course'
import { useGenerationStore } from '@/stores/generation'
import http from '@/utils/http'


describe('course generation lifecycle reconciliation', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.useRealTimers()
    localStorage.clear()
    setActivePinia(createPinia())
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

    expect(refreshDocument).toHaveBeenCalledWith('course-1')
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
      expect(refreshDocument).toHaveBeenCalledWith('course-1')
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

    expect(refreshDocument).toHaveBeenCalledWith('course-warning')
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

  it('发现其他标签页创建的新任务时自动补读课程列表', async () => {
    const generation = useGenerationStore()
    const courses = useCourseStore()
    vi.spyOn(http, 'get').mockResolvedValue({
      data: [{
        id: 'job-remote', course_id: 'course-remote', course_name: '远端课程', status: 'running',
        progress: 18, phase: 'blueprint_generation', completed_nodes: 0, total_nodes: 0,
      }],
    })
    const refreshList = vi.spyOn(courses, 'fetchCourseList').mockResolvedValue(undefined)

    await generation.fetchGlobalTasks()

    expect(generation.getTask('course-remote')?.id).toBe('job-remote')
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
})
