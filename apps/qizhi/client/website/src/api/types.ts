/**
 * API 类型定义
 */

// 操作枚举
export enum OperationEnum {
  CREATE = 'create',
  UPDATE = 'update',
  DELETE = 'delete',
  COPY = 'copy',
  REORDER = 'reorder',
}

// 资源类型枚举（与后端 /resource/list 等接口一致）
export enum ResourceTypeEnum {
  Outline = 'outline',
  Ppt = 'ppt',
  TeachingPlan = 'teaching_plan',
  /** 题库 / 题目生成（与后端 question_bank 一致） */
  QuestionBank = 'question_bank',
}

/** 资源类型显示名称（中文） */
export function getResourceTypeLabel(type: string | undefined | null): string {
  const t = (type ?? '').toString().toLowerCase()
  if (t === 'outline') return '大纲'
  if (t === 'teaching_plan') return '教案'
  if (t === 'question_bank') return '题目'
  if (t === 'ppt') return 'PPT'
  return type ? String(type) : '—'
}

// 文件格式枚举（根据后端推测）
export enum FileFormatEnum {
  PDF = 'pdf',
  DOCX = 'docx',
  Md = 'md',
  PPTX = 'pptx',
  TXT = 'txt'
}

/** 下载接口使用的格式（/resource/download），与 FileFormatEnum 的 docx/md 对应 */
export type DownloadFormat = 'docx' | 'md'

/** 资源下载请求参数（GET /resource/download），回参为文件流 */
export interface ResourceDownloadRequest {
  id: string
  format: DownloadFormat
  [property: string]: unknown
}

// API 响应结构
export interface ApiResponse<T = any> {
  success: boolean
  data?: T
  error?: string
}

// ========== Feedback API 类型 ==========

/** FeedbackRatingType，评价类型枚举 */
export enum FeedbackRatingType {
  Negative = 'negative',
  Neutral = 'neutral',
  Positive = 'positive',
}

/** SubmitFeedbackParams，提交反馈参数（POST /feedback） */
export interface SubmitFeedbackRequest {
  /** Content，评价文案 */
  content: string
  /** Image Paths，图片路径列表 */
  image_paths?: string[] | null
  /** Star，星级，1-5 */
  star: number
  [property: string]: any
}

/** GET /feedback/list 请求参数 */
export interface FeedbackListRequest {
  /** Min Length */
  min_length?: number | null
  /** Rating Type */
  rating_type?: FeedbackRatingType | null
  [property: string]: any
}

/** FeedbackDetail，反馈详情 */
export interface FeedbackDetail {
  content: string
  create_time: string
  id: string
  star: number
  user_id: string
  [property: string]: any
}

/** RatingStatistics，单类评价统计 */
export interface RatingStatistics {
  count: number
  percentage: number
  [property: string]: any
}

/** FeedbackStatistics，反馈统计 */
export interface FeedbackStatistics {
  average_score: number
  negative: RatingStatistics
  neutral: RatingStatistics
  positive: RatingStatistics
  [property: string]: any
}

// 教学大纲表单（POST /ai/outline 的 outline_form，与后端 OutlineForm 一致）
export interface OutlineForm {
  course_name: string
  course_nature: string
  course_category: string
  course_introduction: string
  credits: number
  hours: number
  offline_hours_ratio: number
  offline_score_ratio: number
  prerequisites: string
  target_grade: string
  target_major: string
  teaching_method: string
  teaching_objectives: string
  /** 思政（选填）：后端若未接入会忽略 */
  ideological_political?: string
  /** 各章节安排（选填）：树形结构，后端若未接入会忽略 */
  chapter_structure?: any
  [property: string]: any
}

/** POST /ai/outline 请求体（OutlineGenerateParams） */
export interface OutlineGenerateParams {
  outline_form?: OutlineForm | null
  /** 已有正文（新文档有；旧部署可能忽略，需配合 resource_id） */
  previous_content?: string | null
  /** 资源 ID（远程 127.0.0.1 等旧版从库读 content，文档生成必填） */
  resource_id?: string | null
  prompt?: string | null
  selected_text?: string | null
  [property: string]: any
}

// 教案 / PPT / 题库等生成参数（大纲流式走 /ai/outline，由 buildOutlineGenerateBody 裁剪请求体）
export interface ResourceGenerateParams {
  operation: OperationEnum
  resource_type: ResourceTypeEnum
  source_resource_id?: number | string | null
  source_resource_path?: string | null
  /** 之前的内容，用于在已有内容基础上继续生成（后端字段名为 previous_content） */
  previous_content?: string | null
  outline_form?: OutlineForm | null
  prompt?: string | null
  selected_text?: string | null
  [property: string]: any
}

