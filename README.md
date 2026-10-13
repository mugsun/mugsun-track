![mugsun-track](https://raw.githubusercontent.com/mugsun/mugsun-docs/main/public/brand/banners/repos/mugsun-track.png)

# @mugsun/track-web

[English](./README_EN.md) | 简体中文

本仓库发布浏览器端行为采集 SDK。采集、存储与分析看板可部署于自有环境，默认对接 [mugsun-boot](https://github.com/mugsun/mugsun-boot) 的 `/track/collect` 接口。

[文档](https://docs.mugsun.com/track/) · [接入说明](https://docs.mugsun.com/track/first-event) · [npm](https://www.npmjs.com/package/@mugsun/track-web)

[![npm](https://img.shields.io/npm/v/@mugsun/track-web)](https://www.npmjs.com/package/@mugsun/track-web)
[![core gzip](https://img.shields.io/badge/core_gzip-~5.5KB-blue)](#组成)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

## 概述

| 项 | 说明 |
| --- | --- |
| 包名 | `@mugsun/track-web` |
| 版本 | `0.2.0`（仓内；npm 当前仍为 `0.1.0`，待发布） |
| 运行时 | 浏览器；Node.js ≥ 20（构建与测试） |
| 许可 | [MIT](./LICENSE) |
| 文档 | [docs.mugsun.com/track](https://docs.mugsun.com/track/) |

本组件提供插件化内核，支持页面浏览、停留、全埋点、曝光、Web Vitals 与错误采集。会话回放、圈选埋点、接口监控与地理信息插件按需注册，不进入默认首包。

## 部署

```bash
pnpm add @mugsun/track-web
```

```ts
import { createTracker } from '@mugsun/track-web'

const track = createTracker({
  endpoint: 'https://example.com', // 实际上报 {endpoint}/track/collect
  appKey: 'your-app-key',          // 管理端「埋点分析 → 接入管理」创建
})

track.track('button_click', { name: 'buy' })
```

Vue 3：

```ts
import MugsunTrack from '@mugsun/track-web/vue'
app.use(MugsunTrack, { endpoint, appKey, router })
```

从空环境到看板可见首条事件的完整步骤，见 [文档 · 第一个事件](https://docs.mugsun.com/track/first-event)。

## 组成

<p align="center">
  <img src="https://raw.githubusercontent.com/mugsun/mugsun-docs/main/public/brand/arch/track-iso-zh.jpg" alt="数据流示意" width="100%" />
</p>

| 导出入口 | 用途 |
| --- | --- |
| `@mugsun/track-web` | 主包：`createTracker`、默认插件 |
| `@mugsun/track-web/core` | 无 DOM 依赖的核心逻辑 |
| `@mugsun/track-web/vue` | Vue 3 插件与指令 |
| `@mugsun/track-web/replay` | 会话回放（独立入口） |

默认插件：`pageview`、`pageleave`、`autocapture`、`exposure`、`web-vitals`、`error`。

可选插件（须显式注册）：`api-monitor`、`visual-track`、`geo`；回放通过 `/replay` 入口加载。

传输链路：`sendBeacon` → `fetch` keepalive → `XHR`。队列默认写入 IndexedDB；断网或页面刷新后按指数退避补发。事件携带稳定 `event_id`，供服务端幂等处理。

`appKey` 在浏览器端可见，不具备机密性。服务端须通过存在性校验、限流、队列背压与事件校验实施防护。

隐私默认项：尊重 DNT；提供 `optOut()` / `optIn()`；不采集 `input` / `textarea` 的 `value`；对 `password` 及 `maskSelectors` 命中区域屏蔽。回放默认遮罩输入与页面文本（`maskTextSelector: '*'`，可显式关闭）；`apiBodyMaskEnabled` 默认开启。接口监控上报 URL 会剥离敏感 query（如 `token` / `access_token` 等，值替换为 `***`）。细则见 [隐私与合规](https://docs.mugsun.com/track/privacy)。

构建门禁：`dist/core.js` gzip 体积不超过 8 KB；当前发布说明中的 core 体积约为 5.5 KB gzip。

## 能力范围

**已提供**

- 可私有化部署的采集协议与默认后端对接路径
- 轻量 core 与可裁剪插件
- 断网补发、稳定 `event_id`
- 隐私相关默认策略

**暂未提供**

- 托管于公有云的分析账号服务
- 可公开访问的在线演示环境（本地通过 boot + pc 联调，见 [演示说明](https://docs.mugsun.com/demo)）

接口字段、插件参数与配置项以 [文档](https://docs.mugsun.com/track/) 及源码为准。

## 关联项目

| 仓库 | 职责 |
| --- | --- |
| 本仓库 `@mugsun/track-web` | 浏览器 SDK |
| [mugsun-boot](https://github.com/mugsun/mugsun-boot) | 采集摄入、配置下发、聚合相关 API |
| [mugsun-pc](https://github.com/mugsun/mugsun-pc) | 接入管理与分析看板 |
| [mugsun-docs](https://github.com/mugsun/mugsun-docs) | 文档站 [docs.mugsun.com](https://docs.mugsun.com/) |

与 `mugsun-pc` 平级联调时，本仓库不提交 `dist/`，须先执行 `pnpm build`，或在 pc 侧执行 `pnpm setup:sdk`。业务项目日常安装使用 npm 包即可。

## 本地开发

```bash
pnpm install
pnpm test      # vitest
pnpm build     # 产出 dist/；体积门禁见 scripts/report-size.mjs
```

## 许可

[MIT](./LICENSE) · © 2026 北京定旭晨 / mugsun
