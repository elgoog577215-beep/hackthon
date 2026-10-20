import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import HandoutReadingGuide from '@/components/HandoutReadingGuide.vue'
import HandoutTableOfContents from '@/components/HandoutTableOfContents.vue'
import { buildHandoutPrintBody } from '@/utils/handout-print'
import { setLocale } from '@/shared/i18n'
import zh from '../../../public/locales/zh/translation.json'
import en from '../../../public/locales/en/translation.json'

beforeEach(async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({ ok: true, json: async () => url.includes('/en/') ? en : zh })))
  await setLocale('zh')
})

describe('Handout reading actions', () => {
  it('目录点击在当前阅读器内定位并通知编辑范围，不触发路由跳转', async () => {
    const target = document.createElement('section')
    target.id = 'reading-target'
    target.scrollIntoView = vi.fn()
    document.body.append(target)
    const currentUrl = window.location.href
    const wrapper = mount(HandoutTableOfContents, { props: { entries: [{ id: target.id, title: '当前位置' }] } })
    await wrapper.get('a').trigger('click')
    expect(target.scrollIntoView).toHaveBeenCalledWith({ behavior: 'instant', block: 'start' })
    expect(wrapper.emitted('navigate')).toEqual([['reading-target']])
    expect(window.location.href).toBe(currentUrl)
    wrapper.unmount(); target.remove()
  })

  it('长章节滚动时定位具体内容块，章节容器不遮盖子目录定位', async () => {
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => { callback(0); return 1 })
    vi.stubGlobal('cancelAnimationFrame', vi.fn())
    const root = document.createElement('article')
    const positions: Record<string, number> = { chapter: -900, definition: 30, derivation: 640 }
    Object.keys(positions).forEach(id => {
      const node = document.createElement('section')
      node.id = id
      node.getBoundingClientRect = () => ({ top: positions[id] } as DOMRect)
      root.append(node)
    })
    document.body.append(root)
    const wrapper = mount(HandoutTableOfContents, { props: { entries: [
      { id: 'chapter', title: '本讲' }, { id: 'definition', title: '定义', child: true }, { id: 'derivation', title: '推导', child: true },
    ] } })
    await nextTick()
    expect(wrapper.get('[aria-current="location"]').text()).toBe('定义')
    positions.definition = -700
    positions.derivation = 30
    window.dispatchEvent(new Event('scroll'))
    await nextTick()
    expect(wrapper.get('[aria-current="location"]').text()).toBe('推导')
    wrapper.unmount()
    root.remove()
  })

  it('批量展开只作用于当前讲义，单个解答改变后同步按钮', async () => {
    const root = document.createElement('article')
    root.innerHTML = '<details class="handout-block--answer"><summary>A</summary>Answer A</details><details class="handout-block--answer" open><summary>B</summary>Answer B</details><details><summary>资料</summary>Source</details>'
    const wrapper = mount(HandoutReadingGuide, { props: { target: root } })
    const answers = root.querySelectorAll<HTMLDetailsElement>('.handout-block--answer')
    await wrapper.get('button').trigger('click')
    expect(Array.from(answers).every(node => node.open)).toBe(true)
    expect(root.querySelector('details:not(.handout-block--answer)')?.hasAttribute('open')).toBe(false)
    expect(wrapper.get('button').text()).toBe('收起全部解答')
    answers[0]!.open = false
    answers[0]!.dispatchEvent(new Event('toggle'))
    await nextTick()
    expect(wrapper.get('button').text()).toBe('展开全部解答')
    wrapper.unmount()
  })

  it('草稿变成带关联的完成解答后，阅读操作可用且支持英文', async () => {
    await setLocale('en')
    const root = document.createElement('article')
    const wrapper = mount(HandoutReadingGuide, { props: { target: root } })
    expect(wrapper.text()).not.toContain('Show all answers')
    const answer = document.createElement('details')
    answer.className = 'handout-block--answer'
    root.append(answer)
    await nextTick()
    await nextTick()
    expect(wrapper.text()).toContain('Show all answers')
    expect(wrapper.text()).toContain('Print / Save PDF')
    wrapper.unmount()
  })

  it('打印包含完整解答、公式和图，保留屏幕折叠状态且标题按文本处理', () => {
    const root = document.createElement('article')
    root.innerHTML = '<div data-handout-print-exclude>目录</div><section id="original-block"><span class="katex">x²</span><img src="/figure.svg" alt="Figure"><details class="handout-block--answer"><summary>解析</summary><p>完整解答</p></details><button>调整这段</button></section>'
    const printed = buildHandoutPrintBody(root, '<script>unsafe</script>')
    expect(printed.querySelector('details')?.open).toBe(true)
    expect(root.querySelector('details')?.open).toBe(false)
    expect(printed.querySelector('#original-block .katex')?.textContent).toBe('x²')
    expect(printed.querySelector('img')?.getAttribute('src')).toBe('/figure.svg')
    expect(printed.querySelector('h1')?.textContent).toBe('<script>unsafe</script>')
    expect(printed.querySelector('script')).toBeNull()
    expect(printed.querySelector('button')).toBeNull()
    expect(printed.textContent).not.toContain('目录')
    expect(root.querySelector('button')).not.toBeNull()
  })
})
