/**
 * 视频分析 API
 * - 本地上传：POST /video/init（chunks）→ /video/upload（multipart）→ /video/finish（upload_id）→ /video/operation（create）
 * - 列表/详情：GET /video/list、GET /video 等
 */

import { buildApiFullUrl, get, getBlob, post, postFormData, postFormUrlEncoded } from './request'
import { buildAuthorizationHeader } from './authToken'
import { OperationEnum } from './types'

/** 分片大小（5MB），可按需调整 */
export const CHUNK_SIZE = 5 * 1024 * 1024

export type VideoTaskStatus = 'unstarted' | 'waiting' | 'success' | 'failed'

export interface VideoTaskListItem {
  id: string
  videoName: string
  college: string
  courseName: string
  teacherName: string
  status: VideoTaskStatus
  progress: number
  coverUrl?: string
  /** 开始分析时间（ISO 字符串，来自 Video.analysis_start_time / VideoSummary） */
  analysisStartTime?: string | null
  /** 本地分析预估剩余秒数（仅本地分析「分析中」、含排队；云端分析为 null） */
  estimatedSeconds?: number | null
  createdAt: string
}

/**
 * VideoAnalysisResult，视频分析结果（GET /video 回参 VideoDetail.analysis_result）
 */
export interface VideoAnalysisResult {
  /** Audio Duration */
  audio_duration?: number | null
  /** Class Education Summary */
  class_education_summary?: Record<string, unknown> | null
  /** Class Summary */
  class_summary?: Record<string, unknown> | null
  /** Knowledge Graph */
  knowledge_graph?: Record<string, unknown> | null
  /** Radar Chart */
  radar_chart?: Record<string, unknown> | null
  /** Suggestions */
  suggestions?: string[] | null
  /** Teach Content */
  teach_content?: Record<string, unknown> | null
  /** Teach Db Result */
  teach_db_result?: Record<string, unknown> | null
  /** Teach Knowledge */
  teach_knowledge?: Record<string, unknown>[] | null
  /** Teach Question */
  teach_question?: Record<string, unknown> | null
  /** Teach Summary */
  teach_summary?: Record<string, unknown>[] | null
  /** Teach Wh */
  teach_wh?: Record<string, unknown>[] | null
  /** Transcript */
  transcript?: Record<string, unknown>[] | null
  /** 新版分析结果：教学表达 */
  teaching_expression?: Record<string, unknown> | null
  /** 新版分析结果：教学设计 */
  teaching_design?: Record<string, unknown> | null
  /** 新版分析结果：知识呈现 */
  knowledge_presentation?: Record<string, unknown> | null
  /** 新版分析结果：互动质量 */
  interaction_quality?: Record<string, unknown> | null
  /** 新版分析结果：思政融合 */
  ideological_integration?: Record<string, unknown> | null
  /** 新版雷达维度列表 */
  radar_data?: Array<Record<string, unknown>> | null
  /** 新版 AI 总评 */
  ai_summary?: Record<string, unknown> | null
  [property: string]: unknown
}

/**
 * 前端报告页使用的分析结果（兼容 /video/result、本地 mock 的非标字段形状）
 */
export interface VideoAnalysisReport {
  audio_duration?: number
  class_education_summary?: Record<string, unknown>
  class_summary?: Record<string, unknown>
  knowledge_graph?: Record<string, unknown>
  radar_chart?: unknown
  suggestions?: string[]
  teach_content?: Record<string, unknown>
  teach_db_result?: Record<string, unknown>
  teach_knowledge?: Record<string, unknown> | Record<string, unknown>[]
  teach_question?: Record<string, unknown>
  /** 标准数组或 mock 中的单对象 */
  teach_summary?: Record<string, unknown> | Record<string, unknown>[]
  teach_wh?: Record<string, unknown>[]
  /**
   * 转写文本：
   * - 标准：Record[]（VideoAnalysisResult.transcript）
   * - 兼容：{ status, result: { transcript: [...] } } 等嵌套结构
   */
  transcript?: unknown
  /** 归一化后的词云（来自 knowledge_presentation.word_cloud） */
  word_cloud?: Array<{ word?: string; weight?: number; text?: string; count?: number }>
  [key: string]: unknown
}

function asAnalysisRecord(value: unknown): Record<string, unknown> | null {
  if (value != null && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>
  }
  return null
}

function parseClockTimeToSeconds(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return 0
  const parts = value.trim().split(':').map((v) => Number(v))
  if (parts.some((n) => Number.isNaN(n))) return 0
  if (parts.length === 3) return (parts[0] ?? 0) * 3600 + (parts[1] ?? 0) * 60 + (parts[2] ?? 0)
  if (parts.length === 2) return (parts[0] ?? 0) * 60 + (parts[1] ?? 0)
  if (parts.length === 1) return parts[0] ?? 0
  return 0
}

/** 判断是否为 GET /video 新版嵌套 analysis_result 结构 */
function isNewVideoAnalysisFormat(raw: Record<string, unknown>): boolean {
  return (
    raw.teaching_expression != null ||
    raw.teaching_design != null ||
    raw.knowledge_presentation != null ||
    raw.interaction_quality != null ||
    raw.ideological_integration != null ||
    Array.isArray(raw.radar_data)
  )
}

function normalizeWhDistribution(whDist: Record<string, unknown>): Record<string, unknown>[] {
  const items: Record<string, unknown>[] = []
  for (const [category, infoRaw] of Object.entries(whDist)) {
    const info = asAnalysisRecord(infoRaw)
    if (!info) continue
    const countRaw = info.count
    const count =
      typeof countRaw === 'number' && Number.isFinite(countRaw)
        ? Math.round(countRaw)
        : Number.isFinite(Number(countRaw))
          ? Math.round(Number(countRaw))
          : 0
    const examples = Array.isArray(info.examples) ? info.examples : []
    for (const ex of examples) {
      const e = asAnalysisRecord(ex)
      if (!e) continue
      items.push({
        category,
        start: parseClockTimeToSeconds(e.start),
        end: parseClockTimeToSeconds(e.end),
        text: typeof e.text === 'string' ? e.text : '',
      })
    }
    for (let i = examples.length; i < count; i++) {
      items.push({ category, start: 0, end: 0, text: '' })
    }
  }
  return items
}

