import { t } from '@/shared/i18n'

/**
 * 知识记录来源状态的显示文案。
 *
 * 抽成共用函数而不是各处各写一份：这几种来源**必须显示成不同的话**，
 * 一旦某处漏改，教师就会在那个界面里把「模型凭通用知识写的」当成
 * 「有教材依据的」——这正是这组文案存在的唯一理由。
 * 树视图与关系图共用同一份，才不会一边改一边漏。
 */
export function knowledgeSourceLabel(source: string): string {
  if (source === 'course_path') return t('knowledgeLibrary.sourceCoursePath', '课程路径投影')
  // material_grounded 与 course_generated 必须显示成不同的话：教师要据此判断
  // 这条知识是有资料依据的，还是模型凭通用知识写的。
  if (source === 'material_grounded') return t('knowledgeLibrary.sourceMaterial', '资料来源')
  // 联网必须与教师上传资料显示成不同的话，否则 license_unknown 的网页看起来
  // 和教师自己的教材一样可信。
  if (source === 'web_grounded') return t('knowledgeLibrary.sourceWeb', '联网检索来源')
  if (source === 'course_generated') return t('knowledgeLibrary.sourceModel', '模型推断')
  return t('knowledgeLibrary.sourceCourse', '当前课程知识库')
}
