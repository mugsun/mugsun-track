#!/usr/bin/env python3
"""osv-scanner 结果门禁（清单 3.1）。

用法：osv-gate.py <osv-scanner --format json 输出> [osv-scanner.toml]
- Critical/High（CVSS >= 7.0，或没有评分）且有修复版本：失败。
- High 但没有修复版本：告警，提示写进 osv-scanner.toml 并找安全官审。
- Medium 及以下：只告警。
- osv-scanner.toml 的每条 [[IgnoredVulns]] 必须有 reason 和 ignoreUntil，
  ignoreUntil 不能超过今天起 90 天；过期由 osv-scanner 自动失效，这里也报错。
"""
import datetime as dt
import json
import pathlib
import sys
import tomllib

HIGH = 7.0
MAX_IGNORE_DAYS = 90


def sev(group):
    try:
        return float(group.get("max_severity") or "nan")
    except ValueError:
        return float("nan")


def has_fix(vulns, ids, name):
    for v in vulns:
        if v.get("id") not in ids and not set(v.get("aliases", [])) & set(ids):
            continue
        for aff in v.get("affected", []):
            if aff.get("package", {}).get("name") != name:
                continue
            for r in aff.get("ranges", []):
                if any("fixed" in e for e in r.get("events", [])):
                    return True
    return False


def check_ignores(path):
    errs = []
    p = pathlib.Path(path)
    if not p.exists():
        return errs
    today = dt.datetime.now(dt.timezone.utc)
    for item in tomllib.loads(p.read_text(encoding="utf-8")).get("IgnoredVulns", []):
        vid = item.get("id", "?")
        if not str(item.get("reason", "")).strip():
            errs.append(f"{p}: {vid} 缺少 reason")
        until = item.get("ignoreUntil")
        if until is None:
            errs.append(f"{p}: {vid} 缺少 ignoreUntil")
            continue
        if isinstance(until, dt.date) and not isinstance(until, dt.datetime):
            until = dt.datetime.combine(until, dt.time(), dt.timezone.utc)
        if until.tzinfo is None:
            until = until.replace(tzinfo=dt.timezone.utc)
        if until < today:
            errs.append(f"{p}: {vid} 已于 {until.date()} 过期")
        elif (until - today).days > MAX_IGNORE_DAYS:
            errs.append(f"{p}: {vid} 的 ignoreUntil 超过 {MAX_IGNORE_DAYS} 天")
    return errs


def main():
    data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
    fail, warn = [], []
    for res in data.get("results") or []:
        for pkg in res.get("packages") or []:
            name = pkg["package"]["name"]
            ver = pkg["package"].get("version", "?")
            for g in pkg.get("groups") or []:
                s = sev(g)
                ids = g.get("ids", [])
                label = f"{name}@{ver} {','.join(ids)} (CVSS {g.get('max_severity') or '无'})"
                high = s != s or s >= HIGH  # nan（无评分）按 High 处理
                if high and has_fix(pkg.get("vulnerabilities", []), ids, name):
                    fail.append(label + " 有修复版本，需升级")
                elif high:
                    warn.append(label + " 无修复版本，写进 osv-scanner.toml 并找安全官审")
                else:
                    warn.append(label)
    errs = check_ignores(sys.argv[2] if len(sys.argv) > 2 else "osv-scanner.toml")
    for w in warn:
        print(f"::warning::{w}")
    for e in fail + errs:
        print(f"::error::{e}")
    print(f"osv gate: {len(fail)} blocking, {len(warn)} warning, {len(errs)} ignore-file error")
    return 1 if fail or errs else 0


if __name__ == "__main__":
    sys.exit(main())