function normalizeTeachSummaryFromDesign(
  design: Record<string, unknown>,
): Record<string, unknown>[] {
  const segments = Array.isArray(design.segments) ? design.segments : []
  const intro = asAnalysisRecord(design.introduction_analysis)
  const summaryParts: string[] = []
  if (typeof intro?.description === 'string' && intro.description.trim()) {
    summaryParts.push(intro.description.trim())
  }
  if (typeof intro?.evaluation === 'string' && intro.evaluation.trim()) {
    summaryParts.push(intro.evaluation.trim())
  }

  const fileStructure = segments
    .map((seg) => asAnalysisRecord(seg))
    .filter((s): s is Record<string, unknown> => s != null)
    .map((s) => {
      const keypointName = typeof s.keypoint_name === 'string' ? s.keypoint_name.trim() : ''
      return {
        type: typeof s.type === 'string' ? s.type : '',
        content: typeof s.content === 'string' ? s.content : '',
        start_time: typeof s.start_time === 'string' ? s.start_time : '',
        end_time: typeof s.end_time === 'string' ? s.end_time : '',
        keypoint: keypointName,
      }
    })

  if (!summaryParts.length && !fileStructure.length) return []
  return [{ summary: summaryParts.join('\n\n'), file_structure: fileStructure }]
}

function normalizeRadarChart(radarData: unknown): unknown {
  if (!Array.isArray(radarData)) return radarData
  const items = radarData
    .map((item) => asAnalysisRecord(item))
    .filter((item): item is Record<string, unknown> => item != null)
    .filter((item) => {
      const dim = String(item.dimension ?? item.label ?? item.name ?? '').trim()
      return dim && dim !== '综合得分'
    })

  if (items.length >= 3) {
    return items.map((item) => ({
      label: item.dimension ?? item.label ?? item.name,
      value: item.score ?? item.value,
    }))
  }

  const map: Record<string, number> = {}
  for (const item of items) {
    const dim = String(item.dimension ?? item.label ?? item.name ?? '').trim()
    if (!dim || dim === '综合得分') continue
    const score = item.score ?? item.value
    if (typeof score === 'number' && Number.isFinite(score)) map[dim] = score
  }
  return Object.keys(map).length >= 3 ? map : radarData
}

/** 将新版嵌套 analysis_result 映射为报告页沿用的扁平字段 */
function normalizeNewVideoAnalysisResult(raw: Record<string, unknown>): VideoAnalysisReport {
  const teachingExpression = asAnalysisRecord(raw.teaching_expression)
  const volumeAnalysis = asAnalysisRecord(teachingExpression?.volume_analysis)
  const speechRate = asAnalysisRecord(teachingExpression?.speech_rate_analysis)
  const languageConciseness = asAnalysisRecord(teachingExpression?.language_conciseness)
  const teachingDesign = asAnalysisRecord(raw.teaching_design)
  const knowledgePresentation = asAnalysisRecord(raw.knowledge_presentation)
  const interactionQuality = asAnalysisRecord(raw.interaction_quality)
  const ideologicalIntegration = asAnalysisRecord(raw.ideological_integration)
  const aiSummary = asAnalysisRecord(raw.ai_summary)

  const audioDuration =
    typeof volumeAnalysis?.total_duration === 'number'
      ? volumeAnalysis.total_duration
      : typeof raw.audio_duration === 'number'
        ? raw.audio_duration
        : undefined

  const teachDbResult: Record<string, unknown> = {}
  if (Array.isArray(volumeAnalysis?.result)) teachDbResult.result = volumeAnalysis.result
  if (volumeAnalysis?.avg_spl != null) teachDbResult.avg_spl = volumeAnalysis.avg_spl
  if (volumeAnalysis?.max_spl != null) teachDbResult.max_spl = volumeAnalysis.max_spl
  if (volumeAnalysis?.min_spl != null) teachDbResult.min_spl = volumeAnalysis.min_spl
  if (volumeAnalysis?.total_duration != null) teachDbResult.total_duration = volumeAnalysis.total_duration
  if (speechRate?.avg_cpm != null) {
    teachDbResult.speed = `平均语速约 ${speechRate.avg_cpm} 字/分钟（最快 ${speechRate.max_cpm ?? '—'}，最慢 ${speechRate.min_cpm ?? '—'}）`
  }
  if (volumeAnalysis?.avg_spl != null) {
    teachDbResult.volume = `平均音量 ${volumeAnalysis.avg_spl}dB（最高 ${volumeAnalysis.max_spl ?? '—'}dB，最低 ${volumeAnalysis.min_spl ?? '—'}dB）`
  }
  if (languageConciseness?.filler_word_ratio != null) {
    const ratio = languageConciseness.filler_word_ratio
    const pct = typeof ratio === 'number' ? (ratio * 100).toFixed(1) : String(ratio)
    teachDbResult.filler_ratio = `冗余填充词占比 ${pct}%`
  }

  const suggestionTexts: string[] = []
  if (typeof aiSummary?.summary === 'string' && aiSummary.summary.trim()) {
    suggestionTexts.push(aiSummary.summary.trim())
  }
  if (Array.isArray(aiSummary?.suggestions)) {
    for (const s of aiSummary.suggestions) {
      if (typeof s === 'string' && s.trim()) suggestionTexts.push(s.trim())
    }
  }
  if (suggestionTexts.length) {
    teachDbResult.suggestion = suggestionTexts.slice(0, 2).join('；')
  }

  const teachSummary = teachingDesign ? normalizeTeachSummaryFromDesign(teachingDesign) : []
  const whDist = asAnalysisRecord(interactionQuality?.wh_distribution)
  const teachWh = whDist ? normalizeWhDistribution(whDist) : []

  const typeStats = asAnalysisRecord(interactionQuality?.type_statistics)
  const teachQuestion: Record<string, unknown> = {}
  if (typeStats) {
    const statistics: Record<string, unknown> = {}
    for (const [type, val] of Object.entries(typeStats)) {
      if (typeof val === 'number') statistics[type] = { count: val }
      else if (val && typeof val === 'object') statistics[type] = val
    }
    if (Object.keys(statistics).length) teachQuestion.statistics = statistics
  }
  if (Array.isArray(interactionQuality?.interaction_events)) {
    teachQuestion.questions = interactionQuality.interaction_events
  }

  const knowledgeTree = knowledgePresentation?.knowledge_tree
  const wordCloud = knowledgePresentation?.word_cloud

  const events = Array.isArray(ideologicalIntegration?.ideological_events)
    ? ideologicalIntegration.ideological_events
    : []
  const ideologySummary = events
    .map((e) => asAnalysisRecord(e))
    .filter((e): e is Record<string, unknown> => e != null)
    .map((ev) => ({
      start: ev.start,
      end: ev.end,
      result: {
        title: ev.title,
        content: ev.content,
        status: 2,
      },
    }))

  const report: VideoAnalysisReport = {
    ...raw,
    audio_duration: audioDuration,
    teach_db_result:
      Object.keys(teachDbResult).length > 0
        ? teachDbResult
        : (raw.teach_db_result as Record<string, unknown> | undefined),
    teach_summary:
      teachSummary.length > 0
        ? teachSummary
        : (raw.teach_summary as VideoAnalysisReport['teach_summary']),
    teach_wh:
      teachWh.length > 0 ? teachWh : (raw.teach_wh as VideoAnalysisReport['teach_wh']),
    teach_question:
      Object.keys(teachQuestion).length > 0
        ? teachQuestion
        : (raw.teach_question as Record<string, unknown> | undefined),
    teach_knowledge: Array.isArray(knowledgeTree)
      ? knowledgeTree
      : (raw.teach_knowledge as VideoAnalysisReport['teach_knowledge']),
    word_cloud: Array.isArray(wordCloud)
      ? (wordCloud as VideoAnalysisReport['word_cloud'])
      : undefined,
    class_education_summary:
      ideologySummary.length > 0
        ? { summary: ideologySummary }
        : (raw.class_education_summary as Record<string, unknown> | undefined),
    class_summary:
      typeof aiSummary?.summary === 'string'
        ? { text: aiSummary.summary }
        : (raw.class_summary as Record<string, unknown> | undefined),
    suggestions: Array.isArray(aiSummary?.suggestions)
      ? (aiSummary.suggestions as string[])
      : Array.isArray(raw.suggestions)
        ? (raw.suggestions as string[])
        : undefined,
    radar_chart: normalizeRadarChart(raw.radar_data ?? raw.radar_chart),
  }

  return report
}