// 资源操作参数（POST /resource/operation，与 OpenAPI ResourceCreateParams 等一致）
export interface ResourceOperationParams {
  operation: OperationEnum
  id?: string | null
  name?: string | null
  content?: string | null
  /** 上传落盘后的文件路径（只读资源 create 时必填） */
  path?: string | null
  /** 是否可在线编辑；本地上传只读文件创建时传 false */
  editable?: boolean | null
  related_course_id?: string | null
  related_unit_id?: string | null
  /** 父资源 ID（层级链：教案挂大纲版本，PPT 挂教案版本），create 时可传 */
  parent_resource_id?: string | null
  resource_type?: ResourceTypeEnum | null
  [property: string]: any
}

// 资源绑定参数（POST /resource/binding）
export interface ResourceBindingRequest {
  id: string
  /** Related Course Id */
  related_course_id?: null | string
  /** Related Unit Id */
  related_unit_id?: null | string
  /** 父资源 ID（手动把游离教案/PPT 挂到某个大纲/教案版本下） */
  parent_resource_id?: null | string
  /** Unbind */
  unbind?: boolean
  [property: string]: any
}

// /resource/binding 响应：ApiResponse[NoneType]
export type ResourceBindingResponse = ApiResponse<null>

// 关联课程对象（/resource/ 和 /resource/list 返回的 related_course）
export interface ResourceRelatedCourse {
  id: string
  name: string
  lesson_count: number
  description: string
  labels: string[]
  create_time: string
  manager?: { id: string; username: string; phone: string; email: string; role: string; create_time: string }
}

// 关联章节对象（/resource/list 返回的 related_unit）
export interface ResourceRelatedUnit {
  id: string
  name: string
  description?: string
  level?: number
  create_time?: string
}

/** 资源概要（GET /resource/list 的 ResourceSummary） */
export interface ResourceSummary {
  id: string
  name: string
  resource_type: ResourceTypeEnum | string
  word_count: number
  editable: boolean
  /** 版本号（同作用域内自增，课程下大纲 v1/v2…，大纲下教案 v1/v2…） */
  version_number?: number
  /** 父资源 ID（教案→大纲版本，PPT→教案版本；无则为根级/游离资源） */
  parent_resource_id?: string | null
  /** 子资源（下级版本）数量，层级视图展示用 */
  child_count?: number
  create_time: string
  update_time: string
  related_course?: ResourceRelatedCourse | null
  related_unit?: ResourceRelatedUnit | null
  [property: string]: any
}

// 资源响应数据（GET /resource?id= 详情；在 ResourceSummary 基础上含 path/content 等）
export interface ResourceResponse extends ResourceSummary {
  content?: string
  /** PPT 在线预览(html)地址（生成后落库，再次进入据此渲染预览） */
  ppt_html_url?: string | null
  /** PPT 下载(pptx)地址（生成后落库） */
  ppt_pptx_url?: string | null
  // 详情接口额外字段
  related_unit_name?: string | null
  // 兼容旧字段
  related_course_id?: string | null
  related_course_name?: string | null
  related_unit_id?: string | null
  /** 只读上传文件路径（后端字段 path，兼容旧字段 file_path） */
  path?: string
  file_path?: string
  file_format?: string
  file_size?: number
  course_name?: string
  modified_days?: number
  tags?: string[]
  file_url?: string
}

// 查询单个资源请求参数（/resource/ 请求）
export interface ResourceQueryRequest {
  id: string
  [property: string]: any
}

// 资源列表查询参数（/resource/list 请求，默认返回当前登录用户的资源）
export interface ResourceListParams {
  course_id?: string | null
  keyword?: string | null
  resource_type?: ResourceTypeEnum | null
  unit_id?: string | null
  /** 层级下钻：只返回挂在该父资源下的子版本 */
  parent_resource_id?: string | null
  /** 只返回根级资源（无父资源），课程页大纲版本列表用 */
  root_only?: boolean
  [property: string]: any
}

// ========== 课程 API 类型 ==========

/** 课程列表请求参数（/course/list） */
export interface CourseListRequest {
  keyword?: string | null
  [property: string]: any
}

/** UserDetail，用户详情（课程 managers 等返回） */
export interface UserDetail {
  id: string
  name: string
  zju_id: string
  department: string
  email?: string | null
  phone?: string | null
  create_time: string
  [property: string]: any
}

/** 课程展示扩展信息（extra_info，snake_case，前后端契约严格一致） */
export interface CourseExtraInfo {
  /** 授课对象年级 */
  grade?: string
  /** 课程类别 */
  category?: string
  /** 学分 */
  credits?: number
  /** 授课对象专业 */
  major?: string
  /** 线下学时占比（教学安排） */
  offline_hours_ratio?: number
  /** 线下成绩占比（考核方式） */
  offline_score_ratio?: number
}

