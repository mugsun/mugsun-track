import { afterEach, describe, expect, it } from 'vitest'
import { geoPlugin } from '../src/plugins/geo'
import { allEvents, createTestClient, destroyAllClients } from './helpers'

afterEach(() => destroyAllClients())

describe('geo 插件', () => {
  it('geoEnabled 未开时不征求定位', async () => {
    let called = 0
    const t = createTestClient({
      plugins: [
        geoPlugin({
          locate: async () => {
            called++
            return { lon: 116.397428, lat: 39.90923 }
          }
        })
      ]
    })
    t.client.track('page')
    await t.client.flush()
    expect(called).toBe(0)
    expect(allEvents(t.sent)[0]?.props.geo_lon).toBeUndefined()
  })

  it('开启后圆整超属性并随事件上报', async () => {
    const t = createTestClient({
      geoEnabled: true,
      plugins: [
        geoPlugin({
          locate: async () => ({ lon: 116.397428, lat: 39.90923, accuracy: 12.4 })
        })
      ]
    })
    await new Promise((r) => setTimeout(r, 0))
    t.client.track('located')
    await t.client.flush()
    const ev = allEvents(t.sent).find((e) => e.event === 'located')
    expect(ev?.props.geo_lon).toBe(116.3974)
    expect(ev?.props.geo_lat).toBe(39.9092)
    expect(ev?.props.geo_acc).toBe(12)
  })

  it('越界坐标不写超属性', async () => {
    const t = createTestClient({
      geoEnabled: true,
      plugins: [geoPlugin({ locate: async () => ({ lon: 200, lat: 30 }) })]
    })
    await new Promise((r) => setTimeout(r, 0))
    t.client.track('bad')
    await t.client.flush()
    expect(allEvents(t.sent)[0]?.props.geo_lon).toBeUndefined()
  })

  it('同一会话只征求一次定位', async () => {
    let called = 0
    const t = createTestClient({
      geoEnabled: true,
      plugins: [
        geoPlugin({
          locate: async () => {
            called++
            return { lon: 116.4, lat: 39.9 }
          }
        })
      ]
    })
    await new Promise((r) => setTimeout(r, 0))
    t.client.track('a')
    await t.client.flush()
    t.client.track('b')
    await t.client.flush()
    expect(called).toBe(1)
  })
})
