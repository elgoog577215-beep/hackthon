const FIELD_LABELS: Record<string, string> = {
  zero_vector_in_set: '零向量属于集合',
  sum: '向量和',
  scalar_multiple: '数乘结果',
  basis: '一组基',
  dimension: '维数',
  preorder: '前序遍历',
  inorder: '中序遍历',
  postorder: '后序遍历',
  bfs_order: '广度优先遍历',
  dfs_order: '深度优先遍历',
  dot_product: '内积',
  norms_squared: '模长平方',
  normalized_basis: '标准正交基',
  target_coordinates: '目标向量的基坐标',
  coefficients: '坐标系数',
  reconstructed: '重构结果',
  dependent: '是否线性相关',
  relation: '线性关系',
  rank: '秩',
  determinant: '行列式',
  kernel_basis: '核空间的一组基',
  image_basis: '像空间的一组基',
  invertible: '是否可逆',
  eigenvalues: '特征值',
  eigenvectors: '特征向量',
  solution: '解',
  residual: '残差',
  singular_values: '奇异值',
  probability: '概率',
  condition_probability: '条件概率',
  product: '矩阵乘积',
  output: '输出',
  stdout: '标准输出',
}

const SEQUENCE_FIELDS = new Set([
  'preorder',
  'inorder',
  'postorder',
  'bfs_order',
  'dfs_order',
])

export function presentSolutionValue(
  value: unknown,
  fieldName?: string,
): string {
  if (value === null || value === undefined) return '无'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) {
    if (!value.length) return '无'
    if (fieldName && SEQUENCE_FIELDS.has(fieldName)) {
      return value.map(item => presentSolutionValue(item)).join(' → ')
    }
    if (value.every(Array.isArray)) {
      return value.map(item => presentVector(item as unknown[])).join('；')
    }
    if (value.every(item => typeof item === 'number')) return presentVector(value)
    return value.map(item => presentSolutionValue(item)).join('、')
  }
  if (typeof value === 'object') {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => (
        `${FIELD_LABELS[key] || fallbackLabel(key)}：${presentSolutionValue(item, key)}`
      ))
      .join('\n')
  }
  return String(value)
}

function presentVector(values: unknown[]): string {
  return `(${values.map(item => presentSolutionValue(item)).join(', ')})`
}

function fallbackLabel(fieldName: string): string {
  const words = fieldName.replaceAll('_', ' ').trim()
  return words ? `${words[0].toUpperCase()}${words.slice(1)}` : '结果'
}