/** CourseDetail，课程详情（/course 与 /course/list 返回） */
export interface CourseDetail {
  id: string
  name: string
  lesson_count: number
  description: string
  labels: string[]
  create_time: string
  managers: UserDetail[]
  extra_info?: CourseExtraInfo | null
  [property: string]: any
}

/** 兼容旧命名：项目里大量使用 CourseListItem */
export type CourseListItem = CourseDetail

/** 单元下的资源项（/course/unit/list 返回的 resources） */
export interface UnitResourceItem {
  id: string
  name: string
  resource_type: string
  word_count: number
  create_time: string
  update_time: string
}

/** 单元详情 */
export interface UnitDetail {
  id: string
  name: string
  description: string
  level: number
  create_time: string
}

/** 课程章节（单元）树节点（/course/unit/list 返回） */
export interface UnitListItem {
  detail: UnitDetail
  children: UnitListItem[]
}

/** 课程操作参数（/course/operation，与用户绑定：创建/更新时传 manager_ids 指定负责人） */
export interface CourseOperationParams {
  operation: OperationEnum
  id?: string | null
  name?: string | null
  description?: string | null
  labels?: string[] | null
  lesson_count?: number | null
  /** 负责人用户 id 列表，创建/更新时传入则课程与对应用户绑定 */
  manager_ids?: string[] | null
  /** 课程展示扩展信息 */
  extra_info?: CourseExtraInfo | null
  [property: string]: any
}

/** 章节（单元）操作参数（/course/unit/operation） */
export interface UnitOperationParams {
  operation: OperationEnum
  id?: string | null
  name?: string | null
  description?: string | null
  course_id?: string | null
  parent_unit_id?: string | null
  previous_unit_id?: string | null
  [property: string]: any
}

// ========== 用户 API 类型 ==========

/** POST /user/login 请求体 */
export interface UserLoginParams {
  username: string
  password: string
  [property: string]: any
}

/**
 * 用户身份枚举（注册等扩展字段用；GET /user/current 新文档以 name/zju_id 为主，未必返回 role）
 */
export enum UserRoleEnum {
  Tagger = 'tagger',
  Reviewer = 'reviewer',
  Admin = 'admin',
  Student = 'student',
  Teacher = 'teacher',
}

/**
 * 平台 RBAC 三角色常量。后端 users.role 列只会是这三个之一；
 * 旧的 UserRoleEnum（tagger/reviewer）不参与路由守卫与权限判断。
 */
export const APP_USER_ROLES = ['student', 'teacher', 'admin'] as const
export type AppUserRole = (typeof APP_USER_ROLES)[number]

export function normalizeAppRole(v: unknown): AppUserRole {
  if (v === 'teacher' || v === 'admin') return v
  return 'student'
}

/**
 * GET /user/current 成功时 data（Header：Authorization: Bearer，后接登录接口返回的 token）
 */
export interface UserResponse {
  id: string
  zju_id?: string | null
  name?: string | null
  department?: string | null
  phone?: string | null
  email?: string | null
  create_time: string
  /** 旧版接口可能仍返回 */
  username?: string | null
  role?: UserRoleEnum | string | null
  [property: string]: any
}

/**
 * POST /user/register、POST /user/operation 请求体（UserOperationParams）
 * 文档列出的字段：operation、email、phone；其余如 username、password、role、id 等以扩展字段形式按后端约定传递
 */
export interface UserOperationParams {
  operation: OperationEnum
  email?: string | null
  phone?: string | null
  id?: string | null
  username?: string | null
  password?: string | null
  role?: UserRoleEnum | null
  [property: string]: any
}

// ========== OAuth 统一认证（浙大 IdP，与后端接口文档一致）==========

/** GET /auth/url，无请求参数；响应 ApiResponse[str]，data 为浙大 OAuth 授权页完整 URL */
export type OAuthAuthUrlApiResponse = ApiResponse<string | null>

/**
 * GET /auth/callback 查询参数（Request：code）
 * 前端使用 GET 并带 ?code=，与常见 OAuth 回调一致
 */
export interface OAuthCallbackRequest {
  code: string
  [property: string]: any
}

/** GET /auth/callback 响应 ApiResponse[str]，data 为系统访问 token */
export type OAuthCallbackApiResponse = ApiResponse<string | null>

/** GET /auth/test-login（仅开发环境）；响应 ApiResponse[str]，data 为测试用户 token */
export type OAuthTestLoginApiResponse = ApiResponse<string | null>

/**
 * DEV 服务器测试登录（仅 ENV=DEV 时前端会展示入口）
 * POST /auth/test-login
 */
export interface OAuthDevTestLoginRequest {
  name: string
  zju_id: string
  [property: string]: any
}

