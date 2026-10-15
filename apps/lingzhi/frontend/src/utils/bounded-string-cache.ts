/** LRU for rendered strings, bounded by both entries and retained UTF-16 chars.
 * Keys count towards the budget too: growing source documents can otherwise
 * retain more memory than their cached result. Object overhead is not included.
 */
export class BoundedStringCache {
  private readonly entries = new Map<string, string>();
  private retainedChars = 0;

  constructor(readonly maxEntries: number, readonly maxChars: number) {}

  get size(): number { return this.entries.size; }
  get totalChars(): number { return this.retainedChars; }

  get(key: string): string | undefined {
    const value = this.entries.get(key);
    if (value === undefined) return undefined;
    this.entries.delete(key);
    this.entries.set(key, value);
    return value;
  }

  set(key: string, value: string): void {
    this.delete(key);
    const chars = key.length + value.length;
    // An oversized result is still returned by the renderer, but not retained.
    if (chars > this.maxChars || this.maxEntries < 1) return;
    while (this.entries.size >= this.maxEntries || this.retainedChars + chars > this.maxChars) {
      const oldest = this.entries.keys().next().value;
      if (oldest === undefined) break;
      this.delete(oldest);
    }
    this.entries.set(key, value);
    this.retainedChars += chars;
  }

  private delete(key: string): void {
    const previous = this.entries.get(key);
    if (previous === undefined) return;
    this.retainedChars -= key.length + previous.length;
    this.entries.delete(key);
  }
}
