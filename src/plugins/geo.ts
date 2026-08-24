import type { PluginContext, Props, TrackPlugin } from '../types'

export interface GeoFix {
  lon: number
  lat: number
  accuracy?: number
}

export interface GeoPluginOptions {
  /** 测试注入；缺省走 Geolocation API */
  locate?: () => Promise<GeoFix | null>
}

const SCALE = 4
const SESSION_DONE = new Set<string>()

function round4(n: number): number {
  return Math.round(n * 10 ** SCALE) / 10 ** SCALE
}

function defaultLocate(): Promise<GeoFix | null> {
  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    return Promise.resolve(null)
  }
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        resolve({
          lon: pos.coords.longitude,
          lat: pos.coords.latitude,
          accuracy: pos.coords.accuracy
        })
      },
      () => resolve(null),
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 300000 }
    )
  })
}

function asSuper(fix: GeoFix): Props | null {
  const lon = round4(fix.lon)
  const lat = round4(fix.lat)
  if (!Number.isFinite(lon) || !Number.isFinite(lat)) return null
  if (lon < -180 || lon > 180 || lat < -90 || lat > 90) return null
  const props: Props = { geo_lon: lon, geo_lat: lat }
  if (typeof fix.accuracy === 'number' && Number.isFinite(fix.accuracy)) {
    props.geo_acc = Math.round(fix.accuracy)
  }
  return props
}

/**
 * 精确位置（G106）：开关由 /track/config geoEnabled 下发（默认关，下次启动生效）。
 * 每会话至多征求一次定位，成功后写入超属性 geo_lon/geo_lat（约 11m）；拒绝/失败静默。
 * 不在默认插件集；宿主显式注册后本开关才接管启停。
 */
export function geoPlugin(pluginOpts: GeoPluginOptions = {}): TrackPlugin {
  const locate = pluginOpts.locate ?? defaultLocate
  return {
    name: 'geo',
    setup(ctx: PluginContext) {
      const { client, options } = ctx
      if (options.geoEnabled !== true) return

      const run = (sessionId: string | null): void => {
        if (!sessionId || SESSION_DONE.has(sessionId)) return
        SESSION_DONE.add(sessionId)
        void locate()
          .then((fix) => {
            if (!fix) return
            const props = asSuper(fix)
            if (props) client.registerSuperProperties(props)
          })
          .catch(() => {
            // 定位 API 异常不影响主采集
          })
      }

      run(client.getSessionId())
      return client.onSessionChange(run)
    }
  }
}

export { round4 as roundGeoCoord, asSuper as geoFixToSuper }