/** 将 GET /video 回参中的 analysis_result 转为前端报告结构 */
export function toVideoAnalysisReport(
  result: VideoAnalysisResult | VideoAnalysisReport | null | undefined
): VideoAnalysisReport | undefined {
  if (result == null) return undefined
  const raw = result as Record<string, unknown>
  if (isNewVideoAnalysisFormat(raw)) {
    return normalizeNewVideoAnalysisResult(raw)
  }
  return result as VideoAnalysisReport
}

export interface VideoTaskDetail extends VideoTaskListItem {
  classTime?: string
  classHour?: string
  videoUrl?: string
  report?: VideoAnalysisReport
}

export interface SubmitVideoParams {
  file: File
  videoName: string
  /**
   * 分片上传进度回调（已上传分片数 / 总分片数）
   */
  onUploadProgress?: (payload: { uploadedChunks: number; totalChunks: number }) => void
  /**
   * 中断信号：调用方 abort 后会取消进行中的 init/分片/finish/create 请求并停止上传
   */
  signal?: AbortSignal
}

export interface SubmitVideoResult {
  /** 落库后的视频主键 id（POST /video/operation 的 data）；若无则回退为 finish 返回的 path */
  taskId: string
  message: string
  /** finish 返回的封面路径（相对或绝对，与 path 规则一致） */
  coverPath?: string
}

// --- 与后端接口文档一致：Request/Response 类型 ---

interface ApiResponse<T = Record<string, unknown>> {
  data?: T | null
  error?: string | null
  success?: boolean
}

export interface VideoOperationParams {
  id?: string | null
  name?: string | null
  path?: string | null
  cover?: string | null
  operation: OperationEnum
  [property: string]: any
}

/** POST /video/init 请求体：分片总数（与接口文档一致；实际以 form 字段 `chunks` 提交） */
export interface VideoInitUploadRequest {
  chunks: number
  [property: string]: unknown
}

/**
 * POST /video/upload 表单字段（与接口文档一致）。
 * 文档中 `file` 为二进制；OpenAPI 常写作 string，此处用 Blob 表示上传体。
 */
export interface VideoChunkUploadForm {
  file: Blob
  index: number
  upload_id: string
  [property: string]: unknown
}

/** POST /video/finish 请求体 */
export interface VideoFinishUploadRequest {
  upload_id: string
  [property: string]: unknown
}

/** POST /video/finish 成功时 `data`：dict[str, str]（视频路径、封面路径等） */
export type VideoFinishUploadResponseData = Record<string, string>

/** 【视频上传初始化】POST /video/init：请求 chunks；回参 ApiResponse[str]，data 为 upload_id */
/** 【视频分片上传】POST /video/upload：multipart/form-data，字段 file、index、upload_id；回参 ApiResponse[NoneType] */
/** 【视频上传完成】POST /video/finish：请求 upload_id；回参 ApiResponse[dict[str,str]] */
/** 【触发视频分析】GET /video/analyze：Query id；回参 ApiResponse[NoneType] */
/** 【导出视频分析报告】GET /video/export：Query id；回参为 Word 文档文件流 */
/** 【查询视频分析结果】/video/result：请求 id；回参 ApiResponse[dict] */
/** 【根据 id 查询视频】GET /video?id=；回参 ApiResponse[VideoDetail] */
/** 【查询视频列表】GET /video/list；回参 ApiResponse[list[VideoSummary]] */
/** 【执行视频操作】POST /video/operation；CREATE 成功时 data 为新视频 id（string） */

/** 视频状态（与后端 VideoStatusEnum 一致；列表/详情共用） */
export enum VideoStatusEnum {
  Failed = 'failed',
  Success = 'success',
  Unstarted = 'unstarted',
  Waiting = 'waiting',
}

/** GET /video 请求参数 */
export interface VideoDetailRequest {
  /** Id */
  id: string
  [property: string]: unknown
}

/**
 * VideoDetail，视频详情（GET /video 回参 data）
 */
export interface VideoDetail {
  analysis_result: VideoAnalysisResult | null
  /** Analysis Start Time */
  analysis_start_time: string | null
  /** Create Time */
  create_time: string
  /** Id */
  id: string
  /** Name */
  name: string
  /** Path */
  path: string
  status: VideoStatusEnum
  [property: string]: unknown
}

/** @deprecated 使用 VideoDetail */
export type VideoDetailResponse = VideoDetail

/** /video/list 单条概要（VideoSummary） */
export interface VideoSummary {
  id: string
  name: string
  status: VideoStatusEnum
  create_time: string
  /** 封面图路径（列表接口 cover；与 finish 返回的 cover / cover_path 经落库后一致） */
  cover?: string | null
  /** 开始分析时间（后端 Video.analysis_start_time，ISO 字符串；部分序列化可能为 analysisStartTime） */
  analysis_start_time?: string | null
  analysisStartTime?: string | null
  /** 本地分析预估剩余秒数（后端 VideoSummary.estimated_seconds） */
  estimated_seconds?: number | null
  /** 绑定的课程 ID */
  related_course_id?: string | null
  /** 绑定的资源 ID（通常为教案版本） */
  related_resource_id?: string | null
  [property: string]: any
}

/** @deprecated 使用 VideoSummary */
export type VideoListResponse = VideoSummary

