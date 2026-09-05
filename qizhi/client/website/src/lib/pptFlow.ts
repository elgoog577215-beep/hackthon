import { operateResource } from '../api/resource'
import { OperationEnum, ResourceTypeEnum } from '../api/types'

export interface CreatePptOptions {
  name?: string
  relatedUserId?: string
  courseId?: string
  unitId?: string
  /** 父资源（教案版本）ID，传入后 PPT 挂在该教案下成为其子版本 */
  parentResourceId?: string
}

/** 创建空 PPT 资源并可选绑定课程章节/教案版本，返回资源 id（用于跳转到本地生成页） */
export async function createPptResource(options: CreatePptOptions = {}): Promise<string> {
  // 课程/父资源直接随 create 提交：后端按所在作用域（教案版本下或课程下）分配版本号
  const id = await operateResource({
    operation: OperationEnum.CREATE,
    name: (options.name || 'PPT').trim() || 'PPT',
    resource_type: ResourceTypeEnum.Ppt,
    editable: true,
    related_user_id: options.relatedUserId,
    related_course_id: options.courseId || null,
    related_unit_id: options.unitId || null,
    parent_resource_id: options.parentResourceId || null,
  })
  if (!id) throw new Error('创建成功但未返回资源 id')
  return id
}
