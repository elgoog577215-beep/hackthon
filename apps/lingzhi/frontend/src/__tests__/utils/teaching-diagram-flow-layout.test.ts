import { describe, expect, it } from 'vitest';
import { teachingDiagramLayoutSamples } from '../../../dev/teaching-diagram-layout-samples';
import { diagramTextLines, diagramTextWidth } from '../../utils/teaching-diagram-text';
import { parseTeachingDiagram, teachingDiagramSvg } from '../../utils/teaching-diagrams';

const draw = (sample: object) => new DOMParser().parseFromString(
  teachingDiagramSvg(parseTeachingDiagram(JSON.stringify(sample)), 'layout'), 'image/svg+xml');
type Bounds = { left: number; top: number; right: number; bottom: number };
const bounds = (rect: Element): Bounds => ({
  left: +rect.getAttribute('x')!, top: +rect.getAttribute('y')!,
  right: +rect.getAttribute('x')! + +rect.getAttribute('width')!,
  bottom: +rect.getAttribute('y')! + +rect.getAttribute('height')!,
});
const textBounds = (text: Element): Bounds[] => {
  let y = +text.getAttribute('y')!;
  return [...text.querySelectorAll('tspan')].map(span => {
    y += +span.getAttribute('dy')!;
    const width = diagramTextWidth(span.textContent!), x = +span.getAttribute('x')!;
    const left = text.getAttribute('text-anchor') === 'start' ? x : x - width / 2;
    return { left, right: left + width, top: y - 16, bottom: y + 5 };
  });
};
const overlaps = (a: Bounds, b: Bounds) =>
  a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;

