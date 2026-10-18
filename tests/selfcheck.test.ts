// @vitest-environment happy-dom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createTracker } from '../src/index'
import { errorPlugin } from '../src/plugins/error'
import { isIgnoredError } from '../src/core/errorFilter'
import { allEvents, createTestClient, destroyAllClients } from './helpers'
import type { TrackClient } from '../src/core/client'

afterEach(() => {
  destroyAllClients()
  vi.unstubAllGlobals()
})

const okPing = vi.fn(async () => ({ status: 200, enabled: true }))
const item = (r: Awaited<ReturnType<TrackClient['selfCheck']>>, id: string) =>
  r.items.find((i) => i.id === id)

describe('selfCheck', () => {
  it('健康配置：全部 ok，ping 只请求 /track/config?app_key=，不入队任何事件', async () => {
    const ping = vi.fn(async () => ({ status: 200, enabled: true }))
    const t = createTestClient({}, { ping })
    const r = await t.client.selfCheck()
    expect(r.status).toBe('ok')
    expect(r.items.every((i) => i.fix === '')).toBe(true)
    expect(ping).toHaveBeenCalledWith('https://t.example.com/track/config?app_key=test-app')
    expect(t.client.queueSize).toBe(0)
    await t.client.flush()
    expect(t.sent).toHaveLength(0)
    // 报告不含用户标识
    expect(JSON.stringify(r)).not.toContain(t.client.getDistinctId())
  })

  it('非法 endpoint → fail 且跳过 ping', async () => {
    const ping = vi.fn(okPing)
    const t = createTestClient({ endpoint: 'api.example.com' }, { ping })
    const r = await t.client.selfCheck()
    expect(r.status).toBe('fail')
    expect(item(r, 'config.endpoint')?.status).toBe('fail')
    expect(item(r, 'ping')?.status).toBe('fail')
    expect(ping).not.toHaveBeenCalled()
  })

  it('ping：网络失败 / 应用不存在 / 应用停用 / 无 ping', async () => {
    for (const [res, msg] of [
      [{ status: 0 }, '无法连接'],
      [{ status: 400 }, '应用不存在'],
      [{ status: 200, enabled: false }, '已停用']
    ] as const) {
      const t = createTestClient({}, { ping: async () => res })
      const r = await t.client.selfCheck()
      expect(item(r, 'ping')?.status).toBe('fail')
      expect(item(r, 'ping')?.message).toContain(msg)
      expect(item(r, 'ping')?.fix).not.toBe('')
    }
    const thrower = createTestClient({}, { ping: async () => Promise.reject(new Error('x')) })
    expect(item(await thrower.client.selfCheck(), 'ping')?.status).toBe('fail')
    const none = createTestClient()
    expect(item(await none.client.selfCheck(), 'ping')?.status).toBe('warn')
  })

  it('privacy：开启响应体采集但未显式开脱敏（默认）也提示，只 warn 不 fail', async () => {
    const t = createTestClient({ apiBodyEnabled: true }, { ping: okPing })
    const p = item(await t.client.selfCheck(), 'privacy')
    expect(p?.status).toBe('warn')
    expect(p?.message).toBe('响应体采集已开启，个人信息字段未脱敏（凭证类键始终脱敏）')
    const on = createTestClient(
      { apiBodyEnabled: true, apiBodyMaskEnabled: true },
      { ping: okPing }
    )
    expect(item(await on.client.selfCheck(), 'privacy')?.status).toBe('ok')
  })

  it('冲突配置、采样 0、DNT、optOut、回放未加载、隐私降级', async () => {
    const t = createTestClient(
      {
        batchSize: 200,
        apiMonitorEnabled: true,
        apiBodyEnabled: true,
        apiBodyMaskEnabled: false,
        replayEnabled: true,
        sampleRate: 0
      },
      { ping: okPing }
    )
    const r = await t.client.selfCheck()
    expect(item(r, 'config.conflict')?.message).toContain('batchSize')
    expect(item(r, 'config.conflict')?.message).toContain('api-monitor')
    expect(item(r, 'sampling')?.status).toBe('fail')
    expect(item(r, 'replay')?.status).toBe('warn')
    expect(item(r, 'privacy')?.status).toBe('warn')

    const dnt = createTestClient({}, { ping: okPing, isDnt: () => true })
    expect(item(await dnt.client.selfCheck(), 'consent')?.status).toBe('warn')
    const opt = createTestClient({}, { ping: okPing })
    opt.client.optOut()
    expect(item(await opt.client.selfCheck(), 'consent')?.message).toContain('optOut')
  })

  it('队列积压 ≥80% 告警', async () => {
    const t = createTestClient({ queueCapacity: 5, batchSize: 100 }, { ping: okPing })
    t.state.fail = true
    for (let i = 0; i < 5; i++) t.client.track('e')
    expect(item(await t.client.selfCheck(), 'queue')?.status).toBe('warn')
  })

  it('filters 项报告 beforeSend / ignoreErrors / skipHandledErrors', async () => {
    const a = createTestClient({}, { ping: okPing })
    // skipHandledErrors 默认 false：上报全部错误
    expect(item(await a.client.selfCheck(), 'filters')?.message).toBe('上报全部错误')
    const c = createTestClient({ skipHandledErrors: true }, { ping: okPing })
    expect(item(await c.client.selfCheck(), 'filters')?.message).toBe('跳过 HttpError/已处理错误')
    const b = createTestClient(
      { beforeSend: (e) => e, ignoreErrors: ['x', /y/], skipHandledErrors: false },
      { ping: okPing }
    )
    const m = item(await b.client.selfCheck(), 'filters')?.message
    expect(m).toContain('beforeSend')
    expect(m).toContain('ignoreErrors(2 条)')
    expect(m).toContain('上报全部错误')
  })

  it('未注入 runner（纯 core 用法）时 reject 并给出提示', async () => {
    const t = createTestClient({}, { selfCheck: undefined })
    await expect(t.client.selfCheck()).rejects.toThrow('deps.selfCheck')
  })
})