/** 查询视频分析结果：响应 data 为 dict，与 VideoAnalysisReport 兼容 */
export interface VideoResultData extends VideoAnalysisReport {
  [key: string]: unknown
}

const UPLOAD_INIT_URL = '/video/init'
const UPLOAD_CHUNK_URL = '/video/upload'
const UPLOAD_FINISH_URL = '/video/finish'
const VIDEO_ANALYZE_URL = '/video/analyze'
const VIDEO_EXPORT_URL = '/video/export'
const VIDEO_RESULT_URL = '/video/result'
const VIDEO_DETAIL_URL = '/video'
const VIDEO_LIST_URL = '/video/list'
const VIDEO_OPERATION_URL = '/video/operation'
// const VIDEO_ANALYSIS_REPORT_URL = '/video/analysis-report'  // 已废弃，统一走 /video?id=xxx
// 新接口：导入智云课堂视频（SSE）
const VIDEO_IMPORT_URL = '/video/zhiyun/import'
// 取消导入智云课堂视频
const VIDEO_IMPORT_CANCEL_URL = '/video/zhiyun/import/cancel'
// 智云课堂课程列表查询
const VIDEO_IMPORT_LIST_URL = '/video/zhiyun/list'

/** GET /video/zhiyun/list 查询参数（与后端 Request 对齐；日期两项由前端校验后传入） */
export interface ZhiyunVideoListQuery {
  search_begin_date: string
  search_end_date: string
  search_course_name?: string | null
  offset?: number
  page_size?: number
}

/** 智云课堂视频章节条目（ZhiyunVideoItem） */
export interface ZhiyunVideoItem {
  class_begin: string
  sub_id: string
  sub_title: string
  teacher_name: string
  [property: string]: any
}

/** 智云课堂按课程分组（ZhiyunVideoGroup） */
export interface ZhiyunVideoGroup {
  course_id: string
  course_name: string
  items: ZhiyunVideoItem[]
  [property: string]: any
}

/** 扁平化后的列表行（供导入页展示与操作） */
export interface SmartClassroomCourseImportListItem {
  course_id: string
  sub_id: string
  course_name: string
  sub_title: string
  teacher_name: string
  class_begin: string
  [property: string]: any
}

function pickZhiyunString(row: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const v = row[key]
    if (v != null && String(v).trim() !== '') return String(v).trim()
  }
  return ''
}

/** 兼容分组列表、扁平列表及 camelCase 字段 */
export function normalizeZhiyunVideoListPayload(data: unknown): SmartClassroomCourseImportListItem[] {
  if (!Array.isArray(data)) return []

  const result: SmartClassroomCourseImportListItem[] = []

  for (const raw of data) {
    if (!raw || typeof raw !== 'object') continue
    const row = raw as Record<string, unknown>
    const nested = row.items

    if (Array.isArray(nested)) {
      const courseId = pickZhiyunString(row, 'course_id', 'courseId')
      const courseName = pickZhiyunString(row, 'course_name', 'courseName')
      for (const itemRaw of nested) {
        if (!itemRaw || typeof itemRaw !== 'object') continue
        const item = itemRaw as Record<string, unknown>
        const subId = pickZhiyunString(item, 'sub_id', 'subId')
        if (!subId) continue
        result.push({
          course_id: courseId,
          course_name: courseName,
          sub_id: subId,
          sub_title: pickZhiyunString(item, 'sub_title', 'subTitle', 'subtitle'),
          teacher_name: pickZhiyunString(item, 'teacher_name', 'teacherName'),
          class_begin: pickZhiyunString(item, 'class_begin', 'classBegin'),
        })
      }
      continue
    }

    const subId = pickZhiyunString(row, 'sub_id', 'subId')
    if (!subId) continue
    result.push({
      course_id: pickZhiyunString(row, 'course_id', 'courseId'),
      course_name: pickZhiyunString(row, 'course_name', 'courseName'),
      sub_id: subId,
      sub_title: pickZhiyunString(row, 'sub_title', 'subTitle', 'subtitle'),
      teacher_name: pickZhiyunString(row, 'teacher_name', 'teacherName'),
      class_begin: pickZhiyunString(row, 'class_begin', 'classBegin'),
    })
  }

  return result
}

/** 【查询智云课堂视频列表】GET /video/zhiyun/list */
export async function listSmartClassroomImportVideos(
  params: ZhiyunVideoListQuery,
): Promise<SmartClassroomCourseImportListItem[]> {
  let begin = String(params.search_begin_date || '').trim()
  let end = String(params.search_end_date || '').trim()
  if (!begin || !end) {
    throw new Error('起始日期与结束日期均为必填')
  }
  if (begin > end) {
    throw new Error('起始日期不能晚于结束日期')
  }
  const query: Record<string, string | number> = {
    search_begin_date: begin,
    search_end_date: end,
    page_size: params.page_size ?? 20,
    offset: params.offset ?? 0,
  }
  if (params.search_course_name != null && String(params.search_course_name).trim() !== '') {
    query.search_course_name = String(params.search_course_name).trim()
  }
  const res = await get<ApiResponse<ZhiyunVideoGroup[] | SmartClassroomCourseImportListItem[]>>(
    VIDEO_IMPORT_LIST_URL,
    query,
  )
  if (!res.success) {
    throw new Error(res.error || '查询智云课堂视频列表失败')
  }
  return normalizeZhiyunVideoListPayload(res.data)
}

/**
 * 后端状态映射为前端任务状态。
 * 后端返回 VideoStatusEnum，映射为 VideoTaskStatus（字符串联合类型）。
 */
export function mapVideoStatus(status: VideoStatusEnum | string): VideoTaskStatus {
  const s = String(status).toLowerCase()
  if (s === VideoStatusEnum.Success) return 'success'
  if (s === VideoStatusEnum.Failed) return 'failed'
  if (s === VideoStatusEnum.Unstarted) return 'unstarted'
  if (s === VideoStatusEnum.Waiting) return 'waiting'
  return 'unstarted'
}

/**
 * 将 finish 或库表中的 `uploads/...` 等路径规范为与静态挂载一致的 `/static/...`（与后端 video_to_detail 约定一致）。
 */
