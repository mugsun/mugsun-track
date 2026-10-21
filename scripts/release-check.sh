#!/usr/bin/env bash
# 发版前检查（release.yml 调用）。输出 skip=true|false 到 $GITHUB_OUTPUT（未设置时只打印）。
# - npm view <pkg>@<ver> 成功且返回该版本 → 已发布，skip=true
# - 只有 E404 / 404 才算「未发布」；网络、鉴权、5xx 等其他错误一律让 job 失败
# - 未发布时要求 package.json 版本严格大于 npm 上的 latest（semver 比较），否则失败
# NPM 环境变量可替换 npm 命令（本地用 mock 测试）
set -euo pipefail

NPM_BIN="${NPM:-npm}"
OUT="${GITHUB_OUTPUT:-/dev/stdout}"
NAME=$(node -p "require('./package.json').name")
VER=$(node -p "require('./package.json').version")

is_404() { grep -Eq '(^|[^0-9])E404([^0-9]|$)|npm (error|ERR!) 404' <<<"$1"; }

set +e
OUT_VER=$("$NPM_BIN" view "$NAME@$VER" version 2>&1)
RC=$?
set -e

if [ "$RC" -eq 0 ] && [ "$(printf '%s' "$OUT_VER" | tr -d '[:space:]')" = "$VER" ]; then
  echo "skip=true" >> "$OUT"
  echo "$NAME@$VER already on npm"
  exit 0
fi
if [ "$RC" -eq 0 ] || ! is_404 "$OUT_VER"; then
  echo "::error::npm view $NAME@$VER failed or returned unexpected output (rc=$RC); not treating as unpublished"
  printf '%s\n' "$OUT_VER" >&2
  exit 1
fi

# 未发布：和 latest 比较
set +e
LATEST=$("$NPM_BIN" view "$NAME" version 2>&1)
RC=$?
set -e
if [ "$RC" -ne 0 ]; then
  if is_404 "$LATEST"; then
    LATEST=""
  else
    echo "::error::npm view $NAME version failed (rc=$RC)"
    printf '%s\n' "$LATEST" >&2
    exit 1
  fi
fi
LATEST=$(printf '%s' "$LATEST" | tr -d '[:space:]')

if [ -n "$LATEST" ]; then
  # semver 比较（含预发布标识，按 semver 2.0 规则）；VER > LATEST 时退出 0
  if ! node -e '
    const parse = (v) => {
      const m = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/.exec(v)
      if (!m) throw new Error("not semver: " + v)
      return { core: [+m[1], +m[2], +m[3]], pre: m[4] ? m[4].split(".") : [] }
    }
    const cmp = (a, b) => {
      for (let i = 0; i < 3; i++) if (a.core[i] !== b.core[i]) return a.core[i] - b.core[i]
      if (!a.pre.length || !b.pre.length) return b.pre.length - a.pre.length
      for (let i = 0; i < Math.max(a.pre.length, b.pre.length); i++) {
        const x = a.pre[i], y = b.pre[i]
        if (x === undefined) return -1
        if (y === undefined) return 1
        const nx = /^\d+$/.test(x), ny = /^\d+$/.test(y)
        if (nx && ny) { if (+x !== +y) return +x - +y; continue }
        if (nx !== ny) return nx ? -1 : 1
        if (x !== y) return x < y ? -1 : 1
      }
      return 0
    }
    process.exit(cmp(parse(process.argv[1]), parse(process.argv[2])) > 0 ? 0 : 1)
  ' "$VER" "$LATEST"; then
    echo "::error::package.json version $VER is not greater than npm latest $LATEST"
    exit 1
  fi
fi

echo "skip=false" >> "$OUT"
echo "Will publish $NAME@$VER (npm latest: ${LATEST:-none})"