describe('beforeSend', () => {
  it('可改写 props、返回 null 丢弃、抛错默认丢弃；会话事件不经过钩子', async () => {
    const seen: string[] = []
    const t = createTestClient({
      beforeSend: (e) => {
        seen.push(e.event)
        if (e.event === 'drop_me') return null
        if (e.event === 'boom') throw new Error('hook bug')
        return { ...e, props: { ...e.props, url: 'redacted' } }
      }
    })
    expect(t.client.track('drop_me')).toBeNull()
    t.client.track('keep', { url: 'https://x/?token=1' })
    expect(t.client.track('boom', { email: 'a@b.c' })).toBeNull()
    t.client.identify('u1')
    await t.client.flush()
    const evs = allEvents(t.sent)
    expect(evs.map((e) => e.event)).toEqual(['$session_start', 'keep', '$identify'])
    expect(evs.find((e) => e.event === 'keep')?.props.url).toBe('redacted')
    expect(JSON.stringify(evs)).not.toContain('a@b.c')
    expect(seen).not.toContain('$session_start')
  })

  it("beforeSendOnError='keep'：抛错发送钩子处理前的原事件（钩子就地修改不生效）", async () => {
    const t = createTestClient({
      beforeSendOnError: 'keep',
      beforeSend: (e) => {
        e.props.touched = 1
        throw new Error('x')
      }
    })
    t.client.track('k', { a: 1 })
    await t.client.flush()
    const ev = allEvents(t.sent).find((e) => e.event === 'k')
    expect(ev?.props.a).toBe(1)
    expect(ev?.props.touched).toBeUndefined()
  })

  it('返回值只合并 props：event_id / distinct_id / event 改动被忽略，非法返回值视为不改', async () => {
    const t = createTestClient({
      beforeSend: (e) => {
        if (e.event === 'weird') return 42 as never
        if (e.event === 'badprops') return { ...e, props: 'x' as never }
        return {
          ...e,
          event: 'hijacked',
          event_id: 'fixed',
          distinct_id: 'other',
          props: { ok: 1 }
        }
      }
    })
    const id = t.client.track('a')
    t.client.track('weird', { w: 1 })
    t.client.track('badprops', { b: 1 })
    await t.client.flush()
    const evs = allEvents(t.sent).filter((e) => e.event !== '$session_start')
    expect(evs.map((e) => e.event)).toEqual(['a', 'weird', 'badprops'])
    expect(evs[0].event_id).toBe(id)
    expect(evs[0].distinct_id).toBe(t.client.getDistinctId())
    expect(evs[0].props).toEqual({ ok: 1 })
    expect(evs[1].props.w).toBe(1)
    expect(evs[2].props.b).toBe(1)
  })
})

