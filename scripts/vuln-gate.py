#!/usr/bin/env python3
# ============================================================================
#  vuln-gate.py  共享漏洞门禁  版本 1.1.0
#  共享文件，禁止各仓单独修改。
#  源头：mugsun CI 清单 3.11 / 3.13；改动先改共享副本、过安全官审，
#  再同步到各仓并更新各仓的 scripts/vuln-gate.sha256。
# ============================================================================
"""共享漏洞门禁：osv-scanner / pnpm audit / npm audit 的 JSON 结果统一判定。

子命令
  config <osv-scanner.toml> --effective <out.toml>
      校验忽略列表，并写出 osv-scanner 认的配置（去掉 added）。
  results --format {osv,pnpm-audit,npm-audit} --exit-code N
          [--ignores osv-scanner.toml] [--require-packages] <report.json>
      判定扫描结果。

忽略列表（osv-scanner.toml 的 [[IgnoredVulns]]）
  - 每条必须是表，且只有 id、scope、reason、added、ignoreUntil 五个键，缺一不可。
  - scope 必填，只能是 "prod"（生产依赖，最长 30 天）或 "dev"（开发依赖，最长 90 天）。
  - id 必须是单个字符串，格式为 GHSA-xxxx-xxxx-xxxx 或 CVE-YYYY-NNNN（安全官 F2）。
  - added、ignoreUntil 写 TOML 原生日期（不加引号）；字符串或格式不对给出明确报错。
  - ignoreUntil 距 added 不超过 scope 对应的天数（prod 30、dev 90）；不得早于 added；added 不得晚于今天。
  - 日期一律按 UTC：ignoreUntil 当天 23:59:59Z 前有效；「今天」取 UTC 日期
    （北京时间 08:00 前仍算前一天）。生成的配置写 ignoreUntil = <日期>T23:59:59Z。
  - osv-scanner 不认 added、scope 键，所以 --config 用 config 子命令生成的文件。

结果判定（任何一条命中都返回 1）
  - 退出码不是 0/1：工具出错。
  - 输出读不了、为空、不是 JSON 对象、出现 error / errors 字段（含 null）。
  - 结构字段缺失、为 null 或类型不对（osv 的 results / packages / groups；
    audit 的 advisories / vulnerabilities / metadata）。osv 的包没有漏洞时
    groups 和 vulnerabilities 两个键都不出现（2.7.0 --all-packages 实测）；
    只出现其中一个判失败。
  - osv 里没被任何 group 引用的漏洞单独算一条发现，照样参与判定。
  - 退出码 1 却没有漏洞记录（JSON 不完整）；退出码 0 却有 High/Critical 或
    （osv）有任何漏洞记录（结果不一致）。
  - --require-packages：扫到的包数为 0（防止覆盖率为 0 的假绿，清单 3.14）。
    osv 必须带 --all-packages 扫描，否则没有漏洞的包不会出现在输出里。
  - 严重度 >= 7.0（High/Critical）。不论有无修复版本：没有修复的应登记忽略条目，
    osv-scanner 会先滤掉，audit 格式由本脚本按 --ignores 滤掉。
  - 严重度无法判定：按 High 处理（清单 3.13）。

严重度
  取所有来源里的最高分：osv 的 max_severity、各漏洞 severity[] 里的 CVSS 向量
  （v2、v3.0、v3.1 按官方公式本地计算基础分）、database_specific.severity 等
  文字等级（大小写不敏感：critical 9.0 / high 7.0 / moderate|medium 4.0 /
  low 0.1 / info|none 0.0）、audit 条目的 severity 与 cvss.score / vectorString。
  来源缺失或为空串不计。来源有值但不合法（NaN / Inf / 超出 0~10 / -0.0、
  非字符串等级、认不出的等级、解析不了的向量、CVSS v4 向量）一律按 10.0
  参与取最高值，不会被同条目里更低的等级压下去（安全官 S3、S4）。
  CVSS v4 不在本地计算（官方算法依赖宏向量查表，不引入第三方库），所以也按 10.0。
  一个来源都没有时按 High 处理。
  npm audit 的 cvss.score 为 0 也算一个来源（0 分）。

告警（Medium/Low，不阻塞）注明修复情况：
  「有修复版本 X，可在现有范围内升级」「修复版本超出依赖范围（修复于 X）」「无修复版本」
  「范围」按 npm ^ 语义近似：1.x 以上看主版本，0.x 看次版本。
"""
import argparse
import datetime as dt
import json
import math
import pathlib
import re
import sys
import tomllib

