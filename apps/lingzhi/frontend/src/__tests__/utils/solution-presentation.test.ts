import { describe, expect, it } from 'vitest'

import { presentSolutionValue } from '../../utils/solution-presentation'

describe('student solution presentation', () => {
  it('renders structured mathematical answers as readable Chinese text', () => {
    const text = presentSolutionValue({
      zero_vector_in_set: true,
      sum: [1, 0, -1],
      basis: [[1, -1, 0], [0, 1, -1]],
      dimension: 2,
    })

    expect(text).toContain('零向量属于集合：是')
    expect(text).toContain('向量和：(1, 0, -1)')
    expect(text).toContain('一组基：(1, -1, 0)；(0, 1, -1)')
    expect(text).toContain('维数：2')
    expect(text).not.toContain('{')
    expect(text).not.toContain('"zero_vector_in_set"')
  })

  it('uses a readable sequence for traversal answers', () => {
    expect(presentSolutionValue(
      { preorder: [30, 20, 10, 25, 40, 50] },
    )).toBe('前序遍历：30 → 20 → 10 → 25 → 40 → 50')
  })
})
