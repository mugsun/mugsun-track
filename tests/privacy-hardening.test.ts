// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest'
import { browserContextProvider, browserIsGpc } from '../src/adapters'
import { redactSensitiveUrl, SENSITIVE_KEYS, URL_ONLY_SENSITIVE_KEYS } from '../src/core/utils'
import { apiMonitorPlugin } from '../src/plugins/api-monitor'
import type { ApiBodyPayload, ApiBodySendOutcome } from '../src/plugins/api-monitor/uploader'
import { autocapturePlugin } from '../src/plugins/autocapture'
import { errorPlugin } from '../src/plugins/error'
import { allEvents, createTestClient, destroyAllClients } from './helpers'

afterEach(() => destroyAllClients())

const settle = async (rounds = 20) => {
  for (let i = 0; i < rounds; i++) await Promise.resolve()
}

describe('URL 敏感参数：新增键、hash、键名归一', () => {
  it('code / sign / signature / ticket / session / otp 替换为 ***，业务参数保留', () => {
    const out = redactSensitiveUrl(
      'https://a.example.com/cb?code=c1&sign=s1&signature=s2&ticket=t1&session=x1&otp=123456&page=2'
    )
    for (const k of ['code', 'sign', 'signature', 'ticket', 'session', 'otp']) {
      expect(out).toContain(`${k}=***`)
    }
    expect(out).toContain('page=2')
    expect(out).not.toMatch(/c1|s1|s2|t1|x1|123456/)
  })

  it('hash 参数：OAuth 隐式流 #access_token= 与 hash 路由 #/cb?code=', () => {
    expect(redactSensitiveUrl('https://a.example.com/#access_token=t1&state=ok')).toBe(
      'https://a.example.com/#access_token=***&state=ok'
    )
    expect(redactSensitiveUrl('https://a.example.com/#/cb?code=c1&tab=2')).toBe(
      'https://a.example.com/#/cb?code=***&tab=2'
    )
    // 普通 hash 不动
    expect(redactSensitiveUrl('https://a.example.com/#/orders')).toBe(
      'https://a.example.com/#/orders'
    )
  })

  it('键名忽略大小写与 _ -：accessToken、Access-Token', () => {
    const out = redactSensitiveUrl('/x?accessToken=a1&Access-Token=a2&q=1')
    expect(out).not.toMatch(/a1|a2/)
    expect(out).toContain('q=1')
  })

  it('无敏感参数时原样返回（相对 URL 保持相对）', () => {
    expect(redactSensitiveUrl('/orders?id=1')).toBe('/orders?id=1')
  })
})

describe('凭证端点：注册、找回/修改密码、OTP/短信/验证码/MFA 的响应体不采集', () => {
  it('默认配置：这些路径标 body_skipped=credential，普通路径照常上传', async () => {
    const calls: ApiBodyPayload[] = []
    const send = async (p: ApiBodyPayload): Promise<ApiBodySendOutcome> => {
      calls.push(p)
      return 'ok'
    }
    window.fetch = (async () =>
      new Response('{"code":"123456"}', {
        status: 200,
        headers: { 'content-type': 'application/json' }
      })) as typeof fetch
    const t = createTestClient({
      apiMonitorEnabled: true,
      apiBodyEnabled: true,
      plugins: [apiMonitorPlugin({ send, gzip: null })]
    })
    const paths = [
      '/api/user/register',
      '/api/signup',
      '/api/Password/Reset',
      '/api/forgot',
      '/api/user/change-password',
      '/api/otp/send',
      '/api/sms/code',
      '/api/captcha',
      '/api/mfa/verify',
      '/api/2fa',
      '/api/totp/bind',
      '/api/verify-code'
    ]
    for (const p of paths) await window.fetch(`https://api.example.com${p}`, { method: 'POST' })
    await window.fetch('https://api.example.com/api/orders')
    await settle()
    await t.client.flush()
    const evs = allEvents(t.sent).filter((e) => e.event === 'api_request')
    expect(evs).toHaveLength(paths.length + 1)
    expect(evs.slice(0, paths.length).every((e) => e.props.body_skipped === 'credential')).toBe(
      true
    )
    expect(evs[paths.length].props.body_ref).toBeDefined()
    expect(calls).toHaveLength(1)
  })
})