__version__ = "1.1.0"

HIGH = 7.0
MAX_IGNORE_DAYS = {"prod": 30, "dev": 90}
REQUIRED = ("id", "scope", "reason", "added", "ignoreUntil")
ID_RE = re.compile(r"^(GHSA(-[23456789cfghjmpqrvwx]{4}){3}|CVE-\d{4}-\d{4,})$")
LABELS = {"critical": 9.0, "high": 7.0, "moderate": 4.0, "medium": 4.0,
          "low": 0.1, "info": 0.0, "none": 0.0}


class Invalid(float):
    """有值但不合法的严重度来源，按 10.0 计。"""


INVALID = Invalid(10.0)


class GateError(Exception):
    """结构或工具层面的错误，直接判失败。"""


# ============================== CVSS ==============================

def _roundup31(x):
    i = round(x * 100000)
    return i / 100000.0 if i % 10000 == 0 else (math.floor(i / 10000) + 1) / 10.0


def _roundup30(x):
    # 与 3.1 相同的整数化写法，避免 ceil 直接作用在浮点误差上
    i = round(x * 100000)
    return -(-i // 10000) / 10.0


_V3 = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "UI": {"N": 0.85, "R": 0.62},
    "C": {"H": 0.56, "L": 0.22, "N": 0.0},
    "I": {"H": 0.56, "L": 0.22, "N": 0.0},
    "A": {"H": 0.56, "L": 0.22, "N": 0.0},
}


def cvss3_base(vector):
    """CVSS v3.0 / v3.1 基础分（官方规范公式）；向量不合法返回 None。"""
    parts = vector.strip().split("/")
    m = re.fullmatch(r"CVSS:3\.([01])", parts[0])
    if not m:
        return None
    metrics = {}
    for p in parts[1:]:
        if ":" not in p:
            return None
        k, v = p.split(":", 1)
        if k in metrics:
            return None
        metrics[k] = v
    try:
        s = metrics["S"]
        if s not in ("U", "C"):
            return None
        pr = {"N": 0.85, "L": 0.68 if s == "C" else 0.62,
              "H": 0.5 if s == "C" else 0.27}[metrics["PR"]]
        av, ac, ui = (_V3[k][metrics[k]] for k in ("AV", "AC", "UI"))
        c, i, a = (_V3[k][metrics[k]] for k in ("C", "I", "A"))
    except KeyError:
        return None
    iss = 1 - (1 - c) * (1 - i) * (1 - a)
    impact = 6.42 * iss if s == "U" else 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15
    if impact <= 0:
        return 0.0
    expl = 8.22 * av * ac * pr * ui
    raw = impact + expl if s == "U" else 1.08 * (impact + expl)
    up = _roundup31 if m.group(1) == "1" else _roundup30
    return up(min(raw, 10))


_V2 = {
    "AV": {"L": 0.395, "A": 0.646, "N": 1.0},
    "AC": {"H": 0.35, "M": 0.61, "L": 0.71},
    "Au": {"M": 0.45, "S": 0.56, "N": 0.704},
    "C": {"N": 0.0, "P": 0.275, "C": 0.660},
    "I": {"N": 0.0, "P": 0.275, "C": 0.660},
    "A": {"N": 0.0, "P": 0.275, "C": 0.660},
}


