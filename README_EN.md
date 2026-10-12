# @mugsun/track-web

[简体中文](./README.md) | English

Web behavioral analytics SDK. Core bundle is approximately 5.5KB gzipped. Events are intended for submission to a privately deployable backend and for use with the companion admin analytics UI.

[Documentation](https://docs.mugsun.com/en/track/) · [First event](https://docs.mugsun.com/en/track/first-event) · [npm](https://www.npmjs.com/package/@mugsun/track-web)

[![npm](https://img.shields.io/npm/v/@mugsun/track-web)](https://www.npmjs.com/package/@mugsun/track-web)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

## Installation

```bash
pnpm add @mugsun/track-web
```

```ts
import { createTracker } from '@mugsun/track-web'

const track = createTracker({
  endpoint: 'https://your-server.com', // requests go to {endpoint}/track/collect
  appKey: 'your-app-key',
})

track.track('button_click', { name: 'buy' })
```

Vue 3:

```ts
import MugsunTrack from '@mugsun/track-web/vue'
app.use(MugsunTrack, { endpoint, appKey, router })
```

Full integration steps: [First event](https://docs.mugsun.com/en/track/first-event). A public demonstration environment is not available; verify locally with boot and pc as documented.

## Overview

The SDK is designed for deployments that retain control of collection, storage, and presentation. The default integration targets [mugsun-boot](https://github.com/mugsun/mugsun-boot) `/track/collect` and [mugsun-pc](https://github.com/mugsun/mugsun-pc). Compatible custom backends are supported.

Default plugins include pageview, pageleave, autocapture, exposure, web-vitals, and error. Session replay, visual tagging, API monitoring, and precise geolocation require explicit registration and load from separate entry points. The event queue persists in IndexedDB and retries with exponential backoff. Transport attempts sendBeacon, then fetch keepalive, then XHR. Each event includes a stable `event_id` for server-side deduplication.

Defaults respect Do Not Track; `optOut()` / `optIn()` are provided; input values are not collected; password fields and `maskSelectors` subtrees are masked; replay masks inputs by default. See [Privacy](https://docs.mugsun.com/en/track/privacy). APIs and configuration are documented at [docs.mugsun.com](https://docs.mugsun.com/en/track/).

## Architecture

<p align="center">
  <img src="https://raw.githubusercontent.com/mugsun/mugsun-docs/main/public/brand/arch/track-iso-en.jpg" alt="Architecture" width="100%" />
</p>

`appKey` is readable in the browser and is not a secret credential. The server applies application existence checks, rate limiting by appKey and IP, bounded queues, and event validation.

## Related repositories

| Repository | Description |
| --- | --- |
| This repository | Browser SDK (npm; optional `file:` linkage) |
| [mugsun-boot](https://github.com/mugsun/mugsun-boot) | Ingest, configuration, aggregation |
| [mugsun-pc](https://github.com/mugsun/mugsun-pc) | Administration and analytics UI |
| [mugsun-docs](https://github.com/mugsun/mugsun-docs) | Documentation site |

## Local build

```bash
pnpm install && pnpm test && pnpm build
```

Current version: **0.1.0**. Approximately 155 unit tests. Core gzip size gate: ≤ 8KB. Exports: main, `/vue`, `/replay`, `/core`.

## License

[MIT](./LICENSE)