describe('Global Privacy Control', () => {
  it('respectGpc 默认 false：未设置时 GPC 开启也照常采集', async () => {
    const t = createTestClient({}, { isGpc: () => true })
    expect(t.client.options.respectGpc).toBe(false)
    t.client.track('default_event')
    await t.client.flush()
    expect(allEvents(t.sent).map((e) => e.event)).toContain('default_event')
  })

  it('respectGpc=true：GPC 开启时不采集，selfCheck consent 提示', async () => {
    const t = createTestClient({ respectGpc: true }, { isGpc: () => true })
    expect(t.client.options.respectGpc).toBe(true)
    t.client.track('gpc_event')
    await t.client.flush()
    expect(t.sent).toHaveLength(0)
    const c = (await t.client.selfCheck()).items.find((i) => i.id === 'consent')
    expect(c?.status).toBe('warn')
    expect(c?.message).toContain('Global Privacy Control')
  })

  it('显式 respectGpc=false 时忽略 GPC', async () => {
    const t = createTestClient({ respectGpc: false }, { isGpc: () => true })
    t.client.track('ok_event')
    await t.client.flush()
    expect(allEvents(t.sent).map((e) => e.event)).toContain('ok_event')
  })

  it('browserIsGpc 只认 navigator.globalPrivacyControl === true', () => {
    const nav = navigator as Navigator & { globalPrivacyControl?: unknown }
    const prev = Object.getOwnPropertyDescriptor(nav, 'globalPrivacyControl')
    Object.defineProperty(nav, 'globalPrivacyControl', { value: true, configurable: true })
    expect(browserIsGpc()).toBe(true)
    Object.defineProperty(nav, 'globalPrivacyControl', { value: '1', configurable: true })
    expect(browserIsGpc()).toBe(false)
    if (prev) Object.defineProperty(nav, 'globalPrivacyControl', prev)
    else delete (nav as { globalPrivacyControl?: unknown }).globalPrivacyControl
  })
})

describe('页面 URL / referrer / 链接 / 资源地址脱敏', () => {
  it('公共属性 referrer 经 redactSensitiveUrl；url_path 只有 pathname（不含 query/hash）', () => {
    const prev = Object.getOwnPropertyDescriptor(Document.prototype, 'referrer')
    Object.defineProperty(document, 'referrer', {
      value: 'https://sso.example.com/cb?ticket=ST-1&code=c1&from=home',
      configurable: true
    })
    const ctx = browserContextProvider()()
    expect(ctx.referrer).toBe('https://sso.example.com/cb?ticket=***&code=***&from=home')
    expect(String(ctx.url_path)).not.toContain('?')
    delete (document as { referrer?: unknown }).referrer
    if (prev) expect(document.referrer).toBeDefined()
  })

  it('$session_start 与普通事件共用公共属性：referrer 已脱敏', async () => {
    const t = createTestClient(
      {},
      {},
      { referrer: redactSensitiveUrl('https://x.example.com/?token=t1') }
    )
    t.client.track('e')
    await t.client.flush()
    const start = allEvents(t.sent).find((e) => e.event === '$session_start')
    expect(start?.props.referrer).toBe('https://x.example.com/?token=***')
  })

  it('自动采集的链接 href 脱敏', async () => {
    const t = createTestClient({ plugins: [autocapturePlugin()] })
    const a = document.createElement('a')
    a.href = '/cb?code=c1&tab=2'
    a.textContent = 'link'
    document.body.appendChild(a)
    a.click()
    await t.client.flush()
    const ev = allEvents(t.sent).find((e) => e.props.href !== undefined)
    expect(ev?.props.href).toBe('/cb?code=***&tab=2')
    a.remove()
  })

  it('资源加载错误的 resource_url 脱敏', async () => {
    const t = createTestClient({ plugins: [errorPlugin()] })
    const img = document.createElement('img')
    img.src = 'https://cdn.example.com/a.png?signature=s1&v=2'
    document.body.appendChild(img)
    img.dispatchEvent(new window.Event('error'))
    await t.client.flush()
    const ev = allEvents(t.sent).find((e) => e.event === '$error')
    expect(ev?.props.resource_url).toBe('https://cdn.example.com/a.png?signature=***&v=2')
    img.remove()
  })
})

