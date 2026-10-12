# @mugsun/track-web

[简体中文](./README.md) | English

Analytics should not lock you to one cloud.  
`@mugsun/track-web` collects in your frontend (~**5.5KB** gzip core), stores events in **your** database, and shows them on **your** dashboard.

[Docs](https://docs.mugsun.com/en/track/) · [First event](https://docs.mugsun.com/en/track/first-event) · [npm](https://www.npmjs.com/package/@mugsun/track-web)

[![npm](https://img.shields.io/npm/v/@mugsun/track-web)](https://www.npmjs.com/package/@mugsun/track-web)
[![core gzip](https://img.shields.io/badge/core_gzip-~5.5KB-blue)](#what-it-does)
[![tests](https://img.shields.io/badge/tests-155-brightgreen)](#local-development)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

```bash
pnpm add @mugsun/track-web
```

```ts
import { createTracker } from '@mugsun/track-web'

const track = createTracker({
  endpoint: 'https://your-server.com', // posts to {endpoint}/track/collect
  appKey: 'your-app-key',
})

track.track('button_click', { name: 'buy' })
```

Vue 3:

```ts
import MugsunTrack from '@mugsun/track-web/vue'
app.use(MugsunTrack, { endpoint, appKey, router })
```

End-to-end “first event on the dashboard”: [docs · first event](https://docs.mugsun.com/en/track/first-event). There is no public demo yet—run boot + pc locally as that page describes.

## What it does

Most product-analytics SDKs send data to a vendor cloud. This one assumes ingest, storage, and dashboards stay in environments you control—usually [mugsun-boot](https://github.com/mugsun/mugsun-boot) `/track/collect` plus [mugsun-pc](https://github.com/mugsun/mugsun-pc). The event protocol is open, so a custom backend works too. It is not Google Analytics and does not require a hosted mugsun analytics account.

The first paint ships core plus default plugins (pageview / pageleave / autocapture / exposure / web-vitals / error). Session replay, visual tagging, API monitor, and precise geo are opt-in separate entries. Queues persist in IndexedDB with exponential backoff; transport falls back sendBeacon → fetch keepalive → XHR; each event has a stable `event_id` for server-side dedupe.

Privacy defaults: honor DNT, `optOut()` / `optIn()`, never read input values, mask password trees and `maskSelectors`. Replay masks inputs by default. Details: [privacy](https://docs.mugsun.com/en/track/privacy). Full APIs live in the [docs](https://docs.mugsun.com/en/track/).

## How data flows

<p align="center">
  <img src="https://raw.githubusercontent.com/mugsun/mugsun-docs/main/public/brand/arch/track-iso-en.jpg" alt="Architecture" width="100%" />
</p>

`appKey` is visible in the browser—not a secret. The server relies on existence checks, per appKey+IP rate limits, bounded queues, and event validation.

## Related repos

| Repo | Role |
| --- | --- |
| **This repo** | Browser SDK (npm or `file:`) |
| [mugsun-boot](https://github.com/mugsun/mugsun-boot) | Ingest, config, aggregation |
| [mugsun-pc](https://github.com/mugsun/mugsun-pc) | Admin + dashboards (`file:../mugsun-track` in monorepo-style clones) |
| [mugsun-docs](https://github.com/mugsun/mugsun-docs) | [docs.mugsun.com](https://docs.mugsun.com/) |

## Local development

```bash
pnpm install && pnpm test && pnpm build
```

Version **0.1.0**; core gzip gate ≤ 8KB. Exports: main, `/vue`, `/replay`, `/core`.

## License

[MIT](./LICENSE)
