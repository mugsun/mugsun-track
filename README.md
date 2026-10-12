# @mugsun/track-web

[English](./README_EN.md) | 简体中文

埋点不该绑死一家云。  
`@mugsun/track-web` 把采集放进你自己的前端：core 约 **5.5KB gzip**，事件进你自己的库，看板跑在你自己的机器上。

[文档](https://docs.mugsun.com/track/) · [第一个事件](https://docs.mugsun.com/track/first-event) · [npm](https://www.npmjs.com/package/@mugsun/track-web)

[![npm](https://img.shields.io/npm/v/@mugsun/track-web)](https://www.npmjs.com/package/@mugsun/track-web)
[![core gzip](https://img.shields.io/badge/core_gzip-~5.5KB-blue)](#它做什么)
[![tests](https://img.shields.io/badge/tests-155-brightgreen)](#本地开发)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

```bash
pnpm add @mugsun/track-web
```

```ts
import { createTracker } from '@mugsun/track-web'

const track = createTracker({
  endpoint: 'https://your-server.com', // 实际上报 {endpoint}/track/collect
  appKey: 'your-app-key',              // 管理端「埋点分析 → 接入管理」新建
})

track.track('button_click', { name: 'buy' })
```

Vue 3：

```ts
import MugsunTrack from '@mugsun/track-web/vue'
app.use(MugsunTrack, { endpoint, appKey, router })
```

从空环境到看板里看到第一条事件：[文档 · 第一个事件](https://docs.mugsun.com/track/first-event)。目前没有公网 Demo，本地请按该页用 boot + pc 跑通。

## 它做什么

多数产品分析工具默认把数据送进厂商云。这个 SDK 默认假设摄入、存储、看板都在你可控的环境里——常见搭配是 [mugsun-boot](https://github.com/mugsun/mugsun-boot) 的 `/track/collect` 与 [mugsun-pc](https://github.com/mugsun/mugsun-pc) 看板；协议开放，也可以对接自建后端。它不是 Google Analytics，也不要求你开我们的分析云账号。

首包只带核心与默认插件（pageview / pageleave / autocapture / exposure / web-vitals / error）。会话回放、圈选埋点、接口监控、精确 geo 需要显式注册，走独立入口。队列落 IndexedDB，断网或刷新后指数退避补发；传输走 sendBeacon → fetch keepalive → XHR；每条事件有稳定 `event_id` 供服务端去重。

隐私默认尊重 DNT，提供 `optOut()` / `optIn()`，不采集输入框内容，password 与 `maskSelectors` 子树整块屏蔽；回放默认遮罩输入。细则见 [隐私与合规](https://docs.mugsun.com/track/privacy)。API、事件字段与插件配置以 [文档](https://docs.mugsun.com/track/) 为准。

## 数据怎么走

<p align="center">
  <img src="https://raw.githubusercontent.com/mugsun/mugsun-docs/main/public/brand/arch/track-iso-zh.jpg" alt="Architecture" width="100%" />
</p>

appKey 在浏览器可见，不要当成机密。服务端靠存在性校验、appKey+IP 限流、有界队列背压与事件校验来防护。

## 相关仓库

| 仓 | 职责 |
| --- | --- |
| **本仓** | 浏览器 SDK（npm；或 `file:` 联调） |
| [mugsun-boot](https://github.com/mugsun/mugsun-boot) | 采集摄入、配置下发、聚合 |
| [mugsun-pc](https://github.com/mugsun/mugsun-pc) | 接入管理与看板；开发时常用 `file:../mugsun-track` |
| [mugsun-docs](https://github.com/mugsun/mugsun-docs) | [docs.mugsun.com](https://docs.mugsun.com/) |

与 pc 平级开发时源码仓不提交 `dist/`，需先 `pnpm build`，或在 pc 跑 `pnpm setup:sdk`。业务项目直接 `pnpm add @mugsun/track-web` 即可。

## 本地开发

```bash
pnpm install
pnpm test      # vitest，约 155 例
pnpm build     # dist/；core gzip 门禁 ≤ 8KB（scripts/report-size.mjs）
```

当前版本 **0.1.0**。导出：主包、`/vue`、`/replay`、`/core`。

## License

[MIT](./LICENSE)