function normalizeVideoStoragePathForRequest(raw: string): string {
  const t = raw.trim()
  if (!t) return t
  if (/^https?:\/\//i.test(t)) return t
  if (t.startsWith('/static/')) return t
  const idx = t.indexOf('uploads/')
  if (idx >= 0) {
    return `/static/${t.slice(idx + 'uploads/'.length)}`
  }
  return t.startsWith('/') ? t : `/${t}`
}

/** 将后端返回的封面/媒体路径拼成可在 img、video 中请求的 URL（与 request.ts 的 buildApiFullUrl 规则一致，避免 /api 重复） */
export function resolveVideoMediaUrl(path: string | null | undefined): string | undefined {
  if (path == null) return undefined
  const raw = String(path).trim()
  if (!raw) return undefined
  if (/^https?:\/\//i.test(raw)) return raw
  const normalized = normalizeVideoStoragePathForRequest(raw)
  const pathPart = normalized.startsWith('/') ? normalized : `/${normalized}`
  return buildApiFullUrl(pathPart)
}

/**
 * 视频任务是否仍处于可变化阶段（需轮询）。
 * 仅 'waiting'（排队/分析中，会自行变成 success/failed）才轮询；
 * 'unstarted'（未开始，需用户手动发起，状态不会自变）不轮询，避免列表里
 * 躺着未开始任务时页面每 5 秒永久空刷。
 */
export function isVideoTaskPollingActive(status: VideoTaskStatus | string): boolean {
  return status === 'waiting'
}

function getChunks(file: File): Blob[] {
  const list: Blob[] = []
  let start = 0
  while (start < file.size) {
    const end = Math.min(start + CHUNK_SIZE, file.size)
    list.push(file.slice(start, end))
    start = end
  }
  return list
}

/**
 * 【视频上传初始化】POST /video/init
 * 传参：chunks（application/x-www-form-urlencoded）。回参：ApiResponse[str]，data 为 upload_id。
 */
async function initUpload(chunks: number, signal?: AbortSignal): Promise<string> {
  const res = await postFormUrlEncoded<ApiResponse<string | null>>(UPLOAD_INIT_URL, { chunks }, { signal })
  if (!res.success || res.data == null || String(res.data).trim() === '') {
    throw new Error(res.error || '初始化上传失败')
  }
  return res.data
}

/**
 * 【视频分片上传】POST /video/upload
 * multipart/form-data：file、index、upload_id。回参：ApiResponse[NoneType]。
 */
async function uploadChunk(uploadId: string, index: number, chunkBlob: Blob, signal?: AbortSignal): Promise<void> {
  const form = new FormData()
  form.append('file', chunkBlob)
  form.append('index', String(index))
  form.append('upload_id', uploadId)
  const res = await postFormData<ApiResponse<null>>(UPLOAD_CHUNK_URL, form, { signal })
  if (!res.success) {
    throw new Error(res.error || `分片 ${index} 上传失败`)
  }
}

/** 解析 POST /video/finish 的 data：须含 path；封面兼容 cover（文档）与 cover_path（后端 common） */
function parseFinishUploadPayload(data: Record<string, unknown>): { path: string; cover?: string } {
  const str = (k: string): string => {
    const v = data[k]
    if (v == null) return ''
    return String(v).trim()
  }
  const path = str('path') || str('video_path')
  if (!path) {
    throw new Error('完成上传未返回视频路径')
  }
  const cover = str('cover') || str('cover_path')
  return { path, cover: cover || undefined }
}

/**
 * 【视频上传完成】POST /video/finish
 * 传参：upload_id（application/x-www-form-urlencoded，与后端 Form 一致）。
 * 回参：ApiResponse[dict[str, str]]。
 */
async function finishUpload(uploadId: string, signal?: AbortSignal): Promise<{ path: string; cover?: string }> {
  const res = await postFormUrlEncoded<ApiResponse<VideoFinishUploadResponseData>>(
    UPLOAD_FINISH_URL,
    { upload_id: uploadId },
    { signal },
  )
  if (!res.success || !res.data) {
    throw new Error(res.error || '完成上传失败（未返回视频路径）')
  }
  const parsed = parseFinishUploadPayload(res.data)
  return parsed
}

/** POST /video/operation 成功时 data 为新视频主键 id（字符串）；旧版可能为含 id 字段的对象 */
function extractCreatedVideoIdFromOperationData(data: unknown): string | null {
  if (data == null) return null
  if (typeof data === 'string') {
    const t = data.trim()
    return t || null
  }
  if (typeof data === 'object') {
    const o = data as Record<string, unknown>
    const id = o.id ?? o.video_id
    if (typeof id === 'string' && id.trim()) return id.trim()
    if (typeof id === 'number' && Number.isFinite(id)) return String(id)
  }
  return null
}

/**
 * 【触发视频分析】GET /video/analyze
 * Query：id（视频 ID）。回参：ApiResponse[NoneType]，data 为 null
 * 返回传入的 id，供后续 result/detail 使用
 */
async function analyzeVideo(id: string, mode: AnalysisMode = 'cloud'): Promise<string> {
  const res = await get<ApiResponse<null>>(VIDEO_ANALYZE_URL, { id, mode })
  if (!res.success) {
    throw new Error(res.error || '启动视频分析失败')
  }
  return id
}

/** 视频分析方式：cloud=智云课堂(超星)云端分析；local=使用本地自建模型分析 */
export type AnalysisMode = 'cloud' | 'local'

/**
 * 启动视频分析（GET /video/analyze?id= 视频主键 id&mode= 分析方式）
 */
export async function startVideoAnalysis(id: string, mode: AnalysisMode = 'cloud'): Promise<string> {
  return analyzeVideo(id, mode)
}

/**
 * 【导出视频分析报告】GET /video/export
 * 请求参数：id（视频主键）；回参为 Word 文档文件流
 */
export async function exportVideoAnalysisReport(id: string): Promise<Blob> {
  return getBlob(VIDEO_EXPORT_URL, { id })
}

/** 将 Blob 触发为浏览器本地下载 */
export function downloadBlobAsFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.rel = 'noopener'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

/**
 * 【查询视频分析结果】/video/result
 * 传参：id。回参：ApiResponse[dict]，data 为分析结果
 */
export async function getVideoResult(id: string): Promise<VideoResultData | null> {
  const res = await get<ApiResponse<Record<string, unknown>>>(VIDEO_RESULT_URL, { id })
  if (!res.success || !res.data) {
    return null
  }
  return res.data as VideoResultData
}

/**
 * 【根据 id 查询视频】GET /video
 * 传参：Query id。回参：ApiResponse[VideoDetail]
 */
export async function getVideoDetail(id: string): Promise<VideoDetail | null> {
  const params: VideoDetailRequest = { id }
  const res = await get<ApiResponse<VideoDetail>>(VIDEO_DETAIL_URL, params)
  if (!res.success || res.data == null) {
    return null
  }
  return res.data
}

/**
 * 【执行视频操作】POST /video/operation
 * - CREATE：path（必填）、name、cover；id 通常不传；成功时 data 为新视频 id（字符串）
 * - UPDATE：id、name
 * - DELETE：id、name 传 null
 */
export async function operateVideo(
  params: VideoOperationParams,
  opts?: { signal?: AbortSignal },
): Promise<string | null> {
  const op = params.operation
  if (op !== OperationEnum.CREATE && (!params.id || !String(params.id).trim())) {
    throw new Error('操作视频缺少 id')
  }
  const body: Record<string, unknown> = {
    operation: params.operation,
  }
  if (params.id != null && String(params.id).trim() !== '') body.id = String(params.id).trim()
  if (params.name !== undefined) body.name = params.name
  if (params.path != null && String(params.path).trim() !== '') body.path = String(params.path).trim()
  if (params.cover != null && String(params.cover).trim() !== '') body.cover = String(params.cover).trim()

  const res = await post<ApiResponse<string | null>>(VIDEO_OPERATION_URL, body, { signal: opts?.signal })
  if (!res.success) {
    throw new Error(res.error || '操作视频失败')
  }
  return res.data ?? null
}

/**
 * 【查询视频列表】GET /video/list
 * 可选按绑定的课程/资源（教案版本）过滤。回参：ApiResponse[list[VideoSummary]]
 */
export async function listVideos(filter?: {
  course_id?: string
  resource_id?: string
}): Promise<VideoSummary[]> {
  const res = await get<ApiResponse<VideoSummary[]>>(VIDEO_LIST_URL, filter)
  if (!res.success || !res.data) {
    return []
  }
  return res.data
}

/** 视频绑定参数（POST /video/binding） */
export interface VideoBindingRequest {
  id: string
  related_course_id?: string | null
  /** 绑定的资源 ID（通常为教案版本） */
  related_resource_id?: string | null
  unbind?: boolean
}

/** 【绑定/解绑视频】POST /video/binding：把视频挂到课程/教案版本，或解绑 */
export async function bindVideo(params: VideoBindingRequest): Promise<void> {
  const res = await post<ApiResponse<null>>('/video/binding', params)
  if (!res.success) {
    throw new Error(res.error || '视频绑定失败')
  }
}

export interface SmartClassroomVideoImportRequest {
  /** 课程 ID（列表项 course_id，对应开放平台 courseId） */
  course_id: string
  /** 章节 subId */
  sub_id: string | number
}

export interface SmartClassroomVideoImportCallbacks {
  onStart?: (payload: Record<string, any>) => void
  onProgress?: (progress: number | null) => void
  onEnd?: (videoId: string) => void
}

/**
 * 【导入智云课堂视频】GET /video/zhiyun/import?course_id=&sub_id=
 * 后端为 SSE（EventSourceResponse）。若用 request.get + response.text()，在代理/长连接未显式关闭时
 * 可能永远不 resolve，导致「导入并进入」不跳转。此处用流式读取，在收到 `event: end` 后立即结束。
 */
const VIDEO_IMPORT_TIMEOUT_MS = 30 * 60 * 1000

async function consumeVideoImportSse(
  response: Response,
  callbacks?: SmartClassroomVideoImportCallbacks,
): Promise<string> {
  const reader = response.body?.getReader()
  if (!reader) {
    throw new Error('无法读取导入响应')
  }

  const decoder = new TextDecoder()
  let buffer = ''
  let pendingEvent = ''
  const dataLines: string[] = []
  let videoId = ''
  let ended = false

  const dispatchMessage = () => {
    if (dataLines.length === 0 && !pendingEvent) return
    const ev = pendingEvent.trim()
    const raw = dataLines.join('\n').trim()
    pendingEvent = ''
    dataLines.length = 0

    if (ev === 'error') {
      let msg = '智云课堂视频导入失败'
      try {
        const j = JSON.parse(raw) as { error?: string }
        if (j.error) msg = j.error
      } catch {
        if (raw) msg = raw
      }
      throw new Error(msg)
    }
    if (ev === 'loading') {
      let progress: number | null = null
      if (raw) {
        try {
          const j = JSON.parse(raw) as { progress?: number | null }
          if (typeof j.progress === 'number' && Number.isFinite(j.progress)) {
            progress = j.progress
          }
        } catch {
          //
        }
      }
      callbacks?.onProgress?.(progress)
      return
    }
    if (ev === 'end' && raw) {
      try {
        const j = JSON.parse(raw) as { id?: string }
        if (typeof j.id === 'string' && j.id) {
          videoId = j.id
        }
      } catch {
        //
      }
      callbacks?.onEnd?.(videoId)
      ended = true
    }
  }

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split(/\r?\n/)
      buffer = lines.pop() ?? ''
      for (const rawLine of lines) {
        const line = rawLine.trimEnd()
        if (line === '') {
          dispatchMessage()
          if (ended) {
            await reader.cancel().catch(() => {})
            if (!videoId) {
              throw new Error('导入完成但未返回视频 id')
            }
            return videoId
          }
          continue
        }
        if (line.startsWith('event:')) {
          pendingEvent = line.slice('event:'.length).trim()
        } else if (line.startsWith('data:')) {
          dataLines.push(line.slice('data:'.length).trimStart())
        }
      }
    }
    if (buffer.trim() !== '') {
      buffer += '\n'
    }
    dispatchMessage()
    if (ended && videoId) {
      return videoId
    }
  } finally {
    try {
      await reader.cancel()
    } catch {
      //
    }
  }

  if (!videoId) {
    throw new Error('导入完成但未返回视频 id')
  }
  return videoId
}

