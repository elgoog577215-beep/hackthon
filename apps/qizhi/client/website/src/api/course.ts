/**
 * 课程相关 API
 */

import { get, post } from './request'
import type {
  ApiResponse,
  CourseListItem,
  CourseListRequest,
  CourseOperationParams,
  UnitListItem,
  UnitOperationParams,
} from './types'
import { OperationEnum } from './types'

const API_PREFIX = '/course'

/**
 * 获取课程列表
 * @param params 查询参数 keyword
 */
export async function listCourses(
  params: CourseListRequest = {}
): Promise<CourseListItem[]> {
  const response = await get<ApiResponse<CourseListItem[]>>(
    `${API_PREFIX}/list`,
    params
  )

  if (!response.success || !response.data) {
    throw new Error(response.error || '获取课程列表失败')
  }

  return response.data || []
}

/**
 * 获取课程的章节（单元）列表（树形）
 * @param courseId 课程 ID
 */
export async function listUnitsByCourse(courseId: string): Promise<UnitListItem[]> {
  const response = await get<ApiResponse<UnitListItem[]>>(
    `${API_PREFIX}/unit/list`,
    { course_id: courseId }
  )
  if (!response.success || !response.data) {
    throw new Error(response.error || '获取章节列表失败')
  }
  return response.data ?? []
}

/**
 * 查询单门课程详情
 * @param id 课程 ID
 */
export async function queryCourse(id: string): Promise<CourseListItem> {
  const response = await get<ApiResponse<CourseListItem>>(
    `${API_PREFIX}`,
    { id }
  )

  if (!response.success || !response.data) {
    throw new Error(response.error || '获取课程详情失败')
  }

  return response.data
}

/**
 * 课程操作：创建 / 更新 / 删除
 * @param params operation 必填；create 时传 name 等；update/delete 时传 id
 * @returns 成功时返回 data 字符串（如新课程 id 或提示信息）
 */
export async function operateCourse(
  params: CourseOperationParams
): Promise<string> {
  const body: Record<string, any> = {
    operation: params.operation,
  }
  if (params.id != null) body.id = params.id
  if (params.name != null) body.name = params.name
  if (params.description != null) body.description = params.description
  if (params.labels != null) body.labels = params.labels
  if (params.lesson_count != null) body.lesson_count = params.lesson_count
  if (params.manager_ids != null) body.manager_ids = params.manager_ids
  if (params.extra_info != null) body.extra_info = params.extra_info

  const response = await post<ApiResponse<string>>(
    `${API_PREFIX}/operation`,
    body
  )

  if (!response.success) {
    throw new Error(response.error || '课程操作失败')
  }

  return response.data ?? ''
}

/**
 * 章节（单元）操作：创建 / 更新 / 删除 / 复制（删除时后端会解绑该章节下的资源，不删除资源）
 *
 * 字段说明：
 * - CREATE：需 course_id、name；可选 parent_unit_id（顶层不传）、previous_unit_id（当前层级第一个不传）；不传 id
 * - UPDATE/DELETE/COPY：需 id；UPDATE 还需传要更新的字段（name、description 等）
 *
 * @param params operation 必填；根据操作类型传对应字段
 */
export async function operateUnit(
  params: UnitOperationParams
): Promise<string> {
  const body: Record<string, unknown> = {
    operation: params.operation,
  }

  // CREATE 操作：不传 id，需要 course_id 和 name
  if (params.operation === OperationEnum.CREATE) {
    if (params.course_id != null) body.course_id = params.course_id
    if (params.name != null) body.name = params.name
    if (params.description != null) body.description = params.description
    // parent_unit_id：顶层不传，有父级时传
    if (params.parent_unit_id != null) body.parent_unit_id = params.parent_unit_id
    // previous_unit_id：当前层级第一个不传，有前一个时传（用于链表插入保证顺序）
    if (params.previous_unit_id != null) body.previous_unit_id = params.previous_unit_id
  } else if (params.operation === OperationEnum.REORDER) {
    if (params.id != null) body.id = params.id
    // null 表示移到同层级最前
    if (params.previous_unit_id !== undefined) body.previous_unit_id = params.previous_unit_id
  } else {
    // UPDATE/DELETE/COPY：需要 id
    if (params.id != null) body.id = params.id
    // UPDATE 操作：传要更新的字段
    if (params.operation === OperationEnum.UPDATE) {
      if (params.name != null) body.name = params.name
      if (params.description != null) body.description = params.description
    }
  }

  const response = await post<ApiResponse<string>>(
    `${API_PREFIX}/unit/operation`,
    body
  )

  if (!response.success) {
    const msg = response.error || '章节操作失败'
    if (import.meta.env.DEV && body.operation === 'delete') {
      console.error('[API] 章节删除失败', { 请求体: body, 响应: response })
    }
    throw new Error(msg)
  }

  return response.data ?? ''
}

/**
 * POST /course/visit：用户进入「我的课程」页面时埋点。
 * fire-and-forget，不阻塞页面加载，失败仅在 DEV 下打 warn。
 */
export async function visitMyCourses(): Promise<void> {
  try {
    await post<ApiResponse<null>>(`${API_PREFIX}/visit`, undefined, {
      suppressAuthRedirect: true,
    })
  } catch (e) {
    if (import.meta.env.DEV) console.warn('[course.visitMyCourses] failed', e)
  }
}
