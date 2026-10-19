import { beforeEach, describe, expect, it, vi } from 'vitest';
vi.mock('mermaid', () => ({ default: { initialize: vi.fn(), run: vi.fn() } }));
vi.mock('highlight.js/styles/atom-one-dark.css', () => ({}));

import { renderMarkdown } from '@/utils/markdown';
import { renderFailures, resetRenderFailures } from '@/utils/render-diagnostics';

const broken = String.raw`\mathbf{u} + \mathbf{v} = (u_1 + v_1, ${String.fromCharCode(92)}u_2 + v_2)`;
const correct = String.raw`\mathbf{u} + \mathbf{v} = (u_1 + v_1, u_2 + v_2)`;
const dom = (source: string) => {
  const box = document.createElement('div');
  box.innerHTML = renderMarkdown(source);
  return box;
};

describe('indexed variable escape compatibility with real KaTeX', () => {
  beforeEach(resetRenderFailures);

  it.each([
    [`$$${broken}$$`, `$$${correct}$$`],
    [String.raw`\[${broken}\]`, String.raw`\[${correct}\]`],
    [`向量加法 $${broken}$。`, `向量加法 $${correct}$。`],
    [`Vector addition $${broken}$ preserves both components.`, `Vector addition $${correct}$ preserves both components.`],
  ])('renders the screenshot formula exactly like its unescaped component: %s', (source, expected) => {
    const box = dom(source);
    expect(box.querySelectorAll('.math-fallback,.katex-error')).toHaveLength(0);
    expect(box.querySelector('.katex')?.outerHTML).toBe(dom(expected).querySelector('.katex')?.outerHTML);
    expect(renderFailures()).toHaveLength(0);
  });

  it('handles more than one damaged component without changing operands or operators', () => {
    const box = dom(String.raw`$$\mathbf{u}+\mathbf{v}=(u_1+v_1,${String.fromCharCode(92)}u_2+\v_2,${String.fromCharCode(92)}u_3-\v_3,${String.fromCharCode(92)}u_4+\v_4)$$`);
    const expected = dom(String.raw`$$\mathbf{u}+\mathbf{v}=(u_1+v_1,u_2+v_2,u_3-v_3,u_4+v_4)$$`);
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0);
    expect(box.querySelector('.katex')?.outerHTML).toBe(expected.querySelector('.katex')?.outerHTML);
  });

  it('accepts an already established indexed variable without requiring bold notation', () => {
    const box = dom(String.raw`$$x_1+${String.fromCharCode(92)}x_2=x_3$$`);
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0);
    expect(box.querySelector('.katex')?.outerHTML).toBe(dom(String.raw`$$x_1+x_2=x_3$$`).querySelector('.katex')?.outerHTML);
  });

  it('leaves valid accents, commands and matrix row breaks intact', () => {
    const box = dom(String.raw`$\text{\u{a}, \v{c}}$ and $\hat{u}_2+\partial_1 f$.

$$\begin{bmatrix}u_1 \${String.fromCharCode(92)}u_2\end{bmatrix}$$`);
    expect(box.querySelectorAll('.katex')).toHaveLength(3);
    expect(box.querySelectorAll('.math-fallback,.katex-error')).toHaveLength(0);
    expect(box.querySelectorAll('.mord.accent').length).toBeGreaterThan(0);
    expect(box.textContent).toContain('u');
    expect(renderFailures()).toHaveLength(0);
  });

  it.each([
    String.raw`${String.fromCharCode(92)}u_2`,
    String.raw`\text{u_1}+${String.fromCharCode(92)}u_2`,
    String.raw`\mathbf{u}+\unknown_2`,
    String.raw`\mathbf{u}+\u{`,
  ])('preserves source and reports errors when a repair is ambiguous or unrelated: %s', formula => {
    const box = dom(`$$${formula}$$`);
    expect(box.querySelector('.math-fallback')?.textContent).toBe(formula);
    expect(renderFailures()).toHaveLength(1);
    expect(renderFailures()[0]?.source).toBe(formula);
  });

  it('preserves a text accent next to an established vector variable', () => {
    const box = dom(String.raw`$$\mathbf{u}+\text{${String.fromCharCode(92)}u_2}$$`);
    const expected = dom(String.raw`$$\mathbf{u}+\text{\u{\_}2}$$`);
    expect(box.querySelectorAll('.math-fallback')).toHaveLength(0);
    expect(box.querySelector('.katex')?.textContent).toBe(expected.querySelector('.katex')?.textContent);
    expect(box.querySelectorAll('.accent').length).toBeGreaterThan(0);
  });

  it('keeps LaTeX examples inside Markdown code literal', () => {
    const box = dom('Inline `' + broken + '`\n\n```latex\n' + broken + '\n```');
    expect(box.querySelectorAll('.katex,.math-fallback')).toHaveLength(0);
    expect(box.querySelector('p code')?.textContent).toBe(broken);
    expect(box.querySelector('pre code')?.textContent?.trim()).toBe(broken);
    expect(renderFailures()).toHaveLength(0);
  });
});