describe('ignoreErrors / skipHandledErrors', () => {
  const base = { skipHandledErrors: true, ignoreErrors: undefined }
  it('skipHandledErrors=true 时跳过 HttpError / handled / expected', () => {
    expect(isIgnoredError(base, Object.assign(new Error('a'), { name: 'HttpError' }), 'a')).toBe(
      true
    )
    expect(isIgnoredError(base, { handled: true }, 'a')).toBe(true)
    expect(isIgnoredError(base, { expected: true }, 'a')).toBe(true)
    expect(isIgnoredError(base, new Error('a'), 'a')).toBe(false)
    expect(isIgnoredError({ ...base, skipHandledErrors: false }, { handled: true }, 'a')).toBe(
      false
    )
  })
  it('字符串子串 / RegExp / 谓词（谓词抛错不忽略）', () => {
    expect(isIgnoredError({ ...base, ignoreErrors: ['Script error'] }, null, 'Script error.')).toBe(
      true
    )
    expect(isIgnoredError({ ...base, ignoreErrors: [/^Abort/] }, null, 'AbortError')).toBe(true)
    expect(isIgnoredError({ ...base, ignoreErrors: [/^Abort/] }, null, 'x Abort')).toBe(false)
    expect(isIgnoredError({ ...base, ignoreErrors: (e) => e === 1 }, 1, '')).toBe(true)
    expect(
      isIgnoredError(
        {
          ...base,
          ignoreErrors: () => {
            throw new Error('x')
          }
        },
        1,
        ''
      )
    ).toBe(false)
  })
  it('默认（skipHandledErrors=false）：HttpError / expected 也上报', async () => {
    const t = createTestClient({ plugins: [errorPlugin()] })
    expect(t.client.options.skipHandledErrors).toBe(false)
    const e = new window.Event('unhandledrejection') as Event & { reason: unknown }
    e.reason = Object.assign(new Error('401'), { name: 'HttpError' })
    window.dispatchEvent(e)
    const e2 = new window.Event('unhandledrejection') as Event & { reason: unknown }
    e2.reason = Object.assign(new Error('biz'), { expected: true })
    window.dispatchEvent(e2)
    await t.client.flush()
    const msgs = allEvents(t.sent)
      .filter((x) => x.event === '$error')
      .map((x) => x.props.message)
    expect(msgs).toEqual(['401', 'biz'])
  })
  it('error 插件：unhandledrejection 与 window error 均过滤', async () => {
    const t = createTestClient({
      plugins: [errorPlugin()],
      ignoreErrors: ['noise'],
      skipHandledErrors: true
    })
    const rej = (reason: unknown) => {
      const e = new window.Event('unhandledrejection') as Event & { reason: unknown }
      e.reason = reason
      window.dispatchEvent(e)
    }
    rej(Object.assign(new Error('401'), { name: 'HttpError' }))
    rej(Object.assign(new Error('biz'), { expected: true }))
    rej(new Error('noise here'))
    rej(new Error('real rejection'))
    window.dispatchEvent(
      new window.ErrorEvent('error', { message: 'noise js', error: new Error('noise js') })
    )
    window.dispatchEvent(
      new window.ErrorEvent('error', { message: 'real js', error: new Error('real js') })
    )
    await t.client.flush()
    const msgs = allEvents(t.sent)
      .filter((e) => e.event === '$error')
      .map((e) => e.props.message)
    expect(msgs).toEqual(['real rejection', 'real js'])
  })
})

