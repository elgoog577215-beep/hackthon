// Conservative 16px system-font metrics keep SVG generation deterministic in
// downloads and tests as well as in the browser. CJK and mathematical symbols
// must not fall back to the old eight-pixel long-token estimate.
export const diagramTextWidth = (value: string): number =>
  [...value].reduce((sum, char) => sum + (
    /[\u2e80-\u9fff\uac00-\ud7af\uf900-\ufaff\u3000-\u303f\uff00-\uffef]/u.test(char) ? 16
      : /[MW@%]/.test(char) ? 15
        : /[A-Z]/.test(char) ? 11
          : /[ilI.,'` :;!|]/.test(char) ? 5
            : /[\u0370-\u03ff]/u.test(char) ? 12
              : /[^\x00-\xff]/u.test(char) ? 16 : 9
  ), 0);

const Segmenter = Reflect.get(Intl, 'Segmenter');
const segmenter: { segment(value: string): Iterable<{ segment: string }> } | undefined =
  Segmenter ? new Segmenter('zh', { granularity: 'word' }) : undefined;

export function diagramTextTokens(value: string): string[] {
  // Keep a short inline expression (e.g. δ = (k + 1/2)λ) together. Ordinary
  // English still wraps at words, and Chinese uses word boundaries when available.
  const chunks = value.match(/[A-Za-z0-9\u0370-\u03ff][A-Za-z0-9\u0370-\u03ff\u2080-\u209f=+*/^()\[\]{}.,…≠≤≥≈←→· \t-]*|[^A-Za-z0-9\u0370-\u03ff]+/gu) || [];
  const words = chunks.flatMap(chunk =>
    /[=+*/^≠≤≥≈←→]|[\u0370-\u03ff]/u.test(chunk)
      ? [chunk]
      : segmenter ? [...segmenter.segment(chunk)].map(word => word.segment)
        : chunk.match(/[A-Za-z0-9_]+|\s+|./gu) || []);
  const tokens: string[] = [];
  for (let i = 0; i < words.length; i++) {
    const word = words[i]!;
    if (/^[，。、；：！？,.!?;:)\]}）】]+$/u.test(word) && tokens.length) tokens[tokens.length - 1] += word;
    else if (/^[(\[{（【]+$/u.test(word) && i + 1 < words.length) words[i + 1] = word + words[i + 1];
    else tokens.push(word);
  }
  return tokens;
}

export function diagramTextLines(value: string, width = 200): string[] {
  const result: string[] = [];
  for (const paragraph of value.split('\n')) {
    let line = '', used = 0;
    for (const token of diagramTextTokens(paragraph)) {
      const size = diagramTextWidth(token);
      if (used + size > width && line) { result.push(line); line = ''; used = 0; }
      if (size > width) {
        for (const char of token) {
          const charWidth = diagramTextWidth(char);
          if (used + charWidth > width && line) {
            const chars = [...line];
            let split = chars.length;
            if (/^[，。、；：！？,.!?;:)\]}）】]$/u.test(char)) {
              split--;
              while (split > 0 && /^[，。、；：！？,.!?;:)\]}）】]$/u.test(chars[split]!)) split--;
            }
            while (split > 0 && /^[(\[{（【]$/u.test(chars[split - 1]!)) split--;
            const tail = chars.slice(split).join('');
            if (split > 0 && diagramTextWidth(tail + char) <= width) {
              result.push(chars.slice(0, split).join('')); line = tail; used = diagramTextWidth(tail);
            } else { result.push(line); line = ''; used = 0; }
          }
          line += char; used += charWidth;
        }
      } else { line += token; used += size; }
    }
    result.push(line);
  }
  return result;
}
