// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest'
import { isCredentialPath } from '../src/plugins/api-monitor'
import { looksLikeToken, maskSensitiveBody } from '../src/plugins/api-monitor/uploader'
import { errorPlugin } from '../src/plugins/error'
import { redactReplayUrls } from '../src/plugins/replay'
import { allEvents, createTestClient, destroyAllClients } from './helpers'

afterEach(() => destroyAllClients())

describe('F-4 凭证端点补全', () => {
  it.each([
    '/api/login',
    '/user/signin',
    '/sign-in',
    '/api/logout',
    '/oauth2/token',
    '/sso/callback',
    '/cas/serviceValidate',
    '/sms/sendCode',
    '/user/sendSmsCode',
    '/user/smsCode',
    '/getCaptcha',
    '/verifyCode',
    '/api/VerificationCode/check',
    '/sendOtp'
  ])('%s 判为凭证端点', (p) => {
    expect(isCredentialPath(p)).toBe(true)
  })

  it.each(['/api/order', '/user/profile', '/api/list', '/report/daily'])('%s 照常采集', (p) => {
    expect(isCredentialPath(p)).toBe(false)
  })
})

describe('F-2 JS 错误 filename 走 URL 脱敏', () => {
  it('filename 里的 token / sign 替换为 ***，其余保留', async () => {
    const t = createTestClient({ plugins: [errorPlugin()] })
    window.dispatchEvent(
      new window.ErrorEvent('error', {
        message: 'boom',
        error: new Error('boom'),
        filename: 'https://cdn.example.com/app.js?token=t1&sign=s1&v=3'
      })
    )
    await t.client.flush()
    const ev = allEvents(t.sent).find((e) => e.event === '$error')
    expect(ev?.props.filename).toBe('https://cdn.example.com/app.js?token=***&sign=***&v=3')
  })
})

describe('F-3 回放 DOM 的 URL 属性脱敏', () => {
  it('全量快照节点树里的 href / src / action 脱敏，其他属性不动', () => {
    const ev = {
      type: 2,
      data: {
        node: {
          type: 0,
          childNodes: [
            { type: 2, tagName: 'a', attributes: { href: '/cb?code=c1&page=2', title: 'code=x' }, childNodes: [] },
            {
              type: 2,
              tagName: 'div',
              attributes: {},
              childNodes: [
                { type: 2, tagName: 'img', attributes: { src: 'https://s.example.com/a.png?signature=s&w=1' }, childNodes: [] },
                { type: 2, tagName: 'form', attributes: { action: '/x?access_token=a' }, childNodes: [] }
              ]
            }
          ]
        }
      }
    }
    const out = redactReplayUrls(ev) as typeof ev
    const [a, div] = out.data.node.childNodes as any[]
    expect(a.attributes).toEqual({ href: '/cb?code=***&page=2', title: 'code=x' })
    expect(div.childNodes[0].attributes.src).toBe('https://s.example.com/a.png?signature=***&w=1')
    expect(div.childNodes[1].attributes.action).toBe('/x?access_token=***')
  })

  it('增量快照的新增节点与属性变更也脱敏；其他增量事件不动', () => {
    const ev = {
      type: 3,
      data: {
        source: 0,
        adds: [{ parentId: 1, node: { type: 2, tagName: 'iframe', attributes: { src: '/e?ticket=t' }, childNodes: [] } }],
        attributes: [{ id: 5, attributes: { href: '/p?token=t&id=1', class: 'x' } }],
        texts: [],
        removes: []
      }
    }
    const out = redactReplayUrls(ev) as any
    expect(out.data.adds[0].node.attributes.src).toBe('/e?ticket=***')
    expect(out.data.attributes[0].attributes).toEqual({ href: '/p?token=***&id=1', class: 'x' })
    const input = { type: 3, data: { source: 5, text: '/p?token=t' } }
    expect(redactReplayUrls(input)).toEqual({ type: 3, data: { source: 5, text: '/p?token=t' } })
  })
})

describe('响应体 code / ticket 值像令牌时也脱敏', () => {
  const jwt = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig'
  it('业务码保留：0、200、"E1001"、"OK"', () => {
    for (const code of [0, 200, 'E1001', 'OK', 'USER_NOT_FOUND']) {
      expect(JSON.parse(maskSensitiveBody(JSON.stringify({ code, ticket: 3 }), false))).toEqual({
        code,
        ticket: 3
      })
    }
  })
  it('长度 ≥16 或 JWT 形态替换为 ***', () => {
    const body = { code: 'SplxlOBeZQQYbYS6WxSbIA', data: { ticket: 'ST-1-abcdefghijk-cas' }, x: { code: jwt } }
    expect(JSON.parse(maskSensitiveBody(JSON.stringify(body), false))).toEqual({
      code: '***',
      data: { ticket: '***' },
      x: { code: '***' }
    })
  })
  it('looksLikeToken 边界', () => {
    expect(looksLikeToken('a'.repeat(15))).toBe(false)
    expect(looksLikeToken('a'.repeat(16))).toBe(true)
    expect(looksLikeToken('eyJa.eyJb.c')).toBe(true)
    expect(looksLikeToken(123456789012345678)).toBe(false)
  })
  it('只对 code / ticket 生效：sign、msg 的长字符串保留', () => {
    const body = { sign: 'x'.repeat(40), msg: 'y'.repeat(40) }
    expect(JSON.parse(maskSensitiveBody(JSON.stringify(body), false))).toEqual(body)
  })
})
