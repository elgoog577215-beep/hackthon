import { describe, expect, it } from 'vitest';
import { BoundedStringCache } from '@/utils/bounded-string-cache';

describe('BoundedStringCache', () => {
  it('evicts by total source and result characters before reaching the entry limit', () => {
    const cache = new BoundedStringCache(500, 12);
    cache.set('ab', '1234');
    cache.set('cd', '5678');
    expect(cache.totalChars).toBe(12);
    cache.get('ab');
    cache.set('ef', '90');
    expect(cache.get('cd')).toBeUndefined();
    expect(cache.get('ab')).toBe('1234');
    expect(cache.totalChars).toBe(10);
  });

  it('evicts least recently used entries with no off-by-one overflow', () => {
    const cache = new BoundedStringCache(2, 100);
    cache.set('a', '1');
    cache.set('b', '2');
    cache.get('a');
    cache.set('c', '3');
    expect(cache.size).toBe(2);
    expect(cache.get('b')).toBeUndefined();
    expect(cache.get('a')).toBe('1');
  });

  it('accounts for replacement and refuses a single oversized result', () => {
    const cache = new BoundedStringCache(5, 10);
    cache.set('a', '123');
    cache.set('b', '45');
    cache.set('a', '6');
    expect(cache.totalChars).toBe(5);
    cache.set('a', 'x'.repeat(10));
    expect(cache.totalChars).toBe(3);
    expect(cache.get('a')).toBeUndefined();
    expect(cache.get('b')).toBe('45');
  });

  it('bounds 500 growing documents including UTF-16 source strings', () => {
    const cache = new BoundedStringCache(32, 2_000);
    for (let index = 0; index < 500; index++) {
      cache.set(`正文${index}😀`, '结果'.repeat(index));
      expect(cache.size).toBeLessThanOrEqual(32);
      expect(cache.totalChars).toBeLessThanOrEqual(2_000);
    }
    expect(cache.get('正文499😀')).toBe('结果'.repeat(499));
  });

  it('supports empty keys and cached empty strings', () => {
    const cache = new BoundedStringCache(1, 10);
    cache.set('', '');
    expect(cache.get('')).toBe('');
    cache.set('a', 'b');
    expect(cache.get('')).toBeUndefined();
    expect(cache.size).toBe(1);
  });
});
