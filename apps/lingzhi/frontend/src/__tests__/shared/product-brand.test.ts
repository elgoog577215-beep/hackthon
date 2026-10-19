import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, describe, expect, it } from 'vitest'
import ProductBrand from '@/components/ProductBrand.vue'
import { activeLocale } from '@/shared/i18n'
import { productSurface, syncProductDocument, type ProductSurface } from '@/shared/product-brand'

afterEach(() => { activeLocale.value = 'zh' })

describe('teacher and student product branding', () => {
  it.each([
    ['teacher', '/study', undefined, 'teacher'],
    ['teacher', '/course/c1/learn', undefined, 'teacher'],
    ['student', '/course/c1/learn', '1', 'student'],
    ['student', '/courses', undefined, 'student'],
    [undefined, '/courses', undefined, 'teacher'],
    [undefined, '/course/c1/workspace/setup', undefined, 'teacher'],
    [undefined, '/course/c1/learn', '1', 'teacher'],
    [undefined, '/course/c1/learn/n1', undefined, 'student'],
    [undefined, '/study/material-1', undefined, 'student'],
  ])('keeps the configured role authoritative (%s %s)', (configured, path, preview, expected) => {
    expect(productSurface(configured, path!, preview)).toBe(expected)
  })

  it.each([
    ['teacher', 'zh', '启智', '教师端', '/courses', 'qizhi-favicon.svg'],
    ['student', 'zh', '灵知', '学生端', '/study', 'lingzhi-favicon.svg'],
    ['teacher', 'en', 'Qizhi', 'Teacher', '/courses', 'qizhi-favicon.svg'],
    ['student', 'en', 'Lingzhi', 'Student', '/study', 'lingzhi-favicon.svg'],
  ] as const)('aligns %s %s name, role, home, tab title and icon', async (surface, locale, name, role, home, icon) => {
    activeLocale.value = locale
    const router = createRouter({ history:createMemoryHistory(), routes:[
      { path:'/courses', component:{ template:'<div />' } }, { path:'/study', component:{ template:'<div />' } },
    ] })
    await router.push(home)
    const wrapper = mount(ProductBrand, { props:{ surface:surface as ProductSurface }, global:{ plugins:[router] } })
    expect(wrapper.get('strong').text()).toBe(name)
    expect(wrapper.get('a').attributes('aria-label')).toBe(`${name} · ${role}`)
    expect(wrapper.get('a').attributes('href')).toBe(home)
    expect(wrapper.get('img').attributes('alt')).toBe(name)
    expect(wrapper.get('img').attributes('src')).toContain(icon)
    syncProductDocument(surface, locale, '/lingzhi/')
    expect(document.title).toBe(`${name} · ${role}`)
    expect(document.querySelector('link[rel="icon"]')?.getAttribute('href')).toBe(`/lingzhi/${icon}`)
    wrapper.unmount()
  })
})