def cvss2_base(vector):
    """CVSS v2 基础分；向量不合法返回 None。"""
    v = vector.strip().strip("()")
    if v.startswith("CVSS:2.0/"):
        v = v[len("CVSS:2.0/"):]
    metrics = {}
    for p in v.split("/"):
        if ":" not in p:
            return None
        k, val = p.split(":", 1)
        metrics[k] = val
    try:
        av, ac, au, c, i, a = (_V2[k][metrics[k]] for k in ("AV", "AC", "Au", "C", "I", "A"))
    except KeyError:
        return None
    impact = 10.41 * (1 - (1 - c) * (1 - i) * (1 - a))
    expl = 20 * av * ac * au
    f = 0 if impact == 0 else 1.176
    return round(((0.6 * impact) + (0.4 * expl) - 1.5) * f + 1e-9, 1)


def _missing(x):
    return x is None or (isinstance(x, str) and not x.strip())


def score_vector(vector):
    """CVSS 向量或数值字符串 -> 分数。缺失或空返回 None；
    有值但算不出（含 v4）返回 INVALID（10.0）。"""
    if _missing(vector):
        return None
    if not isinstance(vector, str):
        return INVALID
    v = vector.strip()
    if v.startswith("CVSS:3."):
        s = cvss3_base(v)
    elif v.startswith("CVSS:4."):
        s = None
    elif "AV:" in v and "Au:" in v:
        s = cvss2_base(v)
    else:
        return finite(v)
    return INVALID if s is None else s


def finite(x):
    """数值或数值字符串 -> 0~10 的 float。缺失或空串返回 None；
    有值但不合法（布尔、其他类型、解析不了、NaN / Inf、超范围、-0.0）返回 INVALID。"""
    if _missing(x):
        return None
    if isinstance(x, bool) or not isinstance(x, (int, float, str)):
        return INVALID
    try:
        val = float(x.strip() if isinstance(x, str) else x)
    except ValueError:
        return INVALID
    if not math.isfinite(val) or not 0.0 <= val <= 10.0 or math.copysign(1.0, val) < 0:
        return INVALID
    return val


def label_score(label):
    """文字等级 -> 分数。缺失或空返回 None；非字符串或认不出返回 INVALID。"""
    if _missing(label):
        return None
    if not isinstance(label, str):
        return INVALID
    return LABELS.get(label.strip().lower(), INVALID)


def best_score(sources):
    """sources: [(描述, 分数或 None)]；返回 (最高分或 None, 说明)。"""
    valid = [(s, d) for d, s in sources if s is not None]
    if not valid:
        return None, "无法判定严重度（按 High 处理）"
    s, d = max(valid, key=lambda t: (t[0], isinstance(t[0], Invalid)))
    if isinstance(s, Invalid):
        return float(s), f"严重度来源不合法，按 10.0 计（{d}）"
    return float(s), f"严重度 {s:.1f}（{d}）"


# ============================ 版本 / 修复 ============================

def parse_ver(v):
    m = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", v or "") if isinstance(v, str) else None
    return tuple(int(x) for x in m.groups()) if m else None


def same_caret_range(cur, fix):
    return fix[0] == cur[0] if cur[0] > 0 else fix[:2] == cur[:2]


def describe_fix(cur_s, fixed_list):
    cur = parse_ver(cur_s)
    fixes = sorted({(f, s) for s in fixed_list for f in [parse_ver(s)]
                    if f and (cur is None or f > cur)})
    if not fixes:
        return "无修复版本"
    if cur and any(same_caret_range(cur, f) for f, _ in fixes):
        best = next(s for f, s in fixes if same_caret_range(cur, f))
        return f"有修复版本 {best}，可在现有范围内升级"
    return f"修复版本超出依赖范围（修复于 {fixes[0][1]}）"


# ============================== 忽略列表 ==============================