/** POST /auth/test-login（仅开发环境）；响应 ApiResponse[str]，data 为测试用户 token */
export type OAuthDevTestLoginApiResponse = ApiResponse<string | null>

// ========== 智能体广场 / 运营后台 ==========

/** GET /agents/public 返回的卡片信息（与首页 HomeView 渲染绑定） */
export interface PublicAgentDetail {
  id: string
  card_key?: string | null
  title: string
  description: string
  tags: string[]
  popular: boolean
  badge_bg: string
  badge_fg: string
  icon_path: string
  href?: string | null
  route_to?: string | null
  sort_order: number
}

/** GET /admin/agents 返回的后台详情（包含上架开关与时间） */
export interface AdminAgentDetail extends PublicAgentDetail {
  enabled: boolean
  create_time?: string | null
  update_time?: string | null
}

/** POST /admin/agents/operation 请求体 */
export interface AdminAgentOperationParams {
  operation: OperationEnum
  id?: string | null
  card_key?: string | null
  title?: string | null
  description?: string | null
  tags?: string[] | null
  popular?: boolean | null
  badge_bg?: string | null
  badge_fg?: string | null
  icon_path?: string | null
  href?: string | null
  route_to?: string | null
  enabled?: boolean | null
  sort_order?: number | null
}

/** POST /admin/agents/toggle 请求体 */
export interface AdminAgentToggleParams {
  id: string
  enabled: boolean
}

/** POST /admin/agents/reorder 请求体（拖拽后提交完整新顺序） */
export interface AdminAgentReorderParams {
  id_list: string[]
}

/** GET /admin/feedbacks 返回的反馈项（JOIN 用户） */
export interface AdminFeedbackDetail {
  id: string
  user_id?: string | null
  user_name?: string | null
  user_zju_id?: string | null
  user_department?: string | null
  star: number
  content: string
  image_paths?: string[] | null
  create_time: string
}

/** GET /admin/dashboard/users 返回的用户明细 */
export interface AdminUserDetail {
  id: string
  zju_id?: string | null
  name?: string | null
  department?: string | null
  phone?: string | null
  email?: string | null
  role?: AppUserRole | string | null
  create_time?: string | null
}

/** GET /admin/dashboard/stats 返回的驾驶舱指标 */
export interface DashboardStats {
  total_users: number
  dau: number
  wau: number
  as_of: string
}

/** GET /admin/dashboard/feature-usage 返回项 */
export interface FeatureUsageItem {
  feature_type: string
  feature_key?: string | null
  label: string
  count: number
  unique_users: number
  pending?: boolean
}

/** GET /admin/dashboard/agent-usage 返回项 */
export interface AgentUsageItem {
  agent_id: string
  title: string
  count: number
  unique_users: number
}

/** POST /auth/logout，无请求参数；响应 ApiResponse[NoneType]，data 为 null */
export type OAuthLogoutApiResponse = ApiResponse<null>

// ========== 智能体广场 API 类型 ==========

/** GET /agents/public 返回的公开智能体卡片 */
export interface PublicAgentDetail {
  id: string
  card_key?: string | null
  title: string
  description: string
  tags: string[]
  popular: boolean
  badge_bg: string
  badge_fg: string
  icon_path: string
  href?: string | null
  route_to?: string | null
  sort_order: number
}

// ========== 审计日志 ==========

/** 审计日志责任主体类型（与后端 AuditActorType 对齐） */
export type AuditActorType = 'admin' | 'user' | 'agent' | 'system'

/** GET /admin/audit-logs 返回的单条审计记录 */
export interface AuditLogDetail {
  id: string
  actor_type: AuditActorType | string
  actor_id?: string | null
  actor_label?: string | null
  action: string
  target_type?: string | null
  target_id?: string | null
  target_label?: string | null
  payload?: Record<string, any> | null
  result?: string | null
  request_ip?: string | null
  user_agent?: string | null
  extra?: Record<string, any> | null
  create_time: string
}

/** GET /admin/audit-logs 查询过滤参数 */
export interface AuditLogListParams {
  actor_type?: AuditActorType | string | null
  actor_id?: string | null
  action?: string | null
  target_type?: string | null
  target_id?: string | null
  /** ISO 8601 时间字符串 */
  time_from?: string | null
  time_to?: string | null
  limit?: number
  offset?: number
}

/** POST /admin/audit/report 与 POST /audit/report 共用请求体 */
export interface AuditReportParams {
  action: string
  actor_id?: string | null
  actor_label?: string | null
  target_type?: string | null
  target_id?: string | null
  target_label?: string | null
  payload?: Record<string, any> | null
  result?: string | null
  extra?: Record<string, any> | null
  idempotency_key?: string | null
}
