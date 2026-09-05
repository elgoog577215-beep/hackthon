/**
 * 资源分析统一 API
 * - 视频：复用 listVideoTasks / getVideoTaskDetail / submitVideo，报告在 /resource-analysis/report/:id 内展示
 * - 文本/PPT：Mock，后续接入真实接口
 */

import { listVideoTasks } from './video'
import type { VideoTaskListItem } from './video'
import { listDocumentHistory } from './document'

const MOCK_DELAY_MS = 500

export type AnalysisTaskType = 'video' | 'text' | 'ppt' | 'document'

export type AnalysisTaskStatus = 'unstarted' | 'waiting' | 'success' | 'failed'

/** 统一任务列表项（视频来自真实接口，文本/PPT 为 Mock） */
export interface UnifiedAnalysisTask {
  id: string
  type: AnalysisTaskType
  name: string
  status: AnalysisTaskStatus
  progress: number
  createdAt: string
  /** 仅视频有，来自原接口 */
  courseName?: string
  teacherName?: string
  college?: string
  /** 仅视频可能有，列表封面预览 */
  coverUrl?: string
  /** 仅视频：开始分析时间（Video.analysis_start_time），用于列表预计剩余展示 */
  analysisStartTime?: string | null
  /** 仅本地分析「分析中」：后端按时长+排队+并发算出的预估剩余秒数（云端为 null） */
  estimatedSeconds?: number | null
}

/** 文本/PPT 分析报告（Mock 结构，与视频报告风格一致） */
export interface MockAnalysisReport {
  summary: string
  teachingRhythm?: string
  interaction?: string
  boardDesign?: string
  suggestions: string[]
}

/** 文本分析提交参数（Mock） */
export interface SubmitTextAnalysisParams {
  file: File
  name: string
}

/** PPT 分析提交参数（Mock） */
export interface SubmitPptAnalysisParams {
  file: File
  name: string
}

// Mock 存储：文本 / PPT 任务（仅内存）
interface MockTaskItem {
  id: string
  type: 'text' | 'ppt'
  name: string
  status: AnalysisTaskStatus
  progress: number
  createdAt: string
  report?: MockAnalysisReport
}

const mockTasks: MockTaskItem[] = []

/** 资源分析列表强制刷新事件（删除/上传后通知列表页重新拉取） */
export const RESOURCE_ANALYSIS_FORCE_REFRESH_EVENT = 'resource-analysis:forceRefresh'

export function notifyResourceAnalysisListRefresh(): void {
  window.dispatchEvent(new CustomEvent(RESOURCE_ANALYSIS_FORCE_REFRESH_EVENT))
}

function createMockReport(type: 'text' | 'ppt'): MockAnalysisReport {
  return {
    summary: `（Mock）这是一份${type === 'text' ? '文本' : 'PPT'}分析报告的总体评价，内容结构清晰，重点突出。`,
    teachingRhythm: '（Mock）内容节奏与逻辑层次合理。',
    interaction: '（Mock）可读性良好，便于后续教学使用。',
    boardDesign: '（Mock）结构设计清晰。',
    suggestions: ['（Mock）建议补充更多示例', '（Mock）可适当增加小结部分'],
  }
}

/**
 * 获取统一分析任务列表（视频接口 + 文本/PPT Mock 合并，按时间倒序）
 */
export async function listUnifiedAnalysisTasks(): Promise<UnifiedAnalysisTask[]> {
  const [videoList, docHistory] = await Promise.all([
    listVideoTasks(),
    listDocumentHistory().catch(() => []),
  ])
  const videoTasks: UnifiedAnalysisTask[] = videoList.map((t: VideoTaskListItem) => ({
    id: t.id,
    type: 'video' as const,
    name: t.videoName,
    status: t.status,
    progress: t.progress,
    createdAt: t.createdAt,
    courseName: t.courseName,
    teacherName: t.teacherName,
    college: t.college,
    coverUrl: t.coverUrl,
    analysisStartTime: t.analysisStartTime ?? undefined,
    estimatedSeconds: t.estimatedSeconds ?? null,
  }))
  const mockTasksMapped: UnifiedAnalysisTask[] = mockTasks.map((t) => ({
    id: t.id,
    type: t.type,
    name: t.name,
    status: t.status,
    progress: t.progress,
    createdAt: t.createdAt,
  }))
  const docTasks: UnifiedAnalysisTask[] = docHistory.map((entry) => ({
    id: `doc-${entry.id}`,
    type: 'document' as const,
    name: entry.file_name,
    status: 'success' as const,
    progress: 100,
    createdAt: entry.create_time,
    courseName: '',
  }))
  const merged = [...videoTasks, ...mockTasksMapped, ...docTasks]
  merged.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
  return merged
}

/**
 * 提交文本分析（Mock）
 */
export async function submitTextAnalysis(params: SubmitTextAnalysisParams): Promise<{ taskId: string; message: string }> {
  await new Promise((r) => setTimeout(r, MOCK_DELAY_MS))
  const { file, name } = params
  if (!file?.name || !name?.trim()) throw new Error('请填写名称并选择文本文件')
  const taskId = `text-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
  const now = new Date().toISOString()
  const task: MockTaskItem = {
    id: taskId,
    type: 'text',
    name: name.trim(),
    status: 'waiting',
    progress: 0,
    createdAt: now,
  }
  mockTasks.unshift(task)
  // 模拟分析完成
  setTimeout(() => {
    task.status = 'success'
    task.progress = 100
    task.report = createMockReport('text')
  }, 1500)
  return { taskId, message: '提交成功，分析任务已创建（当前为演示模式）' }
}

/**
 * 提交 PPT 分析（Mock）
 */
export async function submitPptAnalysis(params: SubmitPptAnalysisParams): Promise<{ taskId: string; message: string }> {
  await new Promise((r) => setTimeout(r, MOCK_DELAY_MS))
  const { file, name } = params
  if (!file?.name || !name?.trim()) throw new Error('请填写名称并选择 PPT 文件')
  const taskId = `ppt-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
  const now = new Date().toISOString()
  const task: MockTaskItem = {
    id: taskId,
    type: 'ppt',
    name: name.trim(),
    status: 'waiting',
    progress: 0,
    createdAt: now,
  }
  mockTasks.unshift(task)
  setTimeout(() => {
    task.status = 'success'
    task.progress = 100
    task.report = createMockReport('ppt')
  }, 1500)
  return { taskId, message: '提交成功，分析任务已创建（当前为演示模式）' }
}

/**
 * 获取分析报告（仅文本/PPT Mock；视频报告由 getVideoTaskDetail 获取，在资源分析报告页内展示）
 */
export async function getMockAnalysisReport(id: string): Promise<{ name: string; report: MockAnalysisReport } | null> {
  await new Promise((r) => setTimeout(r, 200))
  const task = mockTasks.find((t) => t.id === id)
  if (!task || !task.report) return null
  return { name: task.name, report: task.report }
}

/**
 * 判断任务 ID 是否为视频任务（走原有视频报告页）
 */
export function isVideoTaskId(id: string): boolean {
  return !id.startsWith('text-') && !id.startsWith('ppt-') && !id.startsWith('doc-')
}

export function isDocumentHistoryId(id: string): boolean {
  return id.startsWith('doc-')
}

export function getDocumentRecordId(id: string): string {
  return id.replace('doc-', '')
}