def to_date(value, field, vid):
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            value = value.astimezone(dt.timezone.utc)
        return value.date(), None
    if isinstance(value, dt.date):
        return value, None
    if isinstance(value, str):
        hint = "（日期不要加引号，例如 2026-10-21）" if re.fullmatch(
            r"\d{4}-\d{2}-\d{2}(T.*)?", value) else "（应为 YYYY-MM-DD，不加引号）"
        return None, f"{vid}: {field} 写成了字符串 {value!r}{hint}"
    return None, f"{vid}: {field} 类型不对（{type(value).__name__}），应为日期 YYYY-MM-DD"


def utc_today():
    return dt.datetime.now(dt.timezone.utc).date()


def check_config(path, today=None):
    """返回 (errors, entries)。entries: [{id, until, reason}]。"""
    today = today or utc_today()
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
    seen = set()
    for n, item in enumerate(items, 1):
        if not isinstance(item, dict):
            errs.append(f"{p}: 第 {n} 条 IgnoredVulns 不是表（{type(item).__name__}），"
                        "应写成 [[IgnoredVulns]] 加 id = ... 等键")
            continue
        raw_id = item.get("id")
        vid = raw_id if isinstance(raw_id, str) and raw_id else f"第 {n} 条"
        missing = [k for k in REQUIRED if k not in item or item[k] in ("", None)]
        if missing:
            errs.append(f"{p}: {vid} 缺少 {', '.join(missing)}")
            continue
        if not isinstance(raw_id, str):
            errs.append(f"{p}: 第 {n} 条 id 必须是单个字符串，现在是 {type(raw_id).__name__}")
            continue
        if not ID_RE.fullmatch(raw_id):
            errs.append(f"{p}: {raw_id!r} 不是 GHSA-xxxx-xxxx-xxxx 或 CVE-YYYY-NNNN 格式")
            continue
        if raw_id in seen:
            errs.append(f"{p}: {raw_id} 重复登记")
        seen.add(raw_id)
        extra = set(item) - set(REQUIRED)
        if extra:
            errs.append(f"{p}: {vid} 有不认识的键 {sorted(extra)}")
        scope = item["scope"]
        if not isinstance(scope, str) or scope not in MAX_IGNORE_DAYS:
            errs.append(f"{p}: {vid} scope 只能是 \"prod\" 或 \"dev\"，现在是 {scope!r}")
            continue
        limit = MAX_IGNORE_DAYS[scope]
        if not isinstance(item["reason"], str) or not item["reason"].strip():
            errs.append(f"{p}: {vid} reason 必须是非空字符串")
        added, e1 = to_date(item["added"], "added", vid)
        until, e2 = to_date(item["ignoreUntil"], "ignoreUntil", vid)
        for e in (e1, e2):
            if e:
                errs.append(f"{p}: {e}")
        if added is None or until is None:
            continue
        if added > today:
            errs.append(f"{p}: {vid} added {added} 晚于今天（UTC {today}）")
        if until < today:  # until 当天 23:59:59Z 仍有效
            errs.append(f"{p}: {vid} 已于 {until} 23:59:59Z（UTC）过期")
        if until < added:
            errs.append(f"{p}: {vid} ignoreUntil {until} 早于 added {added}")
        elif (until - added).days > limit:
            errs.append(f"{p}: {vid} ignoreUntil 距 added 超过 {limit} 天（scope = {scope}）"
                        f"（{added} → {until}，{(until - added).days} 天）")
        entries.append({"id": raw_id, "until": until, "reason": str(item["reason"])})
    return errs, entries


def write_effective(entries, out):
    lines = ["# 由 vuln-gate.py 从 osv-scanner.toml 生成（去掉 added、scope），不要手改", ""]
    for e in entries:
        lines += ["[[IgnoredVulns]]",
                  f"id = {json.dumps(e['id'])}",
                  f"ignoreUntil = {e['until'].isoformat()}T23:59:59Z",  # 按 UTC，与到期判断一致
                  f"reason = {json.dumps(e['reason'], ensure_ascii=False)}", ""]
    pathlib.Path(out).write_text("\n".join(lines), encoding="utf-8")


