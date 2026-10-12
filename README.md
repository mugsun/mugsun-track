# @mugsun/track-web

[English](./README_EN.md) | 简体中文

埋点不该绑死一家云。  
`@mugsun/track-web`：浏览器侧约 5.5KB gzip，事件进你自己的库，看板跑在你自己的机器上。

[文档](https://docs.mugsun.com/track/) · [第一个事件](https://docs.mugsun.com/track/first-event) · [npm](https://www.npmjs.com/package/@mugsun/track-web)

[![npm](https://img.shields.io/npm/v/@mugsun/track-web)](https://www.npmjs.com/package/@mugsun/track-web)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

```bash
pnpm add @mugsun/track-web
```

```ts
import { createTracker } from '@mugsun/track-web'

const track = createTracker({
  endpoint: 'https://your-server.com', // 上报到 {endpoint}/track/collect
  appKey: 'your-app-key',
})

track.track('button_click', { name: 'buy' })
```

默认对接 [mugsun-boot](https://github.com/mugsun/mugsun-boot)，也可接自建后端。回放、圈选、接口监控是可选插件，不进首包。尊重 DNT，不采输入框内容。

Vue 接入、事件协议与隐私细则见 [文档](https://docs.mugsun.com/track/)。本地：`pnpm install && pnpm test && pnpm build`。

[MIT](./LICENSE)