export async function importSmartClassroomVideo(
  params: SmartClassroomVideoImportRequest,
  callbacks?: SmartClassroomVideoImportCallbacks,
  opts?: { signal?: AbortSignal; importId?: string },
): Promise<string> {
  const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) || ''
  const prefix = API_BASE === '' ? '/api' : ''
  const qs = new URLSearchParams({
    course_id: String(params.course_id ?? ''),
    sub_id: String(params.sub_id ?? ''),
  })
  // 本次导入标识：配合 cancelSmartClassroomImport 让后端可中途取消
  if (opts?.importId) qs.set('import_id', opts.importId)
  const fullUrl = `${API_BASE}${prefix}${VIDEO_IMPORT_URL}?${qs.toString()}`

  const headers: HeadersInit = { Accept: 'text/event-stream' }
  const authorization = buildAuthorizationHeader()
  if (authorization) headers.Authorization = authorization

  const controller = new AbortController()
  const t = window.setTimeout(() => controller.abort(), VIDEO_IMPORT_TIMEOUT_MS)

  // 外部取消信号（用户点击「取消导入」）联动到内部 controller，立即中断 SSE 连接
  const externalSignal = opts?.signal
  const onExternalAbort = () => controller.abort()
  if (externalSignal) {
    if (externalSignal.aborted) controller.abort()
    else externalSignal.addEventListener('abort', onExternalAbort, { once: true })
  }

  try {
    const response = await fetch(fullUrl, { method: 'GET', headers, signal: controller.signal })
    if (!response.ok) {
      const text = await response.text()
      let message = `HTTP ${response.status}`
      try {
        const j = JSON.parse(text) as { detail?: unknown; error?: string }
        if (typeof j.detail === 'string') message = j.detail
        else if (j.error) message = j.error
      } catch {
        if (text) message = text.slice(0, 300)
      }
      throw new Error(message)
    }

    return await consumeVideoImportSse(response, callbacks)
  } catch (e) {
    const isAbort =
      (typeof DOMException !== 'undefined' && e instanceof DOMException && e.name === 'AbortError') ||
      (e instanceof Error && e.name === 'AbortError')
    if (isAbort) {
      // 用户主动取消优先于超时判断：抛出 AbortError 让调用方静默处理
      if (externalSignal?.aborted) {
        throw new DOMException('已取消导入智云课堂视频', 'AbortError')
      }
      throw new Error('智云课堂视频导入超时，请稍后重试或检查网络与后端服务')
    }
    throw e
  } finally {
    window.clearTimeout(t)
    if (externalSignal) externalSignal.removeEventListener('abort', onExternalAbort)
  }
}

