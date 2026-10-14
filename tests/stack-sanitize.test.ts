import { describe, expect, it } from 'vitest'
import { fingerprintOf } from '../src/plugins/error'
import {
  byteLength,
  PROPS_TOTAL_MAX_BYTES,
  sanitizeProps,
  stripStackUrlQuery,
  truncate,
  truncateBytes
} from '../src/core/utils'

const isLoneSurrogate = (s: string) => /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/.test(s)

describe('堆栈清洗', () => {
  it('帧 URL 去掉 query / hash，保留 :行:列', () => {
    const stack = [
      'TypeError: boom',
      '    at a (https://cdn.x.com/app.js?token=SECRET&v=1:10:5)',
      '    at https://cdn.x.com/b.js#frag:3:7',
      '    at c (webpack://src/c.ts?abc:1:2)',
      '    at d (https://cdn.x.com/plain.js:4:4)'
    ].join('\n')
    const out = stripStackUrlQuery(stack)
    expect(out).not.toContain('SECRET')
    expect(out).toContain('(https://cdn.x.com/app.js:10:5)')
    expect(out).toContain('at https://cdn.x.com/b.js:3:7')
    expect(out).toContain('(webpack://src/c.ts:1:2)')
    expect(out).toContain('(https://cdn.x.com/plain.js:4:4)')
  })

  it('Firefox 形态（func@url:行:列）也去掉 query', () => {
    expect(stripStackUrlQuery('f@https://x.com/a.js?sig=1:2:3')).toBe('f@https://x.com/a.js:2:3')
  })

  it('同一错误不同 token：指纹一致', () => {
    const a = fingerprintOf('boom', 'Error\n    at f (https://x.com/a.js?t=1:1:1)')
    const b = fingerprintOf('boom', 'Error\n    at f (https://x.com/a.js?t=2:1:1)')
    expect(a).toBe(b)
  })

  it('截断不拆代理对', () => {
    const s = 'a' + '😀'.repeat(3) // a + 6 码元
    expect(truncate(s, 2)).toBe('a')
    expect(truncate(s, 3)).toBe('a😀')
    expect(isLoneSurrogate(truncate(s, 4))).toBe(false)
    expect(isLoneSurrogate(truncateBytes('😀😀', 5))).toBe(false)
    expect(truncateBytes('中文😀', 7)).toBe('中文')
  })

  it('4096 个中文的堆栈 + 其它属性超过 16KB：先缩 stack，其它键都保留', () => {
    const props: Record<string, unknown> = { stack: '错'.repeat(4096) }
    for (let i = 0; i < 6; i++) props[`k${i}`] = '值'.repeat(300)
    const out = sanitizeProps(props)
    expect(byteLength(JSON.stringify(out))).toBeLessThanOrEqual(PROPS_TOTAL_MAX_BYTES)
    for (let i = 0; i < 6; i++) expect((out[`k${i}`] as string).length).toBe(300)
    expect((out.stack as string).length).toBeGreaterThan(1000)
    expect((out.stack as string).length).toBeLessThan(4096)
  })

  it('未超总量时 stack 不缩', () => {
    const out = sanitizeProps({ stack: 's'.repeat(4096), message: 'm' })
    expect((out.stack as string).length).toBe(4096)
  })

  it('stack 截断点在 emoji 中间时不留孤立代理', () => {
    const out = sanitizeProps({ stack: 'a'.repeat(4095) + '😀😀' })
    expect(isLoneSurrogate(out.stack as string)).toBe(false)
    expect((out.stack as string).length).toBe(4095)
  })
})
