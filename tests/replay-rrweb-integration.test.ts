// @vitest-environment happy-dom
// 真实 rrweb（package.json 固定 2.1.1）录制，经插件同一条 emit 管道后检查脱敏
import { afterEach, describe, expect, it } from 'vitest'
import { record } from 'rrweb'
import { redactReplayUrls } from '../src/plugins/replay'

// happy-dom 的 window 上 NodeList / DOMTokenList 键存在但值为 undefined，rrweb 的 polyfill 会读 .prototype 报错；
// 用实例的构造函数补上（只影响测试环境）
const w = window as unknown as Record<string, unknown>
if (!w.NodeList) w.NodeList = document.querySelectorAll('x').constructor
if (!w.DOMTokenList) w.DOMTokenList = document.createElement('div').classList.constructor

afterEach(() => {
  document.body.innerHTML = ''
})

const collect = (setup: () => void) => {
  setup()
  const events: any[] = []
  const stop = record({
    emit: (e) => {
      events.push(redactReplayUrls(e))
    },
    blockSelector: '[data-track-mask]'
  })
  stop?.()
  return events
}

describe('真实 rrweb 全量快照', () => {
  it('href / src / srcset 脱敏，data-track-mask 元素属性不录', () => {
    const events = collect(() => {
      document.body.innerHTML = `
        <a id="l" href="/cb?code=c1&page=2">x</a>
        <img id="i" src="https://s.example.com/a.png?token=t&w=1" srcset="/a.jpg?sign=s 1x, /b.jpg 2x">
        <div data-track-mask title="/x?token=secret"></div>`
    })
    const full = events.find((e) => e.type === 2)
    expect(full).toBeTruthy()
    const json = JSON.stringify(full)
    expect(json).toContain('code=***')
    expect(json).toContain('token=***')
    expect(json).toContain('sign=***')
    expect(json).not.toContain('code=c1')
    expect(json).not.toContain('token=t&')
    expect(json).not.toContain('secret')
  })
})
