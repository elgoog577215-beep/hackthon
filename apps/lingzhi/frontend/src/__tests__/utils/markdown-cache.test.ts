import { afterEach, describe, expect, it, vi } from 'vitest';
import katex from 'katex';
import { renderMarkdown } from '@/utils/markdown';
import { renderFailures, resetRenderFailures, withRenderContext } from '@/utils/render-diagnostics';

const dom = (source: string) => {
  const box = document.createElement('div');
  box.innerHTML = renderMarkdown(source);
  return box;
};
afterEach(() => vi.restoreAllMocks());

describe('formula reuse in growing Markdown', () => {
  it('reuses completed formulas across documents while showing every appended tail', () => {
    const render = vi.spyOn(katex, 'renderToString');
    const formula = String.raw`q_{971}^2+\frac{1}{971}`;
    const first = dom(`$${formula}$\n\n第0轮`);
    expect(render).toHaveBeenCalledTimes(1);
    const exactFormula = first.querySelector('.katex')?.outerHTML;
    for (let round = 1; round <= 20; round++) {
      const next = dom(`$${formula}$\n\n第${round}轮`);
      expect(next.querySelector('.katex')?.outerHTML).toBe(exactFormula);
      expect(next.textContent).toContain(`第${round}轮`);
    }
    expect(render).toHaveBeenCalledTimes(1);
    dom(`$${formula}$\n\n$z_{972}$`);
    expect(render).toHaveBeenCalledTimes(2);
  });

  it('keeps inline and display results distinct', () => {
    const render = vi.spyOn(katex, 'renderToString');
    const formula = String.raw`\sum_{k=1}^{973}k`;
    const inline = dom(`Inline $${formula}$.`);
    const display = dom(`$$${formula}$$`);
    expect(render).toHaveBeenCalledTimes(2);
    expect(inline.querySelector('.katex-display')).toBeNull();
    expect(display.querySelector('.katex-display')).not.toBeNull();
  });

  it('retains parse diagnostics with the current context for unsuccessful formulas', () => {
    resetRenderFailures();
    const render = vi.spyOn(katex, 'renderToString');
    const source = String.raw`$\unknownCachedMath_{974}$`;
    withRenderContext('first-answer', () => dom(`${source}\n\nFirst`));
    withRenderContext('second-answer', () => dom(`${source}\n\nSecond`));
    expect(render).toHaveBeenCalledTimes(2);
    expect(renderFailures().map(item => item.contextId)).toEqual(['first-answer', 'second-answer']);
  });

  it('resolves a later reference definition and preserves list/table semantics', () => {
    const source = 'Read [the source][book]. $x_{975}$\n\n1. First\n2. Second\n\n| Formula | Meaning |\n| --- | --- |\n| $P(A|B)$ | Conditional |';
    expect(dom(source).querySelector('a')).toBeNull();
    const next = dom(`${source}\n\n[book]: https://example.com/chapter`);
    expect(next.querySelector('a')?.getAttribute('href')).toBe('https://example.com/chapter');
    expect(next.querySelectorAll('li')).toHaveLength(2);
    expect(next.querySelectorAll('tbody td')).toHaveLength(2);
    expect(next.querySelectorAll('.katex')).toHaveLength(2);
    expect(next.querySelector('[data-rendered-math]')).toBeNull();
  });

  it('still sanitizes math commands and surrounding hostile HTML on cache hits', () => {
    const formula = String.raw`\href{javascript:alert(976)}{x}+\htmlData{audit=literal}{y}`;
    for (const tail of ['first', 'second']) {
      const box = dom(`$${formula}$\n\n<a href="javascript:alert(1)" onclick="alert(1)">${tail}</a><img src=x onerror="alert(1)"><script>alert(1)</script>`);
      expect(box.querySelector('.katex')).not.toBeNull();
      expect(box.querySelector('script,[onclick],[onerror],a[href^="javascript:"]')).toBeNull();
      expect(box.textContent).toContain(tail);
      expect(box.querySelector('[data-audit]')?.getAttribute('data-audit')).toBe('literal');
    }
  });

  it('does not replace a lookalike token in text, code, attributes or untrusted spans', () => {
    const fake = '<span data-rendered-math="lzmath-user-controlled-0"></span>';
    const box = dom(`$x_{977}$\n\n${fake}\n\n\`${fake}\`\n\n<div title="&lt;span data-rendered-math=&quot;lzmath-user-controlled-0&quot;&gt;&lt;/span&gt;">literal</div>`);
    expect(box.querySelectorAll('.katex')).toHaveLength(1);
    expect(box.querySelector('[data-rendered-math="lzmath-user-controlled-0"]')?.innerHTML).toBe('');
    expect(box.querySelector('code')?.textContent).toBe(fake);
    expect(box.querySelector('[title]')?.getAttribute('title')).toBe(fake);
  });

  it('does not insert math HTML into an attribute containing a formula', () => {
    const box = dom('<div title="$x_{978}$">Attribute stays literal</div>\n\n$x_{979}$');
    expect(box.querySelector('[title]')?.getAttribute('title')).toBe('$x_{978}$');
    expect(box.querySelectorAll('.katex')).toHaveLength(1);
  });

  it.each(['tilde', 'long-backtick', 'indent', 'blockquote', 'list'])('keeps matrix examples literal inside %s code blocks', kind => {
    const formula = String.raw`$A=\begin{bmatrix}1&2\\3&4\end{bmatrix}$`;
    const code = kind === 'tilde' ? `~~~latex\n${formula}\n~~~`
      : kind === 'long-backtick' ? `\`\`\`\`latex\n${formula}\n\`\`\`\``
      : kind === 'indent' ? `    ${formula}`
      : kind === 'blockquote' ? `> ~~~latex\n> ${formula}\n> ~~~`
      : `1. Example\n\n    ~~~latex\n    ${formula}\n    ~~~`;
    const box = dom(`${code}\n\n$z_{980}$`);
    expect(box.querySelector('pre code')?.textContent?.trim()).toBe(formula);
    expect(box.querySelector('pre .katex')).toBeNull();
    expect(box.querySelectorAll('.katex')).toHaveLength(1);
    const encoded = box.querySelector('.copy-btn')?.getAttribute('data-code');
    if (kind !== 'indent') expect(decodeURIComponent(encoded || '').trim()).toBe(formula);
    expect(box.textContent).not.toContain('MATHDISPLAYPLACEHOLDER');
  });
});