# ============================== 读取 ==============================

def load_json(path):
    try:
        raw = pathlib.Path(path).read_text(encoding="utf-8")
    except OSError as e:
        raise GateError(f"读不了扫描结果 {path}：{e}") from e
    if not raw.strip():
        raise GateError("扫描结果为空")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise GateError(f"扫描结果不是合法 JSON：{e}") from e
    if not isinstance(data, dict):
        raise GateError("扫描结果不是 JSON 对象")
    for k in ("error", "errors"):
        if k in data:
            raise GateError(f"扫描结果含 {k} 字段（{str(data[k])[:200]}），工具出错")
    return data


def need(obj, key, typ, where):
    if not isinstance(obj, dict) or key not in obj:
        raise GateError(f"{where}: 缺少 {key}")
    val = obj[key]
    if not isinstance(val, typ) or isinstance(val, bool):
        raise GateError(f"{where}: {key} 类型不对（{type(val).__name__}）")
    return val


def _vkeys(v):
    return {v["id"]} | {a for a in (v.get("aliases") or []) if isinstance(a, str)}


def _vuln_sources(v, name, sources, fixed):
    for sev in v.get("severity") or []:
        if isinstance(sev, dict):
            sources.append((f"{v['id']} {sev.get('type', '?')}",
                            score_vector(sev.get("score"))))
    db = v.get("database_specific")
    if isinstance(db, dict):
        sources.append((f"{v['id']} 等级 {db.get('severity')}",
                        label_score(db.get("severity"))))
    for aff in v.get("affected") or []:
        if not isinstance(aff, dict):
            continue
        if (aff.get("package") or {}).get("name") not in (None, name):
            continue
        for r in aff.get("ranges") or []:
            for ev in (r.get("events") or []) if isinstance(r, dict) else []:
                if isinstance(ev, dict) and isinstance(ev.get("fixed"), str):
                    fixed.append(ev["fixed"])


# 每条发现：dict(name, version, ids, sources, fixed, fix_note[, unignorable])
def findings_osv(data):
    results = need(data, "results", list, "osv 输出")
    found, packages = [], 0
    for i, res in enumerate(results):
        w = f"results[{i}]"
        if not isinstance(res, dict) or "error" in res:
            raise GateError(f"{w} 条目异常")
        for j, pkg in enumerate(need(res, "packages", list, w)):
            wp = f"{w}.packages[{j}]"
            if not isinstance(pkg, dict) or "error" in pkg:
                raise GateError(f"{wp} 条目异常")
            info = pkg.get("package")
            if not isinstance(info, dict) or not isinstance(info.get("name"), str) \
                    or not info["name"]:
                raise GateError(f"{wp}: package.name 缺失")
            packages += 1
            has_g, has_v = "groups" in pkg, "vulnerabilities" in pkg
            if has_g != has_v:
                raise GateError(f"{wp}: 只有 {'groups' if has_g else 'vulnerabilities'}，"
                                "osv 输出不完整")
            if not has_g:
                continue  # 2.7.0 --all-packages：没有漏洞的包两个键都不出现
            groups = need(pkg, "groups", list, wp)
            vulns = need(pkg, "vulnerabilities", list, wp)
            if any(not isinstance(v, dict) or not isinstance(v.get("id"), str) for v in vulns):
                raise GateError(f"{wp}: vulnerabilities 条目类型不对")
            if vulns and not groups:
                raise GateError(f"{wp}: 有漏洞但缺少 groups")
            used = set()
            for g in groups:
                ids = g.get("ids") if isinstance(g, dict) else None
                if not isinstance(ids, list) or not ids or \
                        not all(isinstance(x, str) for x in ids):
                    raise GateError(f"{wp}: groups 条目缺少 ids")
                aliases = g.get("aliases") if isinstance(g.get("aliases"), list) else []
                keys = set(ids) | {a for a in aliases if isinstance(a, str)}
                sources = [("max_severity", finite(g.get("max_severity")))]
                fixed = []
                for n, v in enumerate(vulns):
                    if not _vkeys(v) & keys:
                        continue
                    used.add(n)
                    _vuln_sources(v, info["name"], sources, fixed)
                found.append({"name": info["name"], "version": info.get("version"),
                              "ids": sorted(keys), "label": ",".join(ids),
                              "sources": sources,
                              "fix_note": describe_fix(info.get("version"), fixed)})
            # 阻塞 1：没被任何 group 引用的漏洞单独算一条
            for n, v in enumerate(vulns):
                if n in used:
                    continue
                sources, fixed = [], []
                _vuln_sources(v, info["name"], sources, fixed)
                found.append({"name": info["name"], "version": info.get("version"),
                              "ids": sorted(_vkeys(v)), "label": f"{v['id']}（未归组）",
                              "sources": sources,
                              "fix_note": describe_fix(info.get("version"), fixed)})
    return found, packages