describe('凭证键共用一份清单，code / sign 等只在 URL 里脱敏', () => {
  it('业务响应 {code,msg,data:{sign,ticket}} 原样保留；session 属凭证键，响应体里也替换', async () => {
    const { maskSensitiveBody } = await import('../src/plugins/api-monitor/uploader')
    const body = { code: 0, msg: 'ok', data: { sign: true, ticket: 1 } }
    expect(JSON.parse(maskSensitiveBody(JSON.stringify(body), false))).toEqual(body)
    expect(
      JSON.parse(maskSensitiveBody(JSON.stringify({ code: 0, data: { session: 'x' } }), false))
    ).toEqual({ code: 0, data: { session: '***' } })
    expect(
      JSON.parse(maskSensitiveBody(JSON.stringify({ signature: 's', otp: '1' }), false))
    ).toEqual({
      signature: 's',
      otp: '1'
    })
  })

  it('URL 里 ?code=、#code= 与 referrer 里的 ?sign= 都替换', () => {
    expect(redactSensitiveUrl('https://a.example.com/cb?code=abc&state=1')).toBe(
      'https://a.example.com/cb?code=***&state=1'
    )
    expect(redactSensitiveUrl('https://a.example.com/#code=abc&state=1')).toBe(
      'https://a.example.com/#code=***&state=1'
    )
    for (const k of URL_ONLY_SENSITIVE_KEYS)
      expect(redactSensitiveUrl(`/x?${k}=v`)).toBe(`/x?${k}=***`)
  })

  it('referrer 带 ?sign= 时替换', () => {
    Object.defineProperty(document, 'referrer', {
      value: 'https://shop.example.com/pay?sign=abc&id=1',
      configurable: true
    })
    try {
      const ctx = browserContextProvider()()
      expect(String(ctx.referrer)).toBe('https://shop.example.com/pay?sign=***&id=1')
    } finally {
      delete (document as unknown as Record<string, unknown>).referrer
    }
  })

  it('凭证键在 URL 和响应体里都替换', async () => {
    const { maskSensitiveBody } = await import('../src/plugins/api-monitor/uploader')
    for (const k of SENSITIVE_KEYS) {
      expect(redactSensitiveUrl(`/x?${k}=v`)).toBe(`/x?${k}=***`)
      expect(JSON.parse(maskSensitiveBody(JSON.stringify({ [k]: 'v' }), false))).toEqual({
        [k]: '***'
      })
    }
    const out = JSON.parse(
      maskSensitiveBody(
        JSON.stringify({
          client_secret: 'c',
          sessionId: 's',
          'X-Api-Key': 'k',
          jwt: 'j',
          accessKey: 'a'
        }),
        false
      )
    ) as Record<string, unknown>
    for (const v of Object.values(out)) expect(v).toBe('***')
  })

  it('归一后精确匹配，不做子串匹配：codeType / errCode / signedAt / ticketCount / sessionTimeout 保留', () => {
    expect(
      redactSensitiveUrl('/x?codeType=1&errCode=500&signedAt=t&ticketCount=3&sessionTimeout=30')
    ).toBe('/x?codeType=1&errCode=500&signedAt=t&ticketCount=3&sessionTimeout=30')
  })
})

describe('maskSensitiveBody 解析失败不返回原文（P4）', () => {
  it('非法 JSON 整体返回 ***', async () => {
    const { maskSensitiveBody } = await import('../src/plugins/api-monitor/uploader')
    expect(maskSensitiveBody('{"token":"leak-me", oops')).toBe('***')
    expect(maskSensitiveBody('token=leak-me', false)).toBe('***')
  })
})