describe('fence metadata uses actual Markdown structure', () => {
  it.each([
    '```mermaid\nflowchart LR\nA --> B\n```',
    '~~~mermaid\nflowchart LR\nA --> B\n~~~',
    '> ```mermaid\n> flowchart LR\n> A --> B\n> ```',
    '1. Diagram\n\n    ```mermaid\n    flowchart LR\n    A --> B\n    ```',
    '````mermaid\nflowchart LR\nA --> B\n`````',
    '```mermaid\r\nflowchart LR\r\nA --> B\r\n```',
  ])('recognizes a complete Mermaid fence: %s', source => {
    expect(dom(source).querySelector('.mermaid')?.getAttribute('data-pending')).toBe('false');
  });

  it.each([
    '```mermaid\nflowchart LR\nA --> B',
    '> ```mermaid\n> flowchart LR\n> A --> B',
    '1. Diagram\n\n    ```mermaid\n    flowchart LR\n    A --> B',
    '````mermaid\nflowchart LR\nA --> B\n```',
    '```mermaid\nflowchart LR\nA --> B\n``` trailing',
    '```mermaid\nflowchart LR\nA --> B\n```\u00a0',
  ])('keeps an unclosed Mermaid fence pending: %s', source => {
    expect(dom(source).querySelector('.mermaid')?.getAttribute('data-pending')).toBe('true');
  });

  it('tracks both diagram types across ordinary fenced code and blockquotes', () => {
    const source = '```text\nmermaid\n```\n\n> ```lingzhi-diagram\n> {"type":"flowchart"}\n> ```\n\n```mermaid\nflowchart LR\nA --> B\n```';
    const box = dom(source);
    expect(box.querySelector('.teaching-diagram-host')?.getAttribute('data-pending')).toBe('false');
    expect(box.querySelector('.mermaid')?.getAttribute('data-pending')).toBe('false');
  });

  it('exposes safe language and action metadata for shared code controls', () => {
    const box = dom('```python\nprint(1)\n```');
    expect(box.querySelector('code')?.classList.contains('language-python')).toBe(true);
    expect(box.querySelector('[data-lang]')?.getAttribute('data-lang')).toBe('python');
    expect(box.querySelector('[data-code-actions]')).not.toBeNull();
    expect(box.querySelector('[data-markdown-action="copy"]')?.getAttribute('type')).toBe('button');
    const hostile = dom('```html"onclick="alert(1)\nexample\n```');
    expect(hostile.querySelector('[onclick],script')).toBeNull();
    expect(hostile.querySelector('code')?.getAttribute('class')).toBe('language-html"onclick="alert(1)');
  });
});
