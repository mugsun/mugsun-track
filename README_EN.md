![mugsun-track](https://raw.githubusercontent.com/mugsun/mugsun-docs/main/public/brand/banners/repos/mugsun-track-en.png)

# @mugsun/track-web

[简体中文](./README.md) | English

This repository publishes a browser analytics SDK. Collection, storage, and dashboards may be deployed in a self-managed environment. The default ingest path is [mugsun-boot](https://github.com/mugsun/mugsun-boot) `/track/collect`.

[Documentation](https://docs.mugsun.com/en/track/) · [First event](https://docs.mugsun.com/en/track/first-event) · [npm](https://www.npmjs.com/package/@mugsun/track-web)

[![npm](https://img.shields.io/npm/v/@mugsun/track-web)](https://www.npmjs.com/package/@mugsun/track-web)
[![core gzip](https://img.shields.io/badge/core_gzip-~5.5KB-blue)](#composition)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

## Overview

| Item | Detail |
| --- | --- |
| Package | `@mugsun/track-web` |
| Version | `0.1.1` (repo tip; npm still `0.1.0` until publish) |
| Runtime | Browser; Node.js ≥ 20 for build and test |
| License | [MIT](./LICENSE) |
| Docs | [docs.mugsun.com/en/track](https://docs.mugsun.com/en/track/) |

The SDK provides a plugin core for pageview, page leave, autocapture, exposure, Web Vitals, and error collection. Session replay, visual tagging, API monitoring, and geo plugins are registered explicitly and are not part of the default first-load bundle.

## Deployment

```bash
pnpm add @mugsun/track-web
```

```ts
import { createTracker } from '@mugsun/track-web'

const track = createTracker({
  endpoint: 'https://example.com', // posts to {endpoint}/track/collect
  appKey: 'your-app-key',
})

track.track('button_click', { name: 'buy' })
```

Vue 3:

```ts
import MugsunTrack from '@mugsun/track-web/vue'
app.use(MugsunTrack, { endpoint, appKey, router })
```

End-to-end steps from an empty environment to the first dashboard event: [Documentation · First event](https://docs.mugsun.com/en/track/first-event).

## Composition

<p align="center">
  <img src="https://raw.githubusercontent.com/mugsun/mugsun-docs/main/public/brand/arch/track-iso-en.jpg" alt="Data flow diagram" width="100%" />
</p>

| Export | Purpose |
| --- | --- |
| `@mugsun/track-web` | Main entry: `createTracker`, default plugins |
| `@mugsun/track-web/core` | Core logic without DOM adapters |
| `@mugsun/track-web/vue` | Vue 3 plugin and directives |
| `@mugsun/track-web/replay` | Session replay (separate entry) |

Default plugins: `pageview`, `pageleave`, `autocapture`, `exposure`, `web-vitals`, `error`.

Optional plugins (explicit registration): `api-monitor`, `visual-track`, `geo`. Replay loads via the `/replay` entry.

Transport order: `sendBeacon` → `fetch` keepalive → `XHR`. The queue defaults to IndexedDB and retries with exponential backoff after offline periods or reloads. Events carry a stable `event_id` for server-side idempotent handling.

`appKey` is visible in the browser and is not a secret. The server must enforce existence checks, rate limits, queue backpressure, and event validation.

Privacy defaults: honor DNT; provide `optOut()` / `optIn()`; do not read `input` / `textarea` values; mask `password` trees and `maskSelectors` matches. Replay masks inputs by default. API-monitor strips sensitive URL query keys (e.g. `token` / `access_token`, values replaced with `***`). See [Privacy](https://docs.mugsun.com/en/track/privacy).

Build gate: `dist/core.js` gzip size must not exceed 8 KB. Published core size is approximately 5.5 KB gzip.

## Scope

**Provided**

- Privatizable collection protocol and default backend integration path
- Lightweight core with optional plugins
- Offline retry and stable `event_id`
- Privacy-oriented defaults

**Not provided**

- Hosted public-cloud analytics accounts
- A publicly accessible demo environment (local verification uses boot + pc; see [Demo](https://docs.mugsun.com/en/demo))

API fields, plugin options, and configuration keys are defined in the [documentation](https://docs.mugsun.com/en/track/) and source tree.

## Related projects

| Repository | Role |
| --- | --- |
| This repository `@mugsun/track-web` | Browser SDK |
| [mugsun-boot](https://github.com/mugsun/mugsun-boot) | Ingest, config delivery, analytics APIs |
| [mugsun-pc](https://github.com/mugsun/mugsun-pc) | Access management and analytics console |
| [mugsun-docs](https://github.com/mugsun/mugsun-docs) | Documentation site [docs.mugsun.com](https://docs.mugsun.com/) |

When developing alongside `mugsun-pc`, this repository does not commit `dist/`. Run `pnpm build` first, or use `pnpm setup:sdk` in pc. Application projects should install the published npm package.

## Local development

```bash
pnpm install
pnpm test      # vitest
pnpm build     # emits dist/; size gate in scripts/report-size.mjs
```

## License

[MIT](./LICENSE)