![mugsun-track](https://raw.githubusercontent.com/mugsun/mugsun-docs/main/public/brand/banners/repos/mugsun-track-en.png)

# @mugsun/track-web

[简体中文](./README.md) | English

This repository publishes a browser analytics SDK. Collection, storage, and dashboards may be deployed in a self-managed environment. The default ingest path is [mugsun-boot](https://github.com/mugsun/mugsun-boot) `/track/collect`.

[Documentation](https://docs.mugsun.com/en/track/) · [First event](https://docs.mugsun.com/en/track/first-event) · [npm](https://www.npmjs.com/package/@mugsun/track-web)

[![npm](https://img.shields.io/npm/v/@mugsun/track-web)](https://www.npmjs.com/package/@mugsun/track-web)
[![core gzip](https://img.shields.io/badge/core_gzip-~6.3KB-blue)](#composition)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](./LICENSE)

## Overview

| Item | Detail |
| --- | --- |
| Package | `@mugsun/track-web` |
| Version | `0.3.0` (published on npm as `@mugsun/track-web@0.3.0`) |
| Runtime | Browser; Node.js ≥ 22.13 and pnpm ≥ 11.11 for build and test (see `engines` / `packageManager` in package.json) |
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

Privacy defaults: honor DNT (`respectDnt`); Global Privacy Control is ignored unless you set `respectGpc: true`; provide `optOut()` / `optIn()`; autocaptured click / change events carry no `input` / `textarea` values (input values in replays follow `maskAllInputs`, see below); mask `password` trees and `maskSelectors` matches. Replay shows page text and input values as-is by default (pass `maskTextSelector: '*'` or a narrower selector, and `maskAllInputs: true`, to mask them); password fields, `data-track-mask` areas, card fields (`autocomplete=cc-*`) and one-time-code fields are never recorded; `apiBodyMaskEnabled` defaults to off: credential keys in response bodies (`token`, `access_token`, `refresh_token`, `password`, `secret`, `cookie`, …) are always replaced with `***`, while personal data such as phone, email and ID numbers is uploaded as-is unless you set it to `true`. API-monitor strips sensitive URL query keys (e.g. `token` / `access_token`, values replaced with `***`). See [Privacy](https://docs.mugsun.com/en/track/privacy).

Build gate: `dist/core.js` gzip size must not exceed 8 KB. Published core size is approximately 6.3 KB gzip.

## Self-check and error filtering

```ts
const tracker = createTracker({
  endpoint: 'https://api.example.com',
  appKey: 'your-app-key',
  // Rewrite props or drop before sending (return null/false to drop); a throwing hook drops the event by default
  beforeSend: (e) => (e.event === 'debug_only' ? null : e),
  // Strings match a message substring, RegExps test the message, or a predicate (error, message) => boolean
  ignoreErrors: ['ResizeObserver loop', /^AbortError/],
  // Default false (report everything); set true to skip name==='HttpError' and errors flagged handled/expected
  skipHandledErrors: true
})

tracker.trackApiError({ url: '/api/order', method: 'POST', status: 200, bizCode: 40001, message: 'Out of stock' })

const report = await tracker.selfCheck()
console.table(report.items) // each { id, status: 'ok'|'warn'|'fail', message, fix }
```

- `beforeSend` merges only the returned object's `props` (`event_id`, `distinct_id` etc. can't be changed); non-object return values mean "unchanged". If the hook throws, the event is **dropped by default** so a broken masking hook can't leak unmasked data; set `beforeSendOnError: 'keep'` to send the original event instead.
- **Not covered by `beforeSend`**: session events (`$session_start` / `$session_end`), **session replay** chunks and **API response body** uploads. Use `maskTextSelector` / `maskSelectors` for replay and `apiBodyMaskEnabled` (off by default) for bodies.
- `selfCheck()` makes one real `GET /track/config?app_key=` request (no cookies), sends no user data and enqueues nothing. Messages are in Chinese.
- `trackApiError` emits an `api_request` event (`success=false`, `source=manual`, with `biz_code`), same shape as `api-monitor`; sensitive query values in `url` (`token`, `access_token`, …) are replaced with `***`.
- `skipHandledErrors` defaults to `false`: `HttpError` and handled/expected errors are reported as `$error` by default; set it to `true` to skip them.
- `ignoreErrors` / `skipHandledErrors` apply to the `error` plugin (window error, unhandledrejection) and the Vue `errorHandler`.
- The collect URL carries `?app_key=` so the server can attribute rejected requests (unparseable or oversized bodies) to the app; see "Integration health" in the admin UI.
- The self-check implementation is injected by `createTracker` and is not part of the core entry; core-only users inject `deps.selfCheck = runSelfCheck`.

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