def findings_pnpm(data):
    adv = need(data, "advisories", dict, "pnpm audit 输出")
    meta = need(data, "metadata", dict, "pnpm audit 输出")
    need(meta, "vulnerabilities", dict, "metadata")
    deps = meta.get("totalDependencies", meta.get("dependencies"))
    found = []
    for key, a in adv.items():
        if not isinstance(a, dict):
            raise GateError(f"advisory {key} 不是对象")
        gid = a.get("github_advisory_id")
        ids = {x for x in (gid, *(a.get("cves") or [])) if isinstance(x, str)}
        if not ids:
            raise GateError(f"advisory {key} 缺少 github_advisory_id")
        cv = a.get("cvss") if isinstance(a.get("cvss"), dict) else {}
        sources = [(f"severity {a.get('severity')!r}", label_score(a.get("severity"))),
                   ("cvss.score", finite(cv.get("score"))),
                   ("cvss.vectorString", score_vector(cv.get("vectorString")))]
        vers = [f.get("version") for f in a.get("findings") or [] if isinstance(f, dict)]
        patched = a.get("patched_versions")
        fixed = re.findall(r">=\s*v?(\d+\.\d+\.\d+)", patched) if isinstance(patched, str) else []
        found.append({"name": a.get("module_name", "?"), "version": vers[0] if vers else None,
                      "ids": sorted(ids), "label": gid or key, "sources": sources,
                      "fix_note": describe_fix(vers[0] if vers else None, fixed)})
    return found, deps if isinstance(deps, int) and not isinstance(deps, bool) else None


def findings_npm(data):
    if data.get("auditReportVersion") != 2:
        raise GateError("npm audit 输出缺少 auditReportVersion: 2（只支持 npm 7+ 的 JSON）")
    vulns = need(data, "vulnerabilities", dict, "npm audit 输出")
    meta = need(data, "metadata", dict, "npm audit 输出")
    deps = (meta.get("dependencies") or {}).get("total") \
        if isinstance(meta.get("dependencies"), dict) else None
    found = []
    for name, v in vulns.items():
        if not isinstance(v, dict) or not isinstance(v.get("via"), list):
            raise GateError(f"vulnerabilities.{name} 条目异常")
        for via in v["via"]:
            if isinstance(via, str):
                continue  # 传递关系，真正的 advisory 记在被依赖的包上
            if not isinstance(via, dict):
                raise GateError(f"vulnerabilities.{name}.via 条目异常")
            url = via.get("url") if isinstance(via.get("url"), str) else ""
            gid = url.rsplit("/", 1)[-1] if "GHSA-" in url else None
            ids = {x for x in (gid,) if x} or {str(via.get("source", name))}
            cv = via.get("cvss") if isinstance(via.get("cvss"), dict) else {}
            sources = [(f"severity {via.get('severity')!r}", label_score(via.get("severity"))),
                       ("cvss.score", finite(cv.get("score"))),
                       ("cvss.vectorString", score_vector(cv.get("vectorString")))]
            fa = v.get("fixAvailable")
            if fa is False:
                note = "无修复版本"
            elif isinstance(fa, dict) and fa.get("isSemVerMajor"):
                note = f"修复版本超出依赖范围（需 {fa.get('name')}@{fa.get('version')}）"
            elif fa:
                note = "有修复版本，可在现有范围内升级"
            else:
                note = "无修复版本"
            found.append({"name": name, "version": None, "ids": sorted(ids),
                          "label": gid or str(via.get("source", name)),
                          "sources": sources, "fix_note": note,
                          "unignorable": gid is None})
    return found, deps if isinstance(deps, int) and not isinstance(deps, bool) else None