describe('flowchart reading layout', () => {
  it.each(teachingDiagramLayoutSamples)('keeps $id compact with complete centred node text and clear edge labels', sample => {
    const doc = draw(sample), nodes = [...doc.querySelectorAll('[data-node-id]')];
    expect(+doc.documentElement.getAttribute('width')!).toBeLessThan(620);
    expect(+doc.documentElement.getAttribute('height')!).toBeLessThan(650);
    const nodeBounds = nodes.map(node => bounds(node.querySelector('rect')!));
    nodes.forEach((node, i) => {
      const b = nodeBounds[i]!, texts = [...node.querySelectorAll('text')].flatMap(textBounds);
      expect([...node.querySelectorAll('tspan')].map(span => span.textContent).join('')).toBe(sample.nodes[i]!.label);
      for (const t of texts) {
        expect(t.left).toBeGreaterThanOrEqual(b.left + 8);
        expect(t.right).toBeLessThanOrEqual(b.right - 8);
        expect(t.top).toBeGreaterThan(b.top);
        expect(t.bottom).toBeLessThan(b.bottom);
      }
      expect((texts[0]!.top + texts[texts.length - 1]!.bottom) / 2).toBeCloseTo((b.top + b.bottom) / 2);
    });
    for (const edge of doc.querySelectorAll('[data-from]')) {
      expect(edge.querySelector('rect')).toBeNull(); // No opaque patch cutting the connector.
      for (const t of [...edge.querySelectorAll('text')].flatMap(textBounds)) {
        expect(nodeBounds.some(b => overlaps(t, b))).toBe(false);
        expect(t.top).toBeGreaterThanOrEqual(0);
      }
    }
    const middle = nodeBounds[2]!;
    expect((middle.left + middle.right) / 2).toBeCloseTo((nodeBounds[0]!.left + nodeBounds[1]!.right) / 2);
    expect(doc.querySelector('[data-node-id="dark"] text')!.textContent).toContain('δ=(k+1/2)λ');
    expect(doc.querySelector('[data-node-id="dark"] text tspan')!.textContent).toContain('δ=(k+1/2)λ');
  });

  it('reserves space for long branch labels and unequal node heights', () => {
    const doc = draw({ ...teachingDiagramLayoutSamples[0], nodes: [
      { id: 'start', label: '开始' },
      { id: 'a', label: '第一条路径', detail: '保留完整条件\n保留完整来源\n不能省略' },
      { id: 'b', label: '第二条路径' },
    ], edges: [
      { from: 'start', to: 'a', label: '满足全部前置条件后继续这条路径' },
      { from: 'start', to: 'b', label: '否则先完成准备' },
    ] });
    const cards = [...doc.querySelectorAll('[data-node-id] > rect')].map(bounds);
    for (const text of doc.querySelectorAll('[data-from] text')) {
      for (const b of textBounds(text)) expect(cards.some(card => overlaps(card, b))).toBe(false);
    }
  });

  it('aligns parallel paths even when JSON lists the second row backwards', () => {
    const doc = draw({ ...teachingDiagramLayoutSamples[0], nodes: ['a', 'b', 'd', 'c'].map(id => ({ id, label: id })), edges: [
      { from: 'a', to: 'c' }, { from: 'b', to: 'd' },
    ] });
    const x = (id: string) => +doc.querySelector(`[data-node-id="${id}"] text`)!.getAttribute('x')!;
    expect(x('a')).toBe(x('c'));
    expect(x('b')).toBe(x('d'));
  });

  it('keeps the middle label clear of sibling branch and skipped-rank connectors', () => {
    const doc = draw({ ...teachingDiagramLayoutSamples[0], nodes: ['start', 'a', 'b', 'c', 'end'].map(id => ({ id, label: id })), edges: [
      { from: 'start', to: 'a', label: '第一种条件' }, { from: 'start', to: 'b', label: '第二种条件' }, { from: 'start', to: 'c', label: '第三种条件' },
      { from: 'a', to: 'end', label: '完成' }, { from: 'b', to: 'end', label: '完成' }, { from: 'c', to: 'end', label: '完成' },
      { from: 'start', to: 'end', label: '直接结束' },
    ] });
    const labels = [...doc.querySelectorAll('[data-from] text')].flatMap(textBounds);
    for (const path of doc.querySelectorAll('[data-from] path')) {
      let x = 0, y = 0;
      for (const command of path.getAttribute('d')!.match(/[MVH][^MVH]+/g)!) {
        const values = command.slice(1).trim().split(/\s+/).map(Number);
        const nx = command[0] === 'V' ? x : values[0]!;
        const ny = command[0] === 'H' ? y : command[0] === 'V' ? values[0]! : values[1]!;
        if (command[0] !== 'M') for (const label of labels) {
          expect(overlaps(label, { left: Math.min(x, nx) - 1, right: Math.max(x, nx) + 1, top: Math.min(y, ny) - 1, bottom: Math.max(y, ny) + 1 })).toBe(false);
        }
        x = nx; y = ny;
      }
    }
  });

  it('routes skipped ranks and repeats outside intervening cards', () => {
    const doc = draw({ ...teachingDiagramLayoutSamples[0], nodes: ['a', 'b', 'c'].map(id => ({ id, label: id })), edges: [
      { from: 'a', to: 'c', label: '跳过 / Skip' }, { from: 'a', to: 'b', label: '这是必须完整保留的长文字条件' }, { from: 'b', to: 'c' }, { from: 'c', to: 'a', label: '重试 / Repeat' },
    ] });
    const right = Math.max(...[...doc.querySelectorAll('[data-node-id] > rect')].map(rect => bounds(rect).right));
    const labelRight = Math.max(...textBounds(doc.querySelector('[data-from="a"][data-to="b"] text')!).map(b => b.right));
    for (const selector of ['[data-from="a"][data-to="c"]', '[data-from="c"][data-to="a"]']) {
      const edge = doc.querySelector(selector)!;
      expect(+edge.querySelector('text')!.getAttribute('x')!).toBeGreaterThan(right);
      expect(+edge.querySelector('text')!.getAttribute('x')! - 12).toBeGreaterThan(labelRight);
      expect(edge.querySelector('path')!.getAttribute('marker-end')).toContain('td-layout');
    }
  });

  it('wraps words and inline formulas together, with bounded long CJK tokens', () => {
    const formula = 'δ = (k + 1/2)λ';
    const text = `暗纹：${formula}`;
    expect(diagramTextLines(text, 180).some(line => line.includes(formula))).toBe(true);
    for (const value of ['中华人民共和国中华人民共和国', 'WWWWWWWWWWWWWWWWWWWWWW', 'Total optical path difference', text, '条件（满足），继续。']) {
      const lines = diagramTextLines(value, 180);
      expect(lines.join('')).toBe(value);
      expect(lines.every(line => diagramTextWidth(line) <= 180)).toBe(true);
    }
    expect(diagramTextLines('条件（满足），继续。', 64).every(line => !/^[，。）、]/.test(line))).toBe(true);
  });

  it('keeps a long self-loop label inside the downloadable SVG', () => {
    const label = '保留全部条件与说明，'.repeat(18);
    const doc = draw({ ...teachingDiagramLayoutSamples[0], nodes: [{ id: 'a', label: '检查' }], edges: [{ from: 'a', to: 'a', label }] });
    const w = +doc.documentElement.getAttribute('width')!, h = +doc.documentElement.getAttribute('height')!;
    const text = doc.querySelector('[data-from] text')!;
    expect(text.textContent).toBe(label);
    for (const b of textBounds(text)) {
      expect(b.left).toBeGreaterThanOrEqual(0);
      expect(b.top).toBeGreaterThanOrEqual(0);
      expect(b.right).toBeLessThanOrEqual(w);
      expect(b.bottom).toBeLessThanOrEqual(h);
    }
  });
});