/**
 * 取消正在进行的智云课堂视频导入。
 *
 * 仅靠前端 abort SSE 连接并不可靠：反向代理常缓冲上游连接，后端要到下载完成、
 * 视频已落库后才察觉断开，于是「取消后视频仍出现在列表里」。本接口写一个带外
 * 取消标记，后端在下一个分片处即停止下载并清理，不落库。
 *
 * best-effort：请求失败不抛出（调用方仍会 abort 前端连接），仅记录告警。
 */
export async function cancelSmartClassroomImport(importId: string): Promise<void> {
  if (!importId) return
  try {
    await post<ApiResponse<null>>(VIDEO_IMPORT_CANCEL_URL, { import_id: importId })
  } catch (e) {
    console.warn('[SmartClassroom] 取消导入请求失败', e)
  }
}

/**
 * 分片上传视频并落库（不自动触发分析）
 * 流程：init → 分片上传 → finish（path + cover）→ operation create（登记名称等）
 */
export async function submitVideo(params: SubmitVideoParams): Promise<SubmitVideoResult> {
  const { file, videoName, onUploadProgress, signal } = params
  if (!file?.name) throw new Error('请选择视频文件')
  if (!videoName?.trim()) throw new Error('请填写视频名称')

  const throwIfAborted = () => {
    if (signal?.aborted) throw new DOMException('已取消上传', 'AbortError')
  }

  const chunks = getChunks(file)
  const totalChunks = chunks.length
  throwIfAborted()
  const uploadId = await initUpload(totalChunks, signal)

  for (let i = 0; i < totalChunks; i++) {
    const part = chunks[i]
    // 理论上不会为 undefined，这里做一次防御性检查避免 TS 报错
    if (!part) {
      throw new Error(`第 ${i} 个视频分片不存在`)
    }
    throwIfAborted()
    await uploadChunk(uploadId, i, part, signal)
    if (onUploadProgress) {
      onUploadProgress({ uploadedChunks: i + 1, totalChunks })
    }
  }

  throwIfAborted()
  const { path, cover } = await finishUpload(uploadId, signal)
  const createPayload: VideoOperationParams = {
    operation: OperationEnum.CREATE,
    path,
    name: videoName.trim(),
  }
  if (cover) createPayload.cover = cover

  const opData = await operateVideo(createPayload, { signal })
  const createdId = extractCreatedVideoIdFromOperationData(opData)
  const taskId = createdId ?? path

  return {
    taskId,
    coverPath: cover,
    message: '上传成功，请在详情页确认视频无误后点击「开始分析」',
  }
}

// --- 以下列表/详情暂为 Mock，result 则走真实接口 ---

const MOCK_DELAY_MS = 300

/** 演示用：上传后多少毫秒将任务标记为「分析完成」 */
const DEMO_ANALYSIS_DELAY_MS = 3500

/** 本地上传后尚未从后端列表接口拉取到的任务（后端无「任务列表」接口时的临时展示） */
const recentVideoTasks: VideoTaskListItem[] = []

/** 演示用：生成一份完整的 mock 分析报告，便于用户查看报告页 */
function getMockVideoReportForDemo(): VideoAnalysisReport {
  return {
    teach_knowledge: {
      summary: '本节课涉及的核心知识点学生掌握情况良好，重点概念均有覆盖。',
      points: ['概念理解准确', '例题讲解清晰', '与先修知识衔接自然'],
    },
    teach_summary: {
      text: '本节课程整体节奏适中，重点突出，师生互动较好，教学环节完整。',
      rhythm: '语速平稳，重点处有适当停顿与重复。',
    },
    teach_content: {
      main_topics: ['知识点导入', '核心概念讲解', '例题演示', '小结与作业'],
      coverage: '教学内容覆盖教学目标，逻辑清晰。',
    },
    teach_question: {
      count: 3,
      types: ['概念确认', '应用反馈', '总结归纳'],
      feedback: '教师提问后能给予及时反馈，学生参与积极。',
    },
    class_summary: {
      text: '课堂整体完成度较高，学生注意力集中，教学目标基本达成。',
      highlights: ['重点突出', '节奏适中', '互动充分'],
    },
    class_education_summary: {
      text: '课程中自然融入思政要点，与专业内容结合得当。（演示数据）',
    },
    knowledge_graph: {
      nodes: ['极限概念', '连续与间断', '导数引入'],
      edges: [['极限概念', '连续与间断'], ['连续与间断', '导数引入']],
      description: '知识点层次清晰，前后衔接合理。（演示数据）',
    },
    teach_wh: [
      { category: '是何', start: 0, end: 60, text: '明确了本节核心概念与目标' },
      { category: '为何', start: 60, end: 120, text: '解释了概念引入的必要性' },
      { category: '如何', start: 120, end: 180, text: '通过例题与板书进行了演示' },
      { category: '若何', start: 180, end: 240, text: '时间分配合理，重难点时间充足' },
      { category: '由何', start: 240, end: 300, text: '与前后章节关系有说明' },
    ],
    teach_db_result: {
      speed: '语速适中，约 120 字/分钟',
      volume: '音量稳定，无明显忽大忽小',
      suggestion: '可适当在关键处放慢语速以强化记忆。（演示数据）',
    },
  }
}

/**
 * 上传成功后注册到本地列表，使资源分析页能立即看到新卡片（后端暂无任务列表接口时使用）
 * 演示模式：约 3.5 秒后自动将任务标记为「分析完成」，便于用户点击查看 mock 报告
 */