describe('trackApiError', () => {
  it('url 敏感 query 脱敏（token / access_token），业务参数保留', async () => {
    const t = createTestClient()
    t.client.trackApiError({
      url: 'https://api.x.com/o?id=7&token=abc&access_token=xyz&Authorization=q'
    })
    await t.client.flush()
    const url = String(allEvents(t.sent).find((e) => e.event === 'api_request')?.props.url)
    expect(url).not.toContain('abc')
    expect(url).not.toContain('xyz')
    expect(url).toContain('id=7')
    expect(url).toContain('***')
  })

  it('上报 api_request(success=false, source=manual)，带 biz_code 与截断 message', async () => {
    const t = createTestClient()
    const id = t.client.trackApiError({
      url: '/api/order',
      method: 'post',
      status: 200,
      bizCode: 40001,
      message: 'x'.repeat(600)
    })
    expect(id).toBeTruthy()
    await t.client.flush()
    const ev = allEvents(t.sent).find((e) => e.event === 'api_request')
    expect(ev?.props).toMatchObject({
      url: '/api/order',
      method: 'POST',
      status: 200,
      biz_code: '40001',
      success: false,
      source: 'manual'
    })
    expect(String(ev?.props.error_message).length).toBeLessThanOrEqual(515)
  })
})

describe('createTracker', () => {
  it.each(['https://t.example.com/', 'https://t.example.com//', ' https://t.example.com/ '])(
    'endpoint %j 末尾斜杠/空白：collect、config、selfCheck ping 都不出现 //track',
    async (endpoint) => {
      const urls: string[] = []
      vi.stubGlobal('CompressionStream', undefined)
      vi.stubGlobal('fetch', async (url: string) => {
        urls.push(url)
        return new Response(JSON.stringify({ code: 200, data: { enabled: true } }), { status: 200 })
      })
      const c = createTracker({ appKey: 'k1', endpoint, plugins: [] })
      c.track('x')
      await c.flush()
      await c.selfCheck()
      c.destroy()
      expect(urls).toContain('https://t.example.com/track/collect?app_key=k1')
      expect(urls).toContain('https://t.example.com/track/config?app_key=k1')
      expect(urls.every((u) => !u.includes('//track'))).toBe(true)
    }
  )

  it('collect URL 带 ?app_key=，selfCheck ping 走 fetch 且不带凭据', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = []
    vi.stubGlobal('CompressionStream', undefined)
    vi.stubGlobal('fetch', async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url.includes('/track/config'))
        return new Response(JSON.stringify({ code: 200, data: { enabled: true } }), { status: 200 })
      return new Response(null, { status: 204 })
    })
    const c = createTracker({
      appKey: 'k 1',
      endpoint: 'https://t.example.com/',
      fetchRemoteConfig: false,
      plugins: []
    })
    c.track('hello')
    await c.flush()
    expect(calls.some((x) => x.url === 'https://t.example.com/track/collect?app_key=k%201')).toBe(
      true
    )
    const r = await c.selfCheck()
    const ping = calls.find((x) => x.url.includes('/track/config'))
    expect(ping?.init?.credentials).toBe('omit')
    expect(r.items.find((i) => i.id === 'ping')?.status).toBe('ok')
    expect(r.items.find((i) => i.id === 'config.appKey')?.status).toBe('warn')
    c.destroy()
  })
})
