// @vitest-environment happy-dom
import { afterEach, describe, expect, it } from 'vitest'
import { isCredentialPath } from '../src/plugins/api-monitor'
import { looksLikeToken, maskSensitiveBody } from '../src/plugins/api-monitor/uploader'
import { redactSensitiveUrl } from '../src/core/utils'
import { errorPlugin } from '../src/plugins/error'
import { redactReplayUrls, redactSrcset } from '../src/plugins/replay'
import { allEvents, createTestClient, destroyAllClients } from './helpers'

afterEach(() => destroyAllClients())

describe('F-4 凭证端点补全', () => {
  it.each([
    '/auth/login',
    '/oauth/token',
    '/sso/callback',
    '/cas/login',
    '/api/sms/send',
    '/captcha/image',
    '/user/verifycode',
    '/api/login',
    '/user/signin',
    '/sign-in',
    '/api/logout',
    '/api/LOGIN/',
    '/sms/sendCode',
    '/send-otp',
    '/v1/otp_verify',
    '/getCaptcha',
    '/api/VerificationCode/check',
    '/user/sendcode',
    '/user/getCode',
    '/api/checkcode/x'
  ])('%s 判为凭证端点', (p) => {
    expect(isCredentialPath(p)).toBe(true)
  })

  it.each([
    '/monitor/loginLog/list',
    '/system/logininfor/list',
    '/api/cashier/pay',
    '/case/list',
    '/cascade/tree',
    '/tokens/stats',
    '/footprint/list',
    '/smsTemplate/list',
    '/barcode/getcodeList',
    '/api/order',
    '/user/profile'
  ])('%s 照常采集', (p) => {
    expect(isCredentialPath(p)).toBe(false)
  })
})

