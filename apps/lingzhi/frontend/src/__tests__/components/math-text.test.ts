import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MathText from '@/components/MathText.vue'

describe('MathText', () => {
  it('在结构化字段中使用共享 KaTeX 链渲染截图里的公式', () => {
    const wrapper = mount(MathText, {
      props: {
        content: String.raw`写出 $\nabla^2(x^2y+z)$；解一维 $x \in [0,2], \varphi(0)=1, \varphi(2)=3$ 的方程。`,
      },
    })

    expect(wrapper.attributes('data-math-rendered')).toBe('true')
    expect(wrapper.findAll('.katex')).toHaveLength(2)
    expect(wrapper.find('.math-fallback').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('\\nabla')
    expect(wrapper.text()).not.toContain('\\varphi')
    expect(wrapper.text()).not.toContain('$')
  })

  it('不把金额、代码标签和普通界面文字误判为公式', () => {
    const wrapper = mount(MathText, {
      props: { content: '预算 $100，运行 npm test 后保存。' },
    })

    expect(wrapper.attributes('data-math-rendered')).toBeUndefined()
    expect(wrapper.text()).toBe('预算 $100，运行 npm test 后保存。')
    expect(wrapper.find('.katex').exists()).toBe(false)
  })

  it('修复没有分隔符的旧公式，同时保留后面的中文说明', () => {
    const wrapper = mount(MathText, {
      props: {
        content: String.raw`计算 \nabla^2(x^2y+z)，再检查边界条件。`,
      },
    })

    expect(wrapper.attributes('data-math-rendered')).toBe('true')
    expect(wrapper.find('.katex').exists()).toBe(true)
    expect(wrapper.text()).toContain('再检查边界条件')
    expect(wrapper.text()).not.toContain('\\nabla')
  })

  it.each([
    String.raw`变量 x \in [0,2]`,
    String.raw`勾股关系 x^2+y^2=z^2`,
    String.raw`保留宽松分隔符 $ x^2 + y^2 = z^2 $`,
  ])('识别常见公式写法：%s', (content) => {
    const wrapper = mount(MathText, { props: { content } })
    expect(wrapper.find('.katex').exists()).toBe(true)
  })

  it('不把同一句里的两个金额当作公式分隔符', () => {
    const content = '预算 $100，材料费 $200。'
    const wrapper = mount(MathText, { props: { content } })
    expect(wrapper.attributes('data-math-rendered')).toBeUndefined()
    expect(wrapper.text()).toBe(content)
  })

  it('公式字段仍经过 HTML 清洗', () => {
    const wrapper = mount(MathText, {
      props: {
        content: String.raw`<img src=x onerror="alert(1)">令 $x^2=1$<script>alert(2)</script>`,
      },
    })

    expect(wrapper.find('.katex').exists()).toBe(true)
    expect(wrapper.find('img').attributes('onerror')).toBeUndefined()
    expect(wrapper.find('script').exists()).toBe(false)
    expect(wrapper.html()).not.toContain('onerror')
  })
})
