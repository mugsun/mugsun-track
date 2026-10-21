#!/usr/bin/env python3
"""osv-scanner 门禁（清单 3.1）。两个子命令：

1) 扫描前校验忽略列表，并生成给 osv-scanner 用的配置：
     osv-gate.py config osv-scanner.toml --effective <输出.toml>
   osv-scanner.toml 每条 [[IgnoredVulns]] 必须有：
     id、reason、added（登记日期）、ignoreUntil（不早于今天，且不超过 added 起 90 天）
   日期要写 TOML 原生日期（不加引号）；写成字符串或格式不对，给出明确报错。
   osv-scanner 不认 added 这个键（会报 unknown keys），所以输出一份去掉 added 的
   等价配置给 --config 用；忽略的条目和期限与 osv-scanner.toml 完全一致。

2) 扫描后判定结果：
     osv-gate.py results <osv.json> --exit-code <osv-scanner 退出码>
   - 退出码不是 0/1（工具出错）：失败。
   - JSON 读不了、results 缺失 / null / 不是列表、出现 error 字段：失败。
   - 退出码 1 但没有任何漏洞记录（JSON 不完整）、退出码 0 却有漏洞记录：失败。
   - High/Critical（CVSS >= 7.0，或没有评分）：一律失败。已登记在 osv-scanner.toml
     的条目 osv-scanner 已经滤掉，能走到这里的都是未登记的。
   - Medium/Low：告警，并说明修复版本情况：
     「有修复版本，可在现有范围内升级」「修复版本超出依赖范围」「无修复版本」。
     「范围」按 npm ^ 语义近似：1.x 以上看主版本，0.x 看次版本。
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import tomllib

HIGH = 7.0
MAX_IGNORE_DAYS = 90
REQUIRED = ("id", "reason", "added", "ignoreUntil")


# ---------- config ----------

def to_date(value, field, vid):
    """TOML 原生 date / datetime -> date；字符串等其他类型返回 (None, 报错)。"""
    if isinstance(value, dt.datetime):
        return value.date(), None
    if isinstance(value, dt.date):
        return value, None
    if isinstance(value, str):
        hint = "（日期不要加引号，例如 2026-10-21）" if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}(T.*)?", value) else "（应为 YYYY-MM-DD，不加引号）"
        return None, f"{vid}: {field} 写成了字符串 {value!r}{hint}"
    return None, f"{vid}: {field} 类型不对（{type(value).__name__}），应为日期 YYYY-MM-DD"


def check_config(path, today=None):
    """返回 (errors, entries)。entries 用于生成 effective 配置。"""
    today = today or dt.date.today()
    p = pathlib.Path(path)
    if not p.exists():
        return [f"{p}: 文件不存在"], []
    try:
        data = tomllib.loads(p.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        return [f"{p}: TOML 解析失败：{e}"], []
    errs, entries = [], []
    unknown = set(data) - {"IgnoredVulns"}
    if unknown:
        errs.append(f"{p}: 只支持 [[IgnoredVulns]]，多出了 {sorted(unknown)}")
    items = data.get("IgnoredVulns", [])
    if not isinstance(items, list):
        return errs + [f"{p}: IgnoredVulns 必须写成 [[IgnoredVulns]] 数组"], []
    for n, item in enumerate(items, 1):
        vid = str(item.get("id") or f"第 {n} 条")
        missing = [k for k in REQUIRED if k not in item or item[k] in ("", None)]
        if missing:
            errs.append(f"{p}: {vid} 缺少 {', '.join(missing)}")
            continue
        extra = set(item) - set(REQUIRED)
        if extra:
            errs.append(f"{p}: {vid} 有不认识的键 {sorted(extra)}")
        if not str(item["reason"]).strip():
            errs.append(f"{p}: {vid} reason 不能为空")
        added, e1 = to_date(item["added"], "added", vid)
        until, e2 = to_date(item["ignoreUntil"], "ignoreUntil", vid)
        for e in (e1, e2):
            if e:
                errs.append(f"{p}: {e}")
        if added is None or until is None:
            continue
        if added > today:
            errs.append(f"{p}: {vid} added {added} 晚于今天")
        if until < today:
            errs.append(f"{p}: {vid} 已于 {until} 过期")
        if until < added:
            errs.append(f"{p}: {vid} ignoreUntil {until} 早于 added {added}")
        elif (until - added).days > MAX_IGNORE_DAYS:
            errs.append(f"{p}: {vid} ignoreUntil 距 added 超过 {MAX_IGNORE_DAYS} 天"
                        f"（{added} → {until}，{(until - added).days} 天）")
        entries.append({"id": item["id"], "until": until, "reason": str(item["reason"])})
    return errs, entries


def write_effective(entries, out):
    lines = ["# 由 scripts/osv-gate.py 从 osv-scanner.toml 生成（去掉 added），不要手改", ""]
    for e in entries:
        lines += ["[[IgnoredVulns]]",
                  f"id = {json.dumps(e['id'])}",
                  f"ignoreUntil = {e['until'].isoformat()}T00:00:00Z",
                  f"reason = {json.dumps(e['reason'], ensure_ascii=False)}", ""]
    pathlib.Path(out).write_text("\n".join(lines), encoding="utf-8")


# ---------- results ----------

def parse_ver(v):
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", v or "")
    return tuple(int(x) for x in m.groups()) if m else None


def same_caret_range(cur, fix):
    if cur[0] > 0:
        return fix[0] == cur[0]
    return fix[:2] == cur[:2]


def fix_status(pkg, ids):
    """返回 (类别, 说明)：in_range / out_of_range / none。"""
    name, cur = pkg["package"]["name"], parse_ver(pkg["package"].get("version"))
    fixes = []
    for v in pkg.get("vulnerabilities") or []:
        if v.get("id") not in ids and not set(v.get("aliases") or []) & set(ids):
            continue
        for aff in v.get("affected") or []:
            if (aff.get("package") or {}).get("name") != name:
                continue
            for r in aff.get("ranges") or []:
                for ev in r.get("events") or []:
                    fv = parse_ver(ev.get("fixed"))
                    if fv and (cur is None or fv > cur):
                        fixes.append((fv, ev["fixed"]))
    if not fixes:
        return "none", "无修复版本"
    fixes.sort()
    if cur and any(same_caret_range(cur, f) for f, _ in fixes):
        best = next(s for f, s in fixes if same_caret_range(cur, f))
        return "in_range", f"有修复版本 {best}，可在现有范围内升级"
    return "out_of_range", f"修复版本超出依赖范围（修复于 {fixes[0][1]}）"


def severity(group):
    try:
        return float(group.get("max_severity") or "nan")
    except (TypeError, ValueError):
        return float("nan")


def check_results(path, exit_code):
    errs, warn = [], []
    if exit_code not in (0, 1):
        return [f"osv-scanner 退出码 {exit_code}，工具出错"], warn
    try:
        data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [f"读不了 osv-scanner 输出 {path}：{e}"], warn
    if not isinstance(data, dict):
        return ["osv-scanner 输出不是 JSON 对象"], warn
    if "error" in data:
        return [f"osv-scanner 输出含 error 字段：{data['error']}"], warn
    results = data.get("results", "<missing>")
    if results == "<missing>":
        return ["osv-scanner 输出缺少 results"], warn
    if not isinstance(results, list):
        return [f"osv-scanner 输出的 results 不是列表（{type(results).__name__}）"], warn
    groups = 0
    for res in results:
        if not isinstance(res, dict) or "error" in res:
            return [f"results 条目异常：{res!r}"[:300]], warn
        for pkg in res.get("packages") or []:
            if not isinstance(pkg, dict) or "error" in pkg or \
                    not (pkg.get("package") or {}).get("name"):
                return [f"packages 条目异常：{pkg!r}"[:300]], warn
            for g in pkg.get("groups") or []:
                groups += 1
                ids = g.get("ids") or []
                p = pkg["package"]
                label = f"{p['name']}@{p.get('version', '?')} {','.join(ids)} " \
                        f"(CVSS {g.get('max_severity') or '无'})"
                kind, note = fix_status(pkg, ids)
                s = severity(g)
                if s != s or s >= HIGH:
                    tail = "未登记在 osv-scanner.toml" if kind == "none" else "需升级"
                    errs.append(f"{label} {note}，{tail}")
                else:
                    warn.append(f"{label} {note}")
    if exit_code == 1 and groups == 0:
        errs.append("osv-scanner 退出码 1 但输出里没有漏洞记录，JSON 不完整")
    if exit_code == 0 and groups > 0:
        errs.append(f"osv-scanner 退出码 0 但输出里有 {groups} 组漏洞，结果不一致")
    return errs, warn


def report(errs, warn, what):
    for w in warn:
        print(f"::warning::{w}")
    for e in errs:
        print(f"::error::{e}")
    print(f"osv gate ({what}): {len(errs)} error, {len(warn)} warning")
    return 1 if errs else 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("config")
    c.add_argument("toml")
    c.add_argument("--effective", required=True)
    r = sub.add_parser("results")
    r.add_argument("json")
    r.add_argument("--exit-code", type=int, required=True)
    a = ap.parse_args(argv)
    if a.cmd == "config":
        errs, entries = check_config(a.toml)
        if not errs:
            write_effective(entries, a.effective)
        return report(errs, [], "config")
    errs, warn = check_results(a.json, a.exit_code)
    return report(errs, warn, "results")


if __name__ == "__main__":
    sys.exit(main())
