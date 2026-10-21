# 更新日志

本文件记录 [mugsun-track](https://github.com/mugsun/mugsun-track) 的重要变更，格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)。包版本以根目录 `package.json` 中 `@mugsun/track-web` 为准。

## [Unreleased]

> 计划版本：**0.3.0**（minor，含下方行为变更）。本 PR 不改 `package.json` 版本号，避免合入即触发自动发布；发版另走版本 PR。

> **升级提示**：如果你靠 0.2.0 的默认遮罩满足合规要求，升级后必须显式配置 `replayPlugin({ maskTextSelector: '*', maskAllInputs: true })` 和 `apiBodyMaskEnabled: true`，否则回放会录页面文本和输入框的原值，响应体里的个人信息字段会原文上传。
>
> 注意远端配置：mugsun-boot 的 `track_app.api_body_mask_enabled` 默认是 `0`，`/track/config` 会下发 `apiBodyMaskEnabled: false`。本地没有设置 `apiBodyMaskEnabled` 时，SDK 用远端值（下次启动生效），所以即使在 0.2.0，开了远端配置的应用实际也不脱敏。想确保脱敏，就在本地显式设 `apiBodyMaskEnabled: true`（本地显式设置优先于远端），或在管理后台打开「响应体脱敏」。

### 行为变更

- **会话回放默认不遮罩页面文本**：`replayPlugin` 的 `maskTextSelector` 默认不再是 `'*'`，回放里显示原文（0.2.0 起默认遮全页文本）。需要遮罩请显式传 `replayPlugin({ maskTextSelector: '*' })` 或更窄的选择器。
- **会话回放默认不遮罩输入值**：新增 `replayPlugin({ maskAllInputs })` 选项，默认 `false`，输入框的值录原文（0.2.0 固定为 `true`，所有输入值录成 `***`）。想保持 0.2.0 的行为请设 `maskAllInputs: true`。
- **回放始终不录的字段**（不论上面两个选项）：`input[type="password"]`、`data-track-mask` 与 `maskSelectors` 命中的区域、银行卡字段（`autocomplete` 以 `cc-` 开头）、一次性验证码字段（`autocomplete="one-time-code"`）整块不录，canvas 不录。银行卡和一次性验证码是新增的。密码框另外通过 rrweb 的 `maskInputOptions: { password: true }` 兜底。
- **`apiBodyMaskEnabled` 默认改为 `false`，响应体脱敏拆成两层**（api-body 上传器内部的 `maskEnabled` 同步默认 `false`）：
  - 凭证类键 **始终** 替换为 `***`，不受开关控制：`token`、`access_token`、`refresh_token`、`id_token`、`authorization`、`api_key`、`apikey`、`x-api-key`、`auth`、`secret`、`client_secret`、`private_key`、`password`、`passwd`、`pwd`、`cookie`、`set-cookie`、`session`、`session_id`、`jsessionid`、`jwt`、`access_key`、`secret_key`、`x-amz-signature`、`x-amz-security-token`、`x-goog-signature`（与 URL 脱敏共用一份清单）。键名先去掉 `-`、`_` 再小写后匹配，所以 `accessToken`、`Access-Token`、`ACCESS_TOKEN`、`sessionId` 都算。0.2.0 的清单只有 `token` 等少数几个键，而且只做小写匹配，现在会多替换一些键。
  - 个人信息类键（`phone`、`mobile`、`email`、`idcard`、`bankcard`）由 `apiBodyMaskEnabled` 控制，默认原文上传（0.2.0 默认脱敏）。需要脱敏请显式设 `apiBodyMaskEnabled: true`，或远端下发 `1`。
  - 导出的 `maskSensitiveBody(raw, personal = true)` 新增第二个参数，不传时与原来一样两类都替换。
  - content-type 为 JSON 但内容解析失败时，不上传响应体，事件标 `body_skipped: 'unparsable'`（此前会原文上传）。非 JSON 的 content-type 本来就不采集。嵌套超过 8 层的子树整体替换为 `***`（此前原样保留）。凭证端点（`/auth/login` 等）的响应体仍然一律不采集。
- **`skipHandledErrors` 默认 `false`**：`HttpError` 及 `handled === true` / `expected === true` 的错误默认照常上报为 `$error`，与 0.2.0 一致（此前未发布的 main 上默认是 `true`）。需要跳过请显式设 `skipHandledErrors: true`。
- **`selfCheck()` 提示**：开启响应体采集但没有显式设 `apiBodyMaskEnabled: true` 时（包括默认），privacy 项提示「响应体采集已开启，个人信息字段未脱敏（凭证类键始终脱敏）」；回放已加载但没有设 `maskTextSelector` 或 `maskAllInputs: true` 时，replay 项也提示。两者都只是 `warn`，不会 `fail`。此前只在显式设 `apiBodyMaskEnabled: false` 时提示。
- **尊重 Global Privacy Control**：新增 `respectGpc` 选项，默认 `true`，与 `respectDnt` 一致。浏览器 `navigator.globalPrivacyControl === true` 时 SDK 停用，`selfCheck()` 的 consent 项提示。只影响开启 GPC 的用户；调试可设 `respectGpc: false`。
- **URL 敏感参数新增 `code`、`sign`、`signature`、`ticket`、`session`、`otp`**（OAuth 授权码、签名、SSO 票据、会话标识、一次性验证码），以及云存储预签名参数 Azure SAS `sig`、腾讯云 COS `q-signature`、阿里云 OSS `x-oss-signature` / `x-oss-security-token`、腾讯云 COS 临时密钥 `x-cos-security-token`（URL 专用）。URL 脱敏只改 userinfo、路径参数、查询串和 hash（只替换命中键的值，其他参数逐字保留，不再重新编码 `%20`、`/`），协议、主机、路径逐字保留：`https://user:pass@host` 的 `user:pass` 替换为 `***`（取到最后一个 `@`，`//` 也接受反斜杠写法，http(s)、ws(s)、ftp、file 里反斜杠和 `/` 一样结束 authority（与浏览器一致，`https://h\@evil/x` 不动）；`mongodb://`、`redis://` 等其他协议里反斜杠是普通字符，`mongodb://u:p\w@h` 整段遮住；开头的空白和控制字符先去掉。已知漏判：缺 `//` 的 `https:u:p@h`；special scheme 的原始串中，密码若含字面 `\`，不会被遮（与浏览器解析一致））；路径参数 `;jsessionid=…` 等敏感键的值替换为 `***`；匹配前先删掉 TAB、换行、回车（浏览器解析 URL 时也会删），`to\nken=x` 照样替换。相对 URL（`img/a.jpg?token=`）和协议相对 URL（`//cdn.x/a?token=`）不再被改写成以 `/` 开头的路径或丢掉主机，值替换为 `***`。hash 里的参数也会处理：OAuth 隐式流的 `#access_token=...` 和 hash 路由的 `#/cb?code=...`。
- **两份清单**：凭证键清单（`token`、`access_token`、`client_secret`、`session`、`session_id`、`x-api-key`、`cookie`、`jwt`、`access_key`、`secret_key` 等）URL、hash、referrer 与响应体共用；`code`、`sign`、`signature`、`ticket`、`otp` 单列为 URL 专用清单，只在查询串、hash、referrer 里替换。这几个键在响应体里常是业务字段，比如 `{"code":0,"msg":"ok"}`，保留原值，方便看接口错误、复现问题。两份清单都按归一后精确匹配，不做子串匹配，`codeType`、`errCode`、`ticketCount` 保留。
- **凭证端点清单扩充**：路径（小写后）含 `/register`、`/signup`、`/sign-up`、`/password`、`/forgot`、`/reset-password`、`/change-password`、`/otp`、`/sms`、`/captcha`、`/mfa`、`/2fa`、`/totp`、`/verify-code`、`/verification-code` 的接口不采集响应体，事件标 `body_skipped: 'credential'`。此前只有登录、刷新令牌、OAuth 令牌、社交登录四类，且区分大小写。误判只会少采一个响应体。
- **凭证端点再补全**（路径小写后判定，命中则不采集响应体）：
  - 整段匹配 `login`、`signin`、`sign-in`、`logout`、`token`、`sso`、`cas`：左侧是 `/` 或开头，右侧是 `/`、`.`、`;` 或结尾。`/api/login`、`/api/v1/login.json`、`/login.do`、`/login;jsessionid=x`、`/oauth2/token`、`/cas/login` 命中；`/monitor/loginLog/list`、`/system/logininfor/list`、`/tokens/stats`、`/case/list`、`/cascade/tree`、`/api/cashier/pay` 不命中。
  - 子串匹配 `captcha`、`verifycode`、`verificationcode`，覆盖 `/getCaptcha`、`/user/verifyCode`。
  - 按词匹配 `sms`、`otp`、`sendcode`、`getcode`、`checkcode`：路径按非字母字符切词，某个词恰好相等才算。`/api/sms/send`、`/send-otp`、`/user/getcode` 命中；`/smsTemplate/list`、`/footprint/list`、`/barcode/getcodeList` 不命中。
  - 动词组合：路径小写后含 `send`、`get`、`resend`、`check`、`verify`、`validate` 紧跟 `sms`、`otp`、`smscode`、`mobilecode`、`phonecode`、`emailcode`、`msgcode`，如 `/sendSms`、`/getSmsCode`、`/sendOtp`、`/sendEmailCode`。`/smsTemplate/list` 前面没有动词，不命中。
  - 令牌接口：路径先按驼峰拆词、小写，`-`、`_` 当作词间隔。动词 `get`、`refresh`、`renew`、`issue`、`exchange` 必须在词首，可接 `access`、`auth`、`id`、`session`、`csrf`、`user` 中的一个，再接 `token`；或者 `token` 在词首、后接 `exchange` / `refresh`。`/getToken`、`/refresh-token`、`/api/get_access_token`、`/getSessionToken`、`/tokenExchange`、`/token-refresh` 命中；`/forgetToken`、`/budgetTokenUsage`、`/target-token/list`、`/widget_token`、`/tokens/stats` 不命中。已知漏判：`/getJwt`；全小写、没有分隔的路径，如 `/apigettoken`、`/refreshtoken`（拆不出词）。
  - 已知误伤（代价只是少采一个响应体）：
    - 以令牌接口开头的普通接口：`/getTokenList`、`/getTokenizer`、`/order/getTokenFee`、`/getAuthTokenConfig`、`/tenant/getTokenStats`。
    - 含 `sms`、`otp` 这个词：`/sms-template/get`、`/otp-config/list`。
    - 含动词组合子串：`sendSmsNotice`、`budgetSmsCode`。
    - 含 `captcha`、`verifycode` 子串的配置类接口，如 `/captchaConfig`。
    - 以 `/password`、`/register`、`/forgot` 等片段开头的普通路径，如 `/passwordPolicy/list`、`/registerCenter`。
    - 段名恰好是 `login`、`token`、`sso`、`cas` 等的普通接口。
- **响应体里像令牌的 `code` / `ticket` 也替换**：这两个键在响应体里默认保留原值（`{"code":0}`、`{"code":"E1001"}`），但值像令牌时替换为 `***`：JWT 形态（三段 base64url，以 `eyJ` 开头），或长度 ≥16、只含字母、数字和 `. _ ~ + / = -`（base64、base64url、hex，以及 `4/0Ab…` 这类 Google 授权码、带点的令牌）且同时有字母和数字的字符串。只豁免大写下划线业务码（`^[A-Z][A-Z0-9]*(_[A-Z0-9]+)+$`，如 `INVALID_PARAMETER_VALUE`、`ORDER_20261021_0001`）。字符集另含 `%`，URL 编码后的令牌（如 `4%2F0Ab…`）也替换。已知漏判：纯数字或纯字母的令牌不替换。这样能覆盖 OAuth 授权码、CAS 票据在响应体里回显的情况。已知误伤（够长、同时有字母和数字时）：值是路径、文件名或域名的 `code` / `ticket`（如 `static/v2/app.js`）；URL 编码的业务文本（如 `ERR%20CODE%201001ab`）；小写连字符订单号或版本号（如 `order-2026-10-21-0001`、`2026.10.21-build.42`）。`sign`、`signature`、`otp` 仍按原规则只在 URL 里替换。
- collect 上报地址追加 `?app_key=`（网关/CDN 访问日志会出现 appKey；appKey 本就公开，非机密）。

### 修复

- **页面 URL 与 referrer 脱敏**：公共属性 `referrer`（`$pageview`、`$session_start` 等所有事件都带）、自动采集的链接 `href`、资源加载错误的 `resource_url`、回放 rrweb Meta 事件里的 `href`，此前都是原文，现在都经过 URL 敏感参数脱敏。`url_path` 本来就只有 pathname，不含 query 和 hash。
- **JS 错误的 `filename` 脱敏**：`$error` 的 `filename`（出错脚本地址）此前原样上报，CDN 地址里的 `?token=`、`?sign=` 会进到错误事件里，现在按 URL 敏感参数口径替换。
- **回放 DOM 里的地址脱敏**：rrweb 全量快照和增量快照（新增节点、属性变更）里的 `href`、`src`、`action`、`xlink:href`、`formaction`、`poster`、`data` 属性按 URL 敏感参数口径替换（属性名不分大小写）；`srcset`、`imagesrcset` 按 HTML 规范的候选解析（URL 里可以有逗号），逐个替换 URL、保留 `1x`、`480w` 等描述符，`data:` 候选单独跳过、同属性里其他候选照常替换。已知误伤：逗号后不带空白时（`a.jpg?token=1,b.jpg 2x`）按规范整段算一个 URL，命中的参数值连同后面的候选一起替换。CSS 里的 `url()`（`style` 属性、内联样式表）仍原样录制，页面上带 token 的链接、预签名图片地址不再原样进回放。rrweb 2.1.1 的 `record` 没有属性级钩子（`maskAttributeFn` 只在 Sentry 分叉里有），所以在 `emit` 时处理事件。
- **`maskSensitiveBody` 解析失败不再返回原文**：导出函数遇到非法 JSON 时整体返回 `***`。原文可能就是凭证（如 `token=...` 形式的文本）。上传器本来就丢弃这类响应体，行为不变。

- 错误堆栈清洗：① 帧 URL 去掉 query / hash（常带 token、签名），保留 `:行:列`，错误指纹也按去掉后的堆栈计算，同一错误不会因 token 不同被拆成多组；② props 总量超过 16KB 时先缩 `stack`（按 UTF-8 字节），不再让服务端从尾部摘掉其它属性，4096 个中文字符的堆栈约 12KB，加上其它属性很容易超限；③ 截断不再拆开 emoji 等代理对

- 回放收尾块丢失：pagehide 时原来把剩余缓冲（最多 10MB）合成一个明文块用 beacon 发出，超过 sendBeacon 的 64KB 限额或服务端单块上限（明文约 1.07MB）就整块丢失。现在：① 页面转后台（`visibilitychange → hidden`）时先把缓冲走 gzip 管道，以 beacon / fetch keepalive 发出，移动端切后台也能覆盖；② pagehide 剩余部分按 32KB 明文拆块；sendBeacon 与 fetch keepalive 共用每个文档约 64KB 的在途额度，pagehide 时普通事件的收尾 beacon 和仍在途的回放块也占这份额度，所以回放收尾块合计请求体不超过 44KB，第一块放不下即停止，丢弃更晚的事件并记日志（放不下的块先按字节估算，不做 base64 编码）；转后台块的 gzip 还没完成页面就卸载时，改为同步明文发出（沿用原 seq），压缩结果作废，不会重复发送；③ 普通切块也按 1MB 明文拆分，避免触发服务端的 413

- 错误堆栈：`sanitizeProps` 对顶层 `stack` 放宽到 4096 字符，与 error 插件的截断和服务端（mugsun-boot `PROPS_STACK_MAX_LEN`）一致。之前所有字符串一律截到 1024，`$error` 的堆栈实际只剩 1024 字符；其它字符串属性仍是 1024

- URL 敏感参数与响应体凭证键改用同一个键名归一（去掉 `-`、`_` 后小写，再精确匹配）。此前 URL 只做小写，`?accessToken=`、`?Refresh-Token=` 不会被识别；`tokenCount`、`passwordHint`、`sessionTimeout` 这类键依旧保留原值。

- 响应体只 `JSON.parse` 一次：插件判定可解析后把解析结果直接交给上传器脱敏，不再解析两遍。

- endpoint 末尾斜杠/空白统一归一，collect、config 与自检 ping 不再出现 `//track/...`

### 新增

- 会话回放默认每 3 分钟做一次全量快照（rrweb 内置 `checkoutEveryNms`），`replayPlugin({ checkoutEveryNms })` 可调整，传 `false` 关闭。中间某块丢失时，播放器可以从下一个全量快照接着播；代价是每 3 分钟多一份 DOM 快照的上传量（gzip 后通常几十 KB）
- `tracker.selfCheck()`：结构化接入自检（config / ping / sampling / consent / privacy / queue / replay / filters，每项 ok/warn/fail + message + fix），只真实请求一次 `GET /track/config?app_key=`，不发送用户数据。实现由 `createTracker` 注入，不进 core 入口
- `beforeSend(event)` 钩子（返回 null/false 丢弃；只合并返回的 props；抛错默认丢弃，`beforeSendOnError: 'keep'` 可改为发送原事件；不覆盖回放与接口响应体）、`ignoreErrors`（字符串/RegExp/谓词）、`skipHandledErrors` 开关（默认值见上方「行为变更」）
- `trackApiError({ url, method, status, bizCode, message, durationMs })`：手动上报 `api_request`（success=false, source=manual）；url 与 api-monitor 同口径脱敏敏感 query（`token` / `access_token` 等值替换为 `***`）后截断 512
- 服务端可凭 collect 地址上的 `app_key` 对解析失败/超限的请求归因（接入健康）

### 体积

- core.js gzip 5.48 → 6.33 KB（门禁 8 KB）；index.js gzip 14.99 → 18.06 KB；vue/index.js 9.94 → 13.28 KB

### 文档

- CONTRIBUTING 补充发版流程（改版本号 + CHANGELOG → 合入 main → release.yml 自动发布），中英双语

## [0.2.0] - 2026-10-13

### 变更

- api-monitor：上报 URL 剥离敏感 query（`token` / `access_token` / `authorization` / `id_token` / `refresh_token` 等，大小写不敏感，值替换为 `***`；业务参数保留）。与 [隐私与合规](https://docs.mugsun.com/track/privacy) 对齐；docs 站正文若仍写旧行为需另改 `mugsun-docs`

### 变更（行为 / Breaking）

- **回放默认遮罩页面文本**：`rrweb.record` 默认传入 `maskTextSelector: '*'`（此前仅 `maskAllInputs`）。调试可在 `replayPlugin({ maskTextSelector: false })` 显式关闭，或传入自定义选择器。
- **`apiBodyMaskEnabled` 默认改为 `true`**：开启响应体采集时，JSON body 按内置敏感键清单脱敏后再上传。依赖全文 body 的接入请显式设置 `apiBodyMaskEnabled: false`（或远端下发 `0`）。

### 迁移

1. 升级至 `0.2.0` 后，回放画面中的页面文本默认被遮罩；若需可读文本回放，在注册 replay 插件时传 `maskTextSelector: false`（或更窄的选择器）。
2. 若业务依赖 api-body 原文（含 password/token/phone 等字段），升级后须显式 `apiBodyMaskEnabled: false`，否则敏感键值会变为 `***`。
3. 已于 2026-10-13 经 release 工作流（npm Trusted Publishing）发布至 npm。

### 说明

- URL 敏感 query 剥离来自 #2（T1），已合入 main。
- 隐私页源码在 `mugsun-docs`；本仓 README/CHANGELOG 已对齐 docs.mugsun.com/track/privacy 承诺。

## [0.1.1] - 2026-10-12

相对 npm 已发布的 `0.1.0`，main tip 含以下未发包变更；本版本对齐 `package.json` / `SDK_VERSION`，**尚未**执行 `npm publish`（需维护者令牌）。

### 新增

- `geo` 可选定位插件：每会话采集一次，支持配置透传；默认不进入 `defaultPlugins`
- 圈选埋点：草稿提交失败时展示服务端说明；事件名不合法时提示仅可用字母、数字与下划线

### 变更

- 包元数据仓库地址改为 `mugsun/mugsun-track`（npm `0.1.0` 仍指向旧 `curdx/mugsun-track`）
- README / 贡献指南与架构说明更新（文档向，不影响运行时）

### 说明

- 尚未打 GitHub Release / git tag；发布前以本仓 CI（typecheck / test / build）为准

## [0.1.0] - 2026-08-19

### 新增

- `@mugsun/track-web` `0.1.0`：嵌入式采集 SDK（core、默认插件、Vue 集成、replay 独立入口）
- 与 `mugsun-boot` track 模块、看板路径的对接说明见 README

### 说明

- 已发布至 npm；当时无 GitHub Release tag

[Unreleased]: https://github.com/mugsun/mugsun-track/commits/main
[0.2.0]: https://github.com/mugsun/mugsun-track/compare/3a36902...HEAD
[0.1.1]: https://github.com/mugsun/mugsun-track/compare/c20fa8b...3a36902
[0.1.0]: https://github.com/mugsun/mugsun-track/commits/main?since=2026-08-01&until=2026-08-20