describe('云存储预签名参数', () => {
  it('X-Amz-Signature / X-Amz-Security-Token / X-Goog-Signature 在 URL 与响应体里都替换', () => {
    expect(
      redactSensitiveUrl('https://b.s3.amazonaws.com/k?X-Amz-Signature=s&X-Amz-Security-Token=t&X-Amz-Date=d')
    ).toBe('https://b.s3.amazonaws.com/k?X-Amz-Signature=***&X-Amz-Security-Token=***&X-Amz-Date=d')
    expect(redactSensitiveUrl('https://storage.googleapis.com/b/o?X-Goog-Signature=g&x=1')).toBe(
      'https://storage.googleapis.com/b/o?X-Goog-Signature=***&x=1'
    )
    expect(JSON.parse(maskSensitiveBody(JSON.stringify({ xAmzSignature: 's', x_goog_signature: 'g' }), false))).toEqual({
      xAmzSignature: '***',
      x_goog_signature: '***'
    })
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

  it('srcset / imagesrcset 逐个候选脱敏并保留描述符；data: 不拆', () => {
    const ev = {
      type: 2,
      data: {
        node: {
          type: 2,
          tagName: 'div',
          attributes: {},
          childNodes: [
            { type: 2, tagName: 'img', attributes: { srcset: '/a.png?token=t 1x, /b.png?sign=s&w=2 2x' } },
            { type: 2, tagName: 'link', attributes: { imagesrcset: 'https://c.example.com/a.jpg?X-Amz-Signature=z 480w,/d.jpg 800w' } },
            { type: 2, tagName: 'img', attributes: { srcset: 'data:image/png;base64,AAA 1x' } }
          ]
        }
      }
    }
    const kids = (redactReplayUrls(ev) as any).data.node.childNodes
    expect(kids[0].attributes.srcset).toBe('/a.png?token=*** 1x, /b.png?sign=***&w=2 2x')
    expect(kids[1].attributes.imagesrcset).toBe('https://c.example.com/a.jpg?X-Amz-Signature=*** 480w,/d.jpg 800w')
    expect(kids[2].attributes.srcset).toBe('data:image/png;base64,AAA 1x')
  })

  it('video[poster]、object[data]、大写 HREF、xlink:href 都脱敏', () => {
    const ev = {
      type: 2,
      data: {
        node: {
          type: 0,
          childNodes: [
            { type: 2, tagName: 'video', attributes: { poster: '/p.jpg?token=t' } },
            { type: 2, tagName: 'object', attributes: { data: '/f.pdf?ticket=t&v=1' } },
            { type: 2, tagName: 'a', attributes: { HREF: '/x?access_token=a' } },
            { type: 2, tagName: 'use', attributes: { 'xlink:href': '/s.svg?sign=s#i' } }
          ]
        }
      }
    }
    const kids = (redactReplayUrls(ev) as any).data.node.childNodes
    expect(kids[0].attributes.poster).toBe('/p.jpg?token=***')
    expect(kids[1].attributes.data).toBe('/f.pdf?ticket=***&v=1')
    expect(kids[2].attributes.HREF).toBe('/x?access_token=***')
    expect(kids[3].attributes['xlink:href']).toBe('/s.svg?sign=***#i')
  })

  it('任意深度的节点都处理（显式栈，不递归）', () => {
    const root: any = { type: 2, tagName: 'div', attributes: {}, childNodes: [] }
    let cur = root
    for (let i = 0; i < 5000; i++) {
      const n = { type: 2, tagName: 'div', attributes: {}, childNodes: [] as any[] }
      cur.childNodes.push(n)
      cur = n
    }
    cur.childNodes.push({ type: 2, tagName: 'a', attributes: { href: '/deep?token=t' } })
    redactReplayUrls({ type: 2, data: { node: root } })
    expect(cur.childNodes[0].attributes.href).toBe('/deep?token=***')
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
  it('含 _ 的业务码、纯字母、纯数字保留', () => {
    for (const code of ['INVALID_PARAMETER_VALUE', 'ORDER_20261021_0001', 'ABCDEFGHIJKLMNOPQR', '12345678901234567890']) {
      expect(JSON.parse(maskSensitiveBody(JSON.stringify({ code }), false))).toEqual({ code })
    }
  })
  it('looksLikeToken 边界', () => {
    expect(looksLikeToken('a'.repeat(15))).toBe(false)
    expect(looksLikeToken('a'.repeat(16))).toBe(false)
    expect(looksLikeToken('a1'.repeat(8))).toBe(true)
    expect(looksLikeToken('a1'.repeat(7) + 'a')).toBe(false)
    expect(looksLikeToken('eyJa.eyJb.c')).toBe(true)
    expect(looksLikeToken(123456789012345678)).toBe(false)
  })
  it('只对 code / ticket 生效：sign、msg 的长字符串保留', () => {
    const body = { sign: 'x'.repeat(40), msg: 'y'.repeat(40) }
    expect(JSON.parse(maskSensitiveBody(JSON.stringify(body), false))).toEqual(body)
  })
})

describe('安全复核 9b93dda：P2 / P3', () => {
  it('P2 像令牌：base64url（含 _ -）与 hex 令牌替换，大写下划线业务码保留', () => {
    const b64 = 'Ab3_dE-9fGh1_jKl-2mNoPq3rStU_vW4xYz-5aBcDeF' // 43 字符
    expect(b64.length).toBe(43)
    const hex = '9f86d081884c7d659a2feaa0c55ad015a3bf4f1b'
    for (const v of [b64, hex, 'a1b2c3d4e5f60718']) expect(looksLikeToken(v)).toBe(true)
    for (const v of ['INVALID_PARAMETER_VALUE', 'ORDER_20261021_0001', 'E1001', 'USER_NOT_FOUND']) {
      expect(looksLikeToken(v)).toBe(false)
    }
    // 已知漏判（P4）：纯数字 / 纯字母
    expect(looksLikeToken('12345678901234567890')).toBe(false)
    expect(looksLikeToken('abcdefghijklmnopqrst')).toBe(false)
    expect(JSON.parse(maskSensitiveBody(JSON.stringify({ code: b64, ticket: hex }), false))).toEqual({
      code: '***',
      ticket: '***'
    })
  })

  it.each(['/api/v1/login.json', '/login.do', '/login.action', '/login;jsessionid=x', '/oauth/token.json'])(
    'P3-a 段右边界放宽：%s 命中',
    (p) => expect(isCredentialPath(p)).toBe(true)
  )
  it.each(['/tokens/stats', '/loginLog.json', '/cascade.do'])('P3-a %s 仍不命中', (p) =>
    expect(isCredentialPath(p)).toBe(false)
  )

  it.each(['/sendSms', '/getSmsCode', '/sendOtp', '/user/resendOtp', '/validateMobileCode', '/checkPhoneCode'])(
    'P3-b 动词组合：%s 命中',
    (p) => expect(isCredentialPath(p)).toBe(true)
  )
  it.each(['/smsTemplate/list', '/footprint/list', '/messageTemplate/send'])('P3-b %s 不命中', (p) =>
    expect(isCredentialPath(p)).toBe(false)
  )

  it('P3-c srcset：data: 候选单独跳过，同属性里的签名 URL 照常替换', () => {
    expect(redactSrcset('data:image/gif;base64,R0lGOD,lh 1x, https://c.example.com/a.jpg?token=t 2x')).toBe(
      'data:image/gif;base64,R0lGOD,lh 1x, https://c.example.com/a.jpg?token=*** 2x'
    )
  })
  it('P3-c srcset：URL 查询里带逗号不会被拆开', () => {
    const out = redactSrcset('/img?size=1,2&sign=s 1x,/b.jpg 2x')
    expect(out.endsWith(' 1x,/b.jpg 2x')).toBe(true)
    expect(out).toContain('sign=***')
    expect(out).not.toContain('sign=s ')
    expect(new URLSearchParams(out.split('?')[1].split(' ')[0]).get('size')).toBe('1,2')
  })
  it('P3-c srcset：URL 末尾的逗号作分隔；中间无空白的逗号按规范属于 URL', () => {
    expect(redactSrcset('/a.jpg?token=t, /b.jpg?token=u 2x')).toBe('/a.jpg?token=***, /b.jpg?token=*** 2x')
    expect(redactSrcset('/a.jpg?token=t,, /b.jpg 2x')).toBe('/a.jpg?token=***,, /b.jpg 2x')
    // 规范里整段 `/a.jpg?token=t,/b.jpg?token=u` 是一个 URL：token 值整体替换，不会漏出
    expect(redactSrcset('/a.jpg?token=t,/b.jpg?token=u 2x')).toBe('/a.jpg?token=*** 2x')
  })

  it('P3-d 云存储签名参数（URL 专用）：Azure sig、COS q-signature、OSS x-oss-signature / x-oss-security-token', () => {
    expect(redactSensitiveUrl('https://a.blob.core.windows.net/c/b?sv=2024&sig=abc&se=x')).toBe(
      'https://a.blob.core.windows.net/c/b?sv=2024&sig=***&se=x'
    )
    expect(redactSensitiveUrl('https://b.cos.ap-shanghai.myqcloud.com/k?q-sign-algorithm=sha1&q-signature=abc')).toBe(
      'https://b.cos.ap-shanghai.myqcloud.com/k?q-sign-algorithm=sha1&q-signature=***'
    )
    expect(
      redactSensitiveUrl('https://b.oss-cn-hangzhou.aliyuncs.com/k?x-oss-signature=s&x-oss-security-token=t&x-oss-expires=1')
    ).toBe('https://b.oss-cn-hangzhou.aliyuncs.com/k?x-oss-signature=***&x-oss-security-token=***&x-oss-expires=1')
    // URL 专用：响应体里的 sig 保留
    expect(JSON.parse(maskSensitiveBody(JSON.stringify({ sig: 'abc' }), false))).toEqual({ sig: 'abc' })
  })
})

describe('安全复核 8aac4b8：N-1 ~ N-3、srcset 逗号', () => {
  it('N-1 含 / 和 . 的令牌也替换；大写下划线业务码保留', () => {
    const google = '4/0AbCdEfGhIjKlMnOpQrStUvWxYz0123456789-_aBcD'
    const dotted = 'ya29.a0AfB_byC1d2E3f4G5h6I7j8K9'
    const b64 = 'QWxhZGRpbjpvcGVuIHNlc2FtZQ+/abc12=='
    for (const v of [google, dotted, b64]) expect(looksLikeToken(v)).toBe(true)
    expect(JSON.parse(maskSensitiveBody(JSON.stringify({ code: google, ticket: dotted }), false))).toEqual({
      code: '***',
      ticket: '***'
    })
    expect(looksLikeToken('INVALID_PARAMETER_VALUE')).toBe(false)
    expect(looksLikeToken('ORDER_20261021_0001')).toBe(false)
    expect(looksLikeToken('order 2026 10 21 0001')).toBe(false)
  })
  it('N-2 x-cos-security-token 在 URL 里替换', () => {
    expect(redactSensitiveUrl('https://b.cos.ap-shanghai.myqcloud.com/k?x-cos-security-token=t&a=1')).toBe(
      'https://b.cos.ap-shanghai.myqcloud.com/k?x-cos-security-token=***&a=1'
    )
  })
  it.each(['/sendEmailCode', '/user/getMsgCode', '/verifyEmailCode'])('N-3 %s 命中', (p) =>
    expect(isCredentialPath(p)).toBe(true)
  )
  it('srcset 长串逗号：线性处理，结果正确', () => {
    const commas = ','.repeat(200000)
    const t0 = Date.now()
    const out = redactSrcset(`/a.jpg?token=t${commas} /b.jpg 2x`)
    expect(Date.now() - t0).toBeLessThan(1000)
    expect(out).toBe(`/a.jpg?token=***${commas} /b.jpg 2x`)
  })
})

describe('r5', () => {
  it.each(['/getToken', '/api/refreshToken', '/renewAccessToken', '/getAccessToken'])('(a) %s 命中', (p) =>
    expect(isCredentialPath(p)).toBe(true)
  )
  it('(b) srcset 括号描述符里的逗号不拆候选', () => {
    expect(redactSrcset('a.jpg?token=1 1x, b.jpg?token=2 (x,y) 2x')).toBe('a.jpg?token=*** 1x, b.jpg?token=*** (x,y) 2x')
  })
  it('(c) 只改查询串与 hash，相对与协议相对 URL 逐字保留', () => {
    expect(redactSensitiveUrl('img/a.jpg?token=t&w=1')).toBe('img/a.jpg?token=***&w=1')
    expect(redactSensitiveUrl('img/a.jpg')).toBe('img/a.jpg')
    expect(redactSensitiveUrl('//cdn.x/a?token=t')).toBe('//cdn.x/a?token=***')
    expect(redactSensitiveUrl('../p/q?sign=s#frag')).toBe('../p/q?sign=***#frag')
    expect(redactSensitiveUrl('HTTPS://Ex.COM/A?token=t')).toBe('HTTPS://Ex.COM/A?token=***')
    expect(redactSensitiveUrl('/cb#access_token=a&state=x')).toBe('/cb#access_token=***&state=x')
  })
  it('(d) URL 编码的令牌（含 %）也替换', () => {
    const v = '4%2F0AbCdEfGhIjKlMnOpQrStUv123'
    expect(looksLikeToken(v)).toBe(true)
    expect(JSON.parse(maskSensitiveBody(JSON.stringify({ code: v }), false))).toEqual({ code: '***' })
  })
})

describe('r5 安全复核', () => {
  it.each([
    '/refresh-token',
    '/refresh_token',
    '/get-token',
    '/api/get_access_token',
    '/getAuthToken',
    '/getIdToken',
    '/issueToken',
    '/exchangeToken'
  ])('R5-1 %s 命中', (p) => expect(isCredentialPath(p)).toBe(true))
  it.each(['/tokens/stats', '/user/profile'])('R5-1 %s 不命中', (p) => expect(isCredentialPath(p)).toBe(false))

  it('R5-2 userinfo 替换为 ***，协议与主机保留', () => {
    expect(redactSensitiveUrl('https://user:pass@ex.com/a?b=1')).toBe('https://***@ex.com/a?b=1')
    expect(redactSensitiveUrl('//admin@cdn.x/a')).toBe('//***@cdn.x/a')
    expect(redactSensitiveUrl('ftp://u:p@h/f?token=t')).toBe('ftp://***@h/f?token=***')
    expect(redactSensitiveUrl('https://ex.com/a@b')).toBe('https://ex.com/a@b')
    expect(redactSensitiveUrl('/path/a@b?x=1')).toBe('/path/a@b?x=1')
  })
  it('R5-3 路径参数 ;jsessionid= 等敏感键替换', () => {
    expect(redactSensitiveUrl('/app/login;jsessionid=ABC123?x=1')).toBe('/app/login;jsessionid=***?x=1')
    expect(redactSensitiveUrl('https://ex.com/a;token=t;v=2/b')).toBe('https://ex.com/a;token=***;v=2/b')
    expect(redactSensitiveUrl('/a;v=2/b')).toBe('/a;v=2/b')
  })
  it('R5-4 先删 TAB/LF/CR 再匹配', () => {
    expect(redactSensitiveUrl('/x?to\nken=abc&a=1')).toBe('/x?token=***&a=1')
    expect(redactSensitiveUrl('/x?ac\tcess_tok\ren=abc')).toBe('/x?access_token=***')
    expect(redactSensitiveUrl('/x\n?a=1')).toBe('/x\n?a=1')
  })
})

describe('r6 安全复核', () => {
  it('R6-1 userinfo 取到最后一个 @', () => {
    expect(redactSensitiveUrl('https://u:p@ss@h/a')).toBe('https://***@h/a')
    expect(redactSensitiveUrl('https://u:p@ss@h/a@b?token=t')).toBe('https://***@h/a@b?token=***')
  })
  it('R6-2 开头空白 / 控制字符与反斜杠分隔符', () => {
    expect(redactSensitiveUrl('  https://u:p@h/a')).toBe('https://***@h/a')
    expect(redactSensitiveUrl('\u0000\u001fhttps://u:p@h/a')).toBe('https://***@h/a')
    expect(redactSensitiveUrl('https:\\\\u:p@h/a')).toBe('https:\\\\***@h/a')
    expect(redactSensitiveUrl('https:/\\u:p@h/a')).toBe('https:/\\***@h/a')
    expect(redactSensitiveUrl('\\\\u:p@h/a')).toBe('\\\\***@h/a')
    expect(redactSensitiveUrl('  /a?x=1')).toBe('  /a?x=1')
  })
  it('R6-2 长输入线性：无 @ 的长 authority、大量 @', () => {
    const t0 = Date.now()
    redactSensitiveUrl('https://' + 'a'.repeat(200000))
    redactSensitiveUrl('https://' + '@'.repeat(200000) + '/x')
    redactSensitiveUrl(' '.repeat(200000) + 'x')
    expect(Date.now() - t0).toBeLessThan(1000)
  })
})
