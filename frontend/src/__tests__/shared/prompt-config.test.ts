/**
 * prompt-config 验证规则测试
 * 测试共享配置中的验证函数和常量一致性
 */
import { describe, it, expect } from 'vitest'
import {
  validateDifficulty,
  validateStyle,
  validateNodeType,
  validateGenerateCourseParams,
  detectContentTypes,
  generateContextSuggestions,
  VALID_DIFFICULTY_LEVELS,
  VALID_TEACHING_STYLES,
  VALID_NODE_TYPES,
  PARAMETER_RULES,
  DIFFICULTY_LEVELS,
  TEACHING_STYLES,
  NODE_LEVELS,
  NODE_TYPES,
} from '@/shared/prompt-config'

// ---------------------------------------------------------------------------
// 常量一致性
// ---------------------------------------------------------------------------

describe('常量定义', () => {
  it('难度等级常量与有效列表一致', () => {
    const values = Object.values(DIFFICULTY_LEVELS)
    expect(values).toEqual(VALID_DIFFICULTY_LEVELS)
  })

  it('教学风格常量与有效列表一致', () => {
    const values = Object.values(TEACHING_STYLES)
    expect(values).toEqual(VALID_TEACHING_STYLES)
  })

  it('节点类型常量与有效列表一致', () => {
    const values = Object.values(NODE_TYPES)
    expect(values).toEqual(VALID_NODE_TYPES)
  })

  it('节点层级为 1/2/3', () => {
    expect(NODE_LEVELS.CHAPTER).toBe(1)
    expect(NODE_LEVELS.SECTION).toBe(2)
    expect(NODE_LEVELS.SUBSECTION).toBe(3)
  })
})


// ---------------------------------------------------------------------------
// 基础验证函数
// ---------------------------------------------------------------------------

describe('validateDifficulty', () => {
  it('接受有效难度等级', () => {
    expect(validateDifficulty('beginner')).toBe(true)
    expect(validateDifficulty('intermediate')).toBe(true)
    expect(validateDifficulty('advanced')).toBe(true)
  })

  it('拒绝无效难度等级', () => {
    expect(validateDifficulty('expert')).toBe(false)
    expect(validateDifficulty('')).toBe(false)
    expect(validateDifficulty('BEGINNER')).toBe(false)
  })
})

describe('validateStyle', () => {
  it('接受有效教学风格', () => {
    expect(validateStyle('academic')).toBe(true)
    expect(validateStyle('industrial')).toBe(true)
    expect(validateStyle('socratic')).toBe(true)
    expect(validateStyle('humorous')).toBe(true)
  })

  it('拒绝无效教学风格', () => {
    expect(validateStyle('casual')).toBe(false)
    expect(validateStyle('')).toBe(false)
  })
})

describe('validateNodeType', () => {
  it('接受有效节点类型', () => {
    expect(validateNodeType('original')).toBe(true)
    expect(validateNodeType('expanded')).toBe(true)
    expect(validateNodeType('redefined')).toBe(true)
  })

  it('拒绝无效节点类型', () => {
    expect(validateNodeType('custom')).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// 数值范围验证
// ---------------------------------------------------------------------------

describe('课程结构不再按难度硬编数量', () => {
  it('不提供章节数、子节数和公式密度难度映射', () => {
    expect(PARAMETER_RULES).not.toHaveProperty('chapterCount')
    expect(PARAMETER_RULES).not.toHaveProperty('subChapterCount')
    expect(PARAMETER_RULES).not.toHaveProperty('formulaDensity')
  })
})

// ---------------------------------------------------------------------------
// 复合参数验证
// ---------------------------------------------------------------------------

describe('validateGenerateCourseParams', () => {
  const validParams = {
    subject: '机器学习',
    difficulty: 'intermediate' as const,
    style: 'academic' as const,
  }

  it('有效参数返回 valid: true', () => {
    const result = validateGenerateCourseParams(validParams)
    expect(result.valid).toBe(true)
    expect(result.errors).toHaveLength(0)
  })

  it('缺少 subject 返回错误', () => {
    const result = validateGenerateCourseParams({ ...validParams, subject: '' })
    expect(result.valid).toBe(false)
    expect(result.errors.length).toBeGreaterThan(0)
  })

  it('无效 difficulty 返回错误', () => {
    const result = validateGenerateCourseParams({ ...validParams, difficulty: 'expert' as any })
    expect(result.valid).toBe(false)
  })

  it('无效 style 返回错误', () => {
    const result = validateGenerateCourseParams({ ...validParams, style: 'casual' as any })
    expect(result.valid).toBe(false)
  })

  it('空对象返回多个错误', () => {
    const result = validateGenerateCourseParams({})
    expect(result.valid).toBe(false)
    expect(result.errors.length).toBeGreaterThanOrEqual(3)
  })
})

// ---------------------------------------------------------------------------
// 内容类型检测与上下文建议
// ---------------------------------------------------------------------------

describe('detectContentTypes', () => {
  it('检测定义类内容', () => {
    const types = detectContentTypes('什么是机器学习？机器学习的定义是...')
    expect(types).toContain('definition')
  })

  it('检测公式类内容', () => {
    const types = detectContentTypes('根据公式计算结果')
    expect(types).toContain('formula')
  })

  it('检测多种类型', () => {
    const types = detectContentTypes('定义：根据公式推导步骤如下')
    expect(types).toContain('definition')
    expect(types).toContain('formula')
    expect(types).toContain('process')
  })

  it('无匹配时返回空数组', () => {
    const types = detectContentTypes('Hello World')
    expect(types).toHaveLength(0)
  })
})

describe('generateContextSuggestions', () => {
  it('返回不超过 3 条建议', () => {
    const suggestions = generateContextSuggestions('线性代数', '定义：公式推导步骤案例')
    expect(suggestions.length).toBeLessThanOrEqual(3)
  })

  it('始终包含 keypoints 类型建议', () => {
    const suggestions = generateContextSuggestions('测试节点', '普通内容')
    const types = suggestions.map(s => s.type)
    expect(types).toContain('keypoints')
  })

  it('建议文本包含节点名称', () => {
    const suggestions = generateContextSuggestions('神经网络', '定义概念')
    const hasNodeName = suggestions.some(s => s.text.includes('神经网络'))
    expect(hasNodeName).toBe(true)
  })
})