export function registerUploadedVideoTask(params: {
  taskId: string
  videoName: string
  /** finish 返回的封面路径（原始），将解析为列表卡片可用的 URL */
  coverPath?: string
}): void {
  const { taskId, videoName, coverPath } = params
  if (recentVideoTasks.some((t) => t.id === taskId)) return
  recentVideoTasks.unshift({
    id: taskId,
    videoName,
    college: '',
    courseName: '',
    teacherName: '',
    status: 'unstarted',
    progress: 0,
    coverUrl: resolveVideoMediaUrl(coverPath ?? undefined),
    createdAt: new Date().toISOString(),
  })
}

/** 从会话内 recent 缓存移除任务（删除视频或后端列表已收录后调用） */
export function removeRegisteredVideoTask(taskId: string): void {
  const id = taskId.trim()
  if (!id) return
  const idx = recentVideoTasks.findIndex((t) => t.id === id)
  if (idx >= 0) recentVideoTasks.splice(idx, 1)
}

const mockTaskList: VideoTaskDetail[] = [
  {
    id: 'task-demo-1',
    videoName: '高等数学第一章绪论',
    college: '数学科学学院',
    courseName: '高等数学A',
    teacherName: '张老师',
    status: 'success',
    progress: 100,
    createdAt: '2024-12-01T10:00:00Z',
    report: {
      teach_summary: { text: '本节课程整体节奏适中，重点突出极限与连续的概念引入，学生互动较好。' },
      class_summary: { text: '整体教学目标达成良好，学生参与度较高。' },
    },
  },
  {
    id: 'task-demo-2',
    videoName: '大学物理实验-单摆',
    college: '物理学院',
    courseName: '大学物理实验',
    teacherName: '李老师',
    status: 'success',
    progress: 100,
    createdAt: '2024-12-05T14:30:00Z',
    report: {
      teach_summary: { text: '实验演示步骤清楚，安全提示到位，学生能较好理解操作要点。' },
      class_summary: { text: '学生能够按步骤完成实验，实验效果较好。' },
    },
  },
  {
    id: 'task-demo-extra',
    videoName: '线性代数-矩阵运算',
    college: '数学科学学院',
    courseName: '线性代数',
    teacherName: '王老师',
    status: 'success',
    progress: 100,
    createdAt: '2024-12-08T09:00:00Z',
    report: {
      teach_summary: { text: '矩阵运算讲解清晰，例题与定义结合紧密，学生反馈良好。' },
      class_summary: { text: '本节重点突出矩阵乘法与逆矩阵，课堂节奏适中。' },
    },
  },
]

/**
 * 获取视频任务列表
 * 请求 GET /video/list，与本次会话内上传的 recent 合并后按时间倒序
 */
export async function listVideoTasks(): Promise<VideoTaskListItem[]> {
  let list: VideoTaskListItem[] = []
  try {
    const rows = await listVideos()
    list = rows.map((v) => ({
      id: v.id,
      videoName: v.name,
      college: '',
      courseName: '',
      teacherName: '',
      status: mapVideoStatus(v.status),
      progress: mapVideoStatus(v.status) === 'success' ? 100 : 0,
      coverUrl: resolveVideoMediaUrl(v.cover ?? undefined),
      analysisStartTime:
        [v.analysis_start_time, v.analysisStartTime]
          .find((x) => x != null && String(x).trim() !== '')?.toString()
          .trim() ?? null,
      estimatedSeconds: v.estimated_seconds ?? null,
      createdAt: v.create_time,
    }))
  } catch {
    list = []
  }
  const seen = new Set(list.map((t) => t.id))
  // 后端已收录的任务移出 recent，避免状态陈旧；删除后也不会再从 recent 补回
  for (let i = recentVideoTasks.length - 1; i >= 0; i--) {
    const task = recentVideoTasks[i]
    if (task && seen.has(task.id)) {
      recentVideoTasks.splice(i, 1)
    }
  }
  const recent = recentVideoTasks.filter((t) => !seen.has(t.id))
  const merged = [...recent, ...list]
  merged.sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
  return merged
}

/**
 * 获取视频任务详情（仅直连后端，不调用 /video/list）
 * - demo：本地 Mock
 * - 否则：GET /video?id=；若无详情体再尝试 GET /video/result?id=
 */
/** 测试用：从本地 JSON 构造一份分析报告，方便没跑完真正分析流程时也能查看报告页视觉。 */
export const DEMO_LOCAL_JSON_TASK_ID = 'task-demo-local-json'

async function loadLocalDemoVideoTaskDetail(): Promise<VideoTaskDetail> {
  // 懒加载：只有用户点了「测试分析报告」按钮进到报告页才会真正打包并拉这份 335KB 的 JSON
  const mod = await import('../assets/demo-video-analysis.json')
  const data = (mod as unknown as { default: { analysis?: Record<string, unknown> } }).default
  const report = (data?.analysis ?? {}) as VideoAnalysisReport
  return {
    id: DEMO_LOCAL_JSON_TASK_ID,
    videoName: '测试分析报告（本地 JSON）',
    college: '',
    courseName: '',
    teacherName: '',
    status: 'success',
    progress: 100,
    createdAt: new Date().toISOString(),
    // 没有真实视频源；报告页会展示 .video-placeholder 占位。
    videoUrl: undefined,
    report,
  }
}

export async function getVideoTaskDetail(id: string): Promise<VideoTaskDetail | null> {
  if (id === DEMO_LOCAL_JSON_TASK_ID) {
    return loadLocalDemoVideoTaskDetail()
  }

  const mock = mockTaskList.find((t) => t.id === id)
  if (mock) return mock

  let detailRes: VideoDetail | null = null
  try {
    detailRes = await getVideoDetail(id)
  } catch {
    detailRes = null
  }
  if (detailRes) {
    return {
      id: detailRes.id,
      videoName: detailRes.name,
      college: '',
      courseName: '',
      teacherName: '',
      status: mapVideoStatus(detailRes.status),
      progress: detailRes.status === VideoStatusEnum.Success ? 100 : 0,
      createdAt: detailRes.create_time,
      analysisStartTime: detailRes.analysis_start_time,
      videoUrl: resolveVideoMediaUrl(detailRes.path) ?? detailRes.path,
      report: toVideoAnalysisReport(detailRes.analysis_result),
    }
  }

  let result: VideoResultData | null = null
  try {
    result = await getVideoResult(id)
  } catch {
    result = null
  }
  if (!result) return null

  const now = new Date().toISOString()
  return {
    id,
    videoName: `视频任务 ${id}`,
    college: '',
    courseName: '',
    teacherName: '',
    status: 'success',
    progress: 100,
    createdAt: now,
    report: toVideoAnalysisReport(result),
  }
}