READERS = {"osv": findings_osv, "pnpm-audit": findings_pnpm, "npm-audit": findings_npm}


def check_results(path, fmt, exit_code, ignores=None, require_packages=False, today=None):
    """返回 (errors, warnings)。"""
    if exit_code not in (0, 1):
        return [f"{fmt} 退出码 {exit_code}，工具出错"], []
    errs, warn = [], []
    skip = set()
    if ignores:
        cerrs, entries = check_config(ignores, today=today)
        if cerrs:
            return cerrs, []
        skip = {e["id"] for e in entries}
    try:
        found, packages = READERS[fmt](load_json(path))
    except GateError as e:
        return [str(e)], []
    if require_packages and not packages:
        errs.append("没有扫到任何包（osv 须带 --all-packages；锁文件是否被识别？）")
    if exit_code == 1 and not found:
        errs.append(f"{fmt} 退出码 1 但输出里没有漏洞记录，JSON 不完整")
    high = 0
    for f in found:
        label = f"{f['name']}@{f['version'] or '?'} {f['label']}"
        if set(f["ids"]) & skip:
            warn.append(f"{label} 已登记忽略")
            continue
        score, why = best_score(f["sources"])
        if score is None or score >= HIGH:
            high += 1
            if f.get("unignorable"):
                tail = "没有 GHSA 编号，无法登记忽略，只能升级或替换依赖"
            elif f["fix_note"] == "无修复版本":
                tail = "未登记在 osv-scanner.toml"
            else:
                tail = "需升级"
            errs.append(f"{label} {why}，{f['fix_note']}，{tail}")
        else:
            warn.append(f"{label} {why}，{f['fix_note']}")
    if exit_code == 0 and (high if fmt != "osv" else found):
        errs.append(f"{fmt} 退出码 0 但输出里有漏洞记录，结果不一致")
    return errs, warn


# ============================== 命令行 ==============================

def report(errs, warn, what):
    for w in warn:
        print(f"::warning::{w}")
    for e in errs:
        print(f"::error::{e}")
    print(f"vuln-gate {__version__} ({what}): {len(errs)} error, {len(warn)} warning")
    return 1 if errs else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=f"共享漏洞门禁 {__version__}")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("config")
    c.add_argument("toml")
    c.add_argument("--effective", required=True)
    r = sub.add_parser("results")
    r.add_argument("json")
    r.add_argument("--format", choices=sorted(READERS), required=True)
    r.add_argument("--exit-code", type=int, required=True)
    r.add_argument("--ignores")
    r.add_argument("--require-packages", action="store_true")
    a = ap.parse_args(argv)
    if a.cmd == "config":
        errs, entries = check_config(a.toml)
        if not errs:
            write_effective(entries, a.effective)
        return report(errs, [], "config")
    errs, warn = check_results(a.json, a.format, a.exit_code, a.ignores, a.require_packages)
    return report(errs, warn, f"results/{a.format}")


if __name__ == "__main__":
    sys.exit(main())
