#!/usr/bin/env python3
# 共享文件，禁止各仓单独修改。随 vuln-gate.py 1.1.0 一起分发、一起校验哈希。
"""vuln-gate.py 共享反例集（清单 3.11、3.13）。用法：python3 scripts/test_vuln_gate.py

分组：
  Osv / Config      —— 并入 mugsun-track osv-gate.py 的全部 36 个 fixture（31 + 复核新增 5）
  Severity          —— severity 大小写 / 空 / 缺失 / 非字符串、只有向量、NaN/Inf、v4
  Structure         —— 清单 3.13 列出的结构反例
  History           —— 各仓历史缺陷（docs / pc / start / uniappx）逐类复现
  PnpmAudit / NpmAudit —— 其他输入格式
  Cvss              —— 官方公式的已知分数
  Unreferenced      —— 1.1.0：没被 group 引用的漏洞单独判定（代码质量官阻塞 1）
  OsvKeys           —— 1.1.0：groups / vulnerabilities 只出现一个判失败
  Scope             —— 1.1.0：scope 必填，prod 30 天、dev 90 天（阻塞 2、安全官 S1）
  NpmExtra          —— 1.1.0：cvss.score 0 计入、无 GHSA 不可忽略
  Severity 另含 S3（-0.0）、S4（不合法值按 10.0，不被 LOW 压下）反例
"""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "vuln_gate", pathlib.Path(__file__).with_name("vuln-gate.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

TODAY = dt.date(2026, 10, 21)
V98 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"      # 9.8
V53 = "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N"      # 5.3
V4 = "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:H/VI:H/VA:H/SC:N/SI:N/SA:N"


def pkg(name, ver, vid, sev, fixed=None, vuln_extra=None, group_extra=None):
    events = [{"introduced": "0"}] + ([{"fixed": fixed}] if fixed else [])
    v = {"id": vid, "affected": [{"package": {"name": name, "ecosystem": "npm"},
                                  "ranges": [{"type": "SEMVER", "events": events}]}]}
    v.update(vuln_extra or {})
    g = {"ids": [vid], "aliases": [vid]}
    if sev is not ...:
        g["max_severity"] = sev
    g.update(group_extra or {})
    return {"package": {"name": name, "version": ver, "ecosystem": "npm"},
            "groups": [g], "vulnerabilities": [v]}


def doc(*pkgs):
    return {"results": [{"source": {"path": "pnpm-lock.yaml"}, "packages": list(pkgs)}]}


ESBUILD_LOW = pkg("esbuild", "0.27.7", "GHSA-g7r4-m6w7-qqqr", "2.5", "0.28.1")
GOOD = ('[[IgnoredVulns]]\nid = "GHSA-2v37-7h3g-55p8"\nscope = "dev"\nadded = 2026-10-21\n'
        'ignoreUntil = 2027-01-19\nreason = "无修复版本"\n')


class Base(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.addCleanup(self.d.cleanup)

    def file(self, name, text):
        p = pathlib.Path(self.d.name) / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def res(self, data, rc, fmt="osv", raw=None, **kw):
        path = self.file("o.json", raw if raw is not None else json.dumps(data))
        kw.setdefault("today", TODAY)
        return gate.check_results(path, fmt, rc, **kw)

    def fails(self, data, rc, needle=None, **kw):
        e, _ = self.res(data, rc, **kw)
        self.assertTrue(e, "应判失败")
        if needle:
            self.assertTrue(any(needle in x for x in e), e)
        return e

    def passes(self, data, rc, **kw):
        e, w = self.res(data, rc, **kw)
        self.assertEqual(e, [])
        return w

    def check(self, text):
        return gate.check_config(self.file("c.toml", text), today=TODAY)


# ---------------- 来自 track osv-gate.py 的 fixture ----------------

class Osv(Base):
    def test_clean_rc0_ok(self):
        self.assertEqual(self.res({"results": []}, 0), ([], []))

    def test_results_missing(self):
        self.fails({}, 0, "缺少 results")

    def test_results_null(self):
        self.fails({"results": None}, 0, "类型不对")

    def test_results_not_list(self):
        self.fails({"results": {"a": 1}}, 1, "类型不对")

    def test_top_level_error(self):
        self.fails({"results": [], "error": "boom"}, 0, "error 字段")

    def test_result_entry_error(self):
        self.fails({"results": [{"error": "x"}]}, 1, "条目异常")

    def test_invalid_json(self):
        self.fails(None, 1, "不是合法 JSON", raw="{not json")

    def test_tool_error_rc(self):
        for rc in (2, 127, 128, -1):
            self.fails({"results": []}, rc, "工具出错")

    def test_rc1_without_vulns_incomplete(self):
        self.fails({"results": []}, 1, "JSON 不完整")

    def test_rc0_with_vulns_inconsistent(self):
        self.fails(doc(ESBUILD_LOW), 0, "不一致")

    def test_rc1_low_only_ok(self):
        self.assertEqual(len(self.passes(doc(ESBUILD_LOW), 1)), 1)

    def test_high_fix_in_range_fails(self):
        self.fails(doc(pkg("nanoid", "3.3.17", "GHSA-a", "8.2", "3.3.18")), 1, "可在现有范围内升级")

    def test_high_no_fix_unregistered_fails(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-b", "9.8")), 1, "未登记在 osv-scanner.toml")

    def test_high_fix_out_of_range_fails(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-c", "7.0", "2.0.0")), 1, "修复版本超出依赖范围")

    def test_no_score_treated_as_high(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-d", "")), 1, "无法判定严重度")

    def test_medium_only_warns(self):
        w = self.passes(doc(pkg("x", "1.0.0", "GHSA-e", "6.9", "1.0.1")), 1)
        self.assertIn("可在现有范围内升级", w[0])

    def test_esbuild_out_of_range_wording(self):
        w = self.passes(doc(ESBUILD_LOW), 1)
        self.assertIn("修复版本超出依赖范围（修复于 0.28.1）", w[0])

    def test_zero_major_same_minor_in_range(self):
        w = self.passes(doc(pkg("esbuild", "0.27.7", "GHSA-f", "2.5", "0.27.9")), 1)
        self.assertIn("可在现有范围内升级", w[0])

    def test_no_fix_wording(self):
        w = self.passes(doc(pkg("x", "1.0.0", "GHSA-g", "4.0")), 1)
        self.assertIn("无修复版本", w[0])


class Config(Base):
    def test_empty_ok(self):
        self.assertEqual(self.check("# only comments\n"), ([], []))

    def test_good_entry_ok_and_effective_drops_added(self):
        e, entries = self.check(GOOD)
        self.assertEqual(e, [])
        out = self.file("eff.toml", "")
        gate.write_effective(entries, out)
        text = pathlib.Path(out).read_text(encoding="utf-8")
        self.assertNotIn("added =", text)
        self.assertIn("ignoreUntil = 2027-01-19T23:59:59Z", text)

    def test_missing_added(self):
        e, _ = self.check(GOOD.replace("added = 2026-10-21\n", ""))
        self.assertIn("缺少 added", e[0])

    def test_over_90_days_from_added(self):
        e, _ = self.check(GOOD.replace("2027-01-19", "2027-01-20"))
        self.assertTrue(any("超过 90 天" in x for x in e))

    def test_90_days_from_added_not_today(self):
        e, _ = self.check(GOOD.replace("added = 2026-10-21", "added = 2026-09-01")
                          .replace("2027-01-19", "2026-12-15"))
        self.assertTrue(any("超过 90 天" in x for x in e))

    def test_expired(self):
        e, _ = self.check(GOOD.replace("added = 2026-10-21", "added = 2026-08-01")
                          .replace("2027-01-19", "2026-10-20"))
        self.assertTrue(any("过期" in x for x in e))

    def test_until_today_still_valid(self):
        e, _ = self.check(GOOD.replace("added = 2026-10-21", "added = 2026-08-01")
                          .replace("2027-01-19", "2026-10-21"))
        self.assertEqual(e, [])

    def test_until_yesterday_expired_utc_wording(self):
        e, _ = self.check(GOOD.replace("added = 2026-10-21", "added = 2026-08-01")
                          .replace("2027-01-19", "2026-10-20"))
        self.assertTrue(any("23:59:59Z（UTC）过期" in x for x in e))

    def test_default_today_is_utc(self):
        real = gate.dt.datetime

        class Fake(real):
            @classmethod
            def now(cls, tz=None):
                # 北京时间 2026-10-22 07:00 = UTC 2026-10-21 23:00
                return real(2026, 10, 21, 23, 0, tzinfo=dt.timezone.utc).astimezone(tz)
        gate.dt.datetime = Fake
        try:
            path = self.file("u.toml", GOOD.replace("added = 2026-10-21", "added = 2026-08-01")
                             .replace("2027-01-19", "2026-10-21"))
            e, _ = gate.check_config(path)
        finally:
            gate.dt.datetime = real
        self.assertEqual(e, [])

    def test_entry_not_table(self):
        e, _ = self.check('IgnoredVulns = ["GHSA-x", 1]\n')
        self.assertEqual(len(e), 2)
        self.assertTrue(all("不是表" in x for x in e))

    def test_ignoredvulns_not_array(self):
        e, _ = self.check('IgnoredVulns = "GHSA-x"\n')
        self.assertIn("数组", e[0])

    def test_missing_reason(self):
        e, _ = self.check(GOOD.replace('reason = "无修复版本"\n', ""))
        self.assertIn("缺少 reason", e[0])

    def test_quoted_date(self):
        e, _ = self.check(GOOD.replace("ignoreUntil = 2027-01-19", 'ignoreUntil = "2027-01-19"'))
        self.assertTrue(any("写成了字符串" in x and "不要加引号" in x for x in e))

    def test_quoted_bad_format(self):
        e, _ = self.check(GOOD.replace("added = 2026-10-21", 'added = "21/10/2026"'))
        self.assertTrue(any("应为 YYYY-MM-DD" in x for x in e))

    def test_number_date(self):
        e, _ = self.check(GOOD.replace("added = 2026-10-21", "added = 20261021"))
        self.assertTrue(any("类型不对" in x for x in e))

    def test_invalid_toml(self):
        e, _ = self.check("[[IgnoredVulns]\nid=")
        self.assertIn("TOML 解析失败", e[0])

    def test_unknown_key(self):
        e, _ = self.check(GOOD + 'severity = "low"\n')
        self.assertTrue(any("不认识的键" in x for x in e))

    # ---- 安全官 F2：id 必须是单个 GHSA / CVE 字符串 ----
    def test_id_cve_ok(self):
        self.assertEqual(self.check(GOOD.replace("GHSA-2v37-7h3g-55p8", "CVE-2026-12345"))[0], [])

    def test_id_list_rejected(self):
        e, _ = self.check(GOOD.replace('id = "GHSA-2v37-7h3g-55p8"',
                                       'id = ["GHSA-2v37-7h3g-55p8", "CVE-2026-1234"]'))
        self.assertIn("单个字符串", e[0])

    def test_id_number_rejected(self):
        e, _ = self.check(GOOD.replace('id = "GHSA-2v37-7h3g-55p8"', "id = 12345"))
        self.assertIn("单个字符串", e[0])

    def test_id_bad_format_rejected(self):
        for bad in ("GHSA-test-test-test", "ghsa-2v37-7h3g-55p8", "CVE-26-1",
                    "GHSA-2v37-7h3g-55p8,CVE-2026-1234", " GHSA-2v37-7h3g-55p8", "PYSEC-2024-1"):
            e, _ = self.check(GOOD.replace("GHSA-2v37-7h3g-55p8", bad))
            self.assertTrue(any("格式" in x for x in e), bad)

    def test_duplicate_id(self):
        e, _ = self.check(GOOD + "\n" + GOOD)
        self.assertTrue(any("重复" in x for x in e))

    def test_reason_not_string(self):
        e, _ = self.check(GOOD.replace('reason = "无修复版本"', "reason = 1"))
        self.assertTrue(any("reason" in x for x in e))

    def test_added_in_future(self):
        e, _ = self.check(GOOD.replace("added = 2026-10-21", "added = 2026-10-22"))
        self.assertTrue(any("晚于今天" in x for x in e))

    def test_until_before_added(self):
        e, _ = self.check(GOOD.replace("added = 2026-10-21", "added = 2026-10-21")
                          .replace("2027-01-19", "2026-10-20"))
        self.assertTrue(any("早于 added" in x for x in e))


# ---------------- 严重度 ----------------

class Severity(Base):
    def test_label_case_insensitive(self):
        for label in ("HIGH", "High", "high", " high ", "CRITICAL", "Critical"):
            self.fails(doc(pkg("x", "1.0.0", "GHSA-h", ..., vuln_extra={
                "database_specific": {"severity": label}})), 1)
        for label in ("MODERATE", "Moderate", "moderate", "MEDIUM", "Low", "LOW"):
            self.passes(doc(pkg("x", "1.0.0", "GHSA-h", ..., vuln_extra={
                "database_specific": {"severity": label}})), 1)

    def test_label_empty_or_missing_no_other_source(self):
        for extra in ({"database_specific": {"severity": ""}},
                      {"database_specific": {}}, {}):
            self.fails(doc(pkg("x", "1.0.0", "GHSA-i", ..., vuln_extra=extra)), 1, "无法判定严重度")

    def test_label_non_string(self):
        for bad in (7, 7.5, True, ["high"], {"level": "high"}):
            self.fails(doc(pkg("x", "1.0.0", "GHSA-j", ..., vuln_extra={
                "database_specific": {"severity": bad}})), 1, "不合法，按 10.0")
        self.fails(doc(pkg("x", "1.0.0", "GHSA-j", ..., vuln_extra={
            "database_specific": {"severity": None}})), 1, "无法判定严重度")

    def test_unknown_label(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-k", ..., vuln_extra={
            "database_specific": {"severity": "urgent"}})), 1, "不合法，按 10.0")

    def test_vector_only_98_fails(self):
        e = self.fails(doc(pkg("x", "1.0.0", "GHSA-l", ..., vuln_extra={
            "severity": [{"type": "CVSS_V3", "score": V98}]})), 1)
        self.assertIn("严重度 9.8", e[0])

    def test_vector_only_98_with_empty_max_severity(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-l", "", vuln_extra={
            "severity": [{"type": "CVSS_V3", "score": V98}]})), 1, "严重度 9.8")

    def test_vector_only_medium_passes(self):
        w = self.passes(doc(pkg("x", "1.0.0", "GHSA-m", ..., vuln_extra={
            "severity": [{"type": "CVSS_V3", "score": V53}]})), 1)
        self.assertIn("严重度 5.3", w[0])

    def test_max_of_sources_vector_beats_low_label(self):
        # 标签说 low、max_severity 说 2.0，但向量是 9.8：取最高值，判失败
        self.fails(doc(pkg("x", "1.0.0", "GHSA-n", "2.0", vuln_extra={
            "database_specific": {"severity": "LOW"},
            "severity": [{"type": "CVSS_V3", "score": V98}]})), 1, "严重度 9.8")

    def test_max_of_sources_label_beats_low_score(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-o", "3.1", vuln_extra={
            "database_specific": {"severity": "critical"}})), 1, "严重度 9.0")

    def test_nan_inf_score_not_a_source(self):
        for bad in ("NaN", "nan", "inf", "-inf", "Infinity", "11", "-1", "abc",
                    float("nan"), float("inf"), -0.5, 10.01):
            self.fails(doc(pkg("x", "1.0.0", "GHSA-p", bad)), 1, "不合法，按 10.0")

    def test_negative_zero_is_10(self):  # 安全官 S3
        for bad in ("-0.0", "-0", -0.0):
            self.fails(doc(pkg("x", "1.0.0", "GHSA-p", bad)), 1, "不合法，按 10.0")
        self.passes(doc(pkg("x", "1.0.0", "GHSA-p", "0.0")), 1)
        self.passes(doc(pkg("x", "1.0.0", "GHSA-p", 0)), 1)

    def test_nan_with_valid_low_vector_still_fails(self):  # S4：不合法值不能被丢掉
        self.fails(doc(pkg("x", "1.0.0", "GHSA-q", "NaN", vuln_extra={
            "severity": [{"type": "CVSS_V3", "score": V53}]})), 1, "不合法，按 10.0")

    def test_invalid_sources_not_masked_by_low_label(self):  # 安全官 S4 反例
        low = {"database_specific": {"severity": "LOW"}}
        cases = [("NaN", []), ("Infinity", []), ("-0.0", []),
                 (..., [{"type": "CVSS_V3", "score": "CVSS:3.1/AV:N"}]),
                 (..., [{"type": "CVSS_V3", "score": "garbage"}]),
                 (..., [{"type": "CVSS_V4", "score": V4}])]
        for ms, sev in cases:
            extra = dict(low, severity=sev)
            self.fails(doc(pkg("x", "1.0.0", "GHSA-q", ms, vuln_extra=extra)), 1, "不合法，按 10.0")

    def test_pnpm_nan_score_with_low_label_fails(self):  # S4 pnpm 反例
        self.fails(audit({"1": adv("low", cvss={"score": "NaN", "vectorString": None})}), 1,
                   "不合法，按 10.0", fmt="pnpm-audit")

    def test_max_severity_not_string(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-r", None)), 1, "无法判定严重度")
        for bad in (True, [], {}):
            self.fails(doc(pkg("x", "1.0.0", "GHSA-r", bad)), 1, "不合法，按 10.0")

    def test_max_severity_number_ok(self):
        self.passes(doc(pkg("x", "1.0.0", "GHSA-s", 3.3)), 1)

    def test_v4_only_unscorable_fails(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-t", ..., vuln_extra={
            "severity": [{"type": "CVSS_V4", "score": V4}]})), 1, "不合法，按 10.0")

    def test_v4_with_low_label_still_fails(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-u", ..., vuln_extra={
            "severity": [{"type": "CVSS_V4", "score": V4}],
            "database_specific": {"severity": "LOW"}})), 1, "不合法，按 10.0")

    def test_broken_vector_not_a_source(self):
        for bad in ("CVSS:3.1/AV:N", "CVSS:3.1/AV:X/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H",
                    "CVSS:3.2/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", "garbage"):
            self.fails(doc(pkg("x", "1.0.0", "GHSA-v", ..., vuln_extra={
                "severity": [{"type": "CVSS_V3", "score": bad}]})), 1, "不合法，按 10.0")
        self.fails(doc(pkg("x", "1.0.0", "GHSA-v", ..., vuln_extra={
            "severity": [{"type": "CVSS_V3", "score": ""}]})), 1, "无法判定严重度")

    def test_cvss_v2_vector(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-w", ..., vuln_extra={
            "severity": [{"type": "CVSS_V2", "score": "AV:N/AC:L/Au:N/C:C/I:C/A:C"}]})), 1,
            "严重度 10.0")

    def test_alias_matched_vuln_contributes(self):
        # group 用 GHSA，漏洞条目 id 是 CVE、alias 里有 GHSA
        p = pkg("x", "1.0.0", "GHSA-x", ..., )
        p["vulnerabilities"][0] = {"id": "CVE-2026-1", "aliases": ["GHSA-x"],
                                   "severity": [{"type": "CVSS_V3", "score": V98}]}
        self.fails(doc(p), 1, "严重度 9.8")


# ---------------- 结构反例（清单 3.13） ----------------

class Structure(Base):
    def test_empty_object(self):
        self.fails({}, 0)

    def test_results_empty_object(self):
        self.fails({"results": {}}, 0, "类型不对")

    def test_error_null(self):
        self.fails({"results": [], "error": None}, 0, "error 字段")

    def test_errors_field(self):
        self.fails({"results": [], "errors": []}, 0, "errors 字段")

    def test_error_with_empty_results_rc1(self):
        self.fails({"results": [], "error": "x"}, 1, "error 字段")

    def test_packages_null(self):
        self.fails({"results": [{"packages": None}]}, 1, "类型不对")

    def test_packages_missing(self):
        self.fails({"results": [{"source": {}}]}, 1, "缺少 packages")

    def test_result_not_object(self):
        self.fails({"results": [1]}, 1, "条目异常")

    def test_groups_null(self):
        p = pkg("x", "1.0.0", "GHSA-a", "9.8")
        p["groups"] = None
        self.fails(doc(p), 1, "类型不对")

    def test_vulns_without_groups(self):
        p = pkg("x", "1.0.0", "GHSA-a", "9.8")
        p["groups"] = []
        self.fails(doc(p), 1, "缺少 groups")

    def test_group_without_ids(self):
        p = pkg("x", "1.0.0", "GHSA-a", "9.8")
        p["groups"] = [{"max_severity": "9.8"}]
        self.fails(doc(p), 1, "缺少 ids")

    def test_package_name_missing(self):
        p = pkg("x", "1.0.0", "GHSA-a", "2.0")
        p["package"] = {"version": "1"}
        self.fails(doc(p), 1, "package.name")

    def test_empty_file(self):
        self.fails(None, 0, "为空", raw="   \n")

    def test_top_level_list(self):
        self.fails(None, 0, "不是 JSON 对象", raw="[]")

    def test_missing_exit_code_cli(self):
        path = self.file("o.json", '{"results":[]}')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as cm:
            gate.main(["results", "--format", "osv", path])
        self.assertEqual(cm.exception.code, 2)

    def test_require_packages_zero(self):
        self.fails({"results": []}, 0, "没有扫到任何包", require_packages=True)

    def test_require_packages_ok_with_all_packages(self):
        clean = {"package": {"name": "a", "version": "1.0.0"}, "groups": [], "vulnerabilities": []}
        self.passes(doc(clean), 0, require_packages=True)

    def test_ignores_invalid_blocks_results(self):
        bad = self.file("bad.toml", GOOD.replace("added = 2026-10-21\n", ""))
        self.fails({"results": []}, 0, "缺少 added", ignores=bad)

    def test_cli_end_to_end(self):
        path = self.file("o.json", json.dumps(doc(ESBUILD_LOW)))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            rc = gate.main(["results", "--format", "osv", "--exit-code", "1", path])
        self.assertEqual(rc, 0)
        self.assertIn("修复版本超出依赖范围", out.getvalue())


# ---------------- 各仓历史缺陷 ----------------

class History(Base):
    def test_pc_start_vector_in_cvss_v3_score_was_unknown(self):
        # pc/start：CVSS_V3 的 score 是向量，float() 失败 -> UNKNOWN -> 只告警；9.8 被放过
        self.fails(doc(pkg("x", "1.0.0", "GHSA-a", ..., vuln_extra={
            "severity": [{"type": "CVSS_V3", "score": V98}]})), 1, "严重度 9.8")

    def test_pc_start_high_without_fix_was_warning(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-b", ..., vuln_extra={
            "database_specific": {"severity": "HIGH"}})), 1, "未登记")

    def test_pc_start_unknown_severity_was_warning(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-c", ...)), 1, "无法判定严重度")

    def test_pc_start_lowercase_label_with_upper_compare(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-d", ..., vuln_extra={
            "database_specific": {"severity": "critical"}})), 1)

    def test_pc_start_or_true_swallowed_tool_error(self):
        # `|| true` 吞掉退出码：现在退出码必填，工具出错判失败
        self.fails(doc(ESBUILD_LOW), 128, "工具出错")

    def test_pc_start_results_or_empty(self):
        # `data.get("results") or []` 把 null 当成干净
        self.fails({"results": None}, 0)

    def test_pc_ignores_local_date_and_90_from_today(self):
        # pc：90 天从今天算、用本地日期；现在从 added 算、按 UTC
        e, _ = self.check(GOOD.replace("added = 2026-10-21", "added = 2026-07-01")
                          .replace("2027-01-19", "2026-11-01"))
        self.assertTrue(any("超过 90 天" in x for x in e))

    def test_pc_hand_toml_parser_comment_in_string(self):
        # pc 手写 TOML 解析器会把字符串里的 # 当注释截断
        e, entries = self.check(GOOD.replace('reason = "无修复版本"', 'reason = "见 issue #12"'))
        self.assertEqual(e, [])
        self.assertEqual(entries[0]["reason"], "见 issue #12")

    def test_docs_osv_rc0_with_vulns_not_checked(self):
        self.fails(doc(pkg("x", "1.0.0", "GHSA-e", "5.0")), 0, "不一致")

    def test_docs_ignore_id_not_validated(self):
        e, _ = self.check(GOOD.replace("GHSA-2v37-7h3g-55p8", "GHSA-test-test-test"))
        self.assertTrue(e)

    def test_docs_added_regex_strip_multiline(self):
        # docs 用正则删 added 行；这里由解析后重写，不受写法影响
        e, entries = self.check(GOOD.replace("added = 2026-10-21", "added   =   2026-10-21"))
        self.assertEqual(e, [])
        out = self.file("eff.toml", "")
        gate.write_effective(entries, out)
        self.assertNotIn("added", pathlib.Path(out).read_text(encoding="utf-8").split("\n", 1)[1])

    def test_docs_audit_severity_case(self):
        # docs audit-gate 曾只认小写；"High" 必须判失败
        self.fails(audit({"1": adv("High")}), 1, fmt="pnpm-audit")

    def test_uniappx_low_only_should_not_block(self):
        # uniappx 直接用 osv-scanner 退出码，Low 也会挡；共享门禁只告警
        self.passes(doc(ESBUILD_LOW), 1)


# ---------------- pnpm audit ----------------

def adv(sev, gid="GHSA-2v37-7h3g-55p8", patched=">=3.3.18", ver="3.3.17", **extra):
    a = {"github_advisory_id": gid, "module_name": "nanoid", "severity": sev,
         "patched_versions": patched, "findings": [{"version": ver, "paths": ["."]}]}
    a.update(extra)
    return a


def audit(advisories, deps=10):
    return {"advisories": advisories, "metadata": {
        "vulnerabilities": {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0},
        "dependencies": deps, "totalDependencies": deps}}


class PnpmAudit(Base):
    def r(self, data, rc, **kw):
        return self.res(data, rc, fmt="pnpm-audit", **kw)

    def test_clean(self):
        self.assertEqual(self.r(audit({}), 0), ([], []))

    def test_low_warns_with_fix_note(self):
        e, w = self.r(audit({"1": adv("low", patched=">=0.28.1", ver="0.27.7")}), 1)
        self.assertEqual(e, [])
        self.assertIn("修复版本超出依赖范围（修复于 0.28.1）", w[0])

    def test_high_fails(self):
        self.fails(audit({"1": adv("high")}), 1, "可在现有范围内升级", fmt="pnpm-audit")

    def test_severity_missing_or_bad(self):
        for bad in (None, ""):
            self.fails(audit({"1": adv(bad)}), 1, "无法判定严重度", fmt="pnpm-audit")
        for bad in (7, "urgent"):
            self.fails(audit({"1": adv(bad)}), 1, "不合法，按 10.0", fmt="pnpm-audit")

    def test_cvss_vector_beats_label(self):
        self.fails(audit({"1": adv("low", cvss={"score": 0, "vectorString": V98})}), 1,
                   "严重度 9.8", fmt="pnpm-audit")

    def test_structure(self):
        for bad in ({}, {"advisories": None, "metadata": {"vulnerabilities": {}}},
                    {"advisories": [], "metadata": {"vulnerabilities": {}}},
                    {"advisories": {}, "metadata": None},
                    {"advisories": {}, "metadata": {}},
                    {"error": {"code": "ERR_PNPM_AUDIT_BAD_RESPONSE"}},
                    {"advisories": {"1": "x"}, "metadata": {"vulnerabilities": {}}}):
            self.fails(bad, 0, fmt="pnpm-audit")

    def test_rc1_without_advisories(self):
        self.fails(audit({}), 1, "JSON 不完整", fmt="pnpm-audit")

    def test_rc0_with_high_inconsistent(self):
        self.fails(audit({"1": adv("critical")}), 0, "不一致", fmt="pnpm-audit")

    def test_rc0_with_low_ok(self):
        # pnpm audit --audit-level=high 时 Low 不改退出码
        self.passes(audit({"1": adv("low")}), 0, fmt="pnpm-audit")

    def test_ignored_by_toml(self):
        ig = self.file("i.toml", GOOD)
        w = self.passes(audit({"1": adv("high")}), 1, fmt="pnpm-audit", ignores=ig)
        self.assertIn("已登记忽略", w[0])

    def test_require_packages(self):
        self.fails(audit({}, deps=0), 0, "没有扫到任何包", fmt="pnpm-audit",
                   require_packages=True)


# ---------------- npm audit ----------------

def npm(vulns, total=5):
    return {"auditReportVersion": 2, "vulnerabilities": vulns, "metadata": {
        "vulnerabilities": {"total": len(vulns)}, "dependencies": {"total": total}}}


def npm_v(sev, fix=True, cvss=None, gid="GHSA-2v37-7h3g-55p8"):
    via = {"source": 1, "name": "x", "severity": sev,
           "url": f"https://github.com/advisories/{gid}", "cvss": cvss or {"score": 0,
                                                                         "vectorString": None}}
    return {"name": "x", "severity": sev, "via": [via, "y"], "fixAvailable": fix}


class NpmAudit(Base):
    def r(self, data, rc, **kw):
        return self.res(data, rc, fmt="npm-audit", **kw)

    def test_clean(self):
        self.assertEqual(self.r(npm({}), 0), ([], []))

    def test_moderate_warns(self):
        e, w = self.r(npm({"x": npm_v("Moderate")}), 1)
        self.assertEqual(e, [])
        self.assertIn("可在现有范围内升级", w[0])

    def test_semver_major_fix_wording(self):
        _, w = self.r(npm({"x": npm_v("low", fix={"name": "x", "version": "2.0.0",
                                                    "isSemVerMajor": True})}), 1)
        self.assertIn("修复版本超出依赖范围", w[0])

    def test_no_fix_wording(self):
        _, w = self.r(npm({"x": npm_v("low", fix=False)}), 1)
        self.assertIn("无修复版本", w[0])

    def test_high_upper_fails(self):
        self.fails(npm({"x": npm_v("HIGH")}), 1, fmt="npm-audit")

    def test_vector_only_98(self):
        self.fails(npm({"x": npm_v("", cvss={"score": 0, "vectorString": V98})}), 1,
                   "严重度 9.8", fmt="npm-audit")

    def test_structure(self):
        for bad in ({}, {"auditReportVersion": 1, "advisories": {}},
                    {"auditReportVersion": 2, "vulnerabilities": None, "metadata": {}},
                    {"auditReportVersion": 2, "vulnerabilities": {}, "metadata": None},
                    {"auditReportVersion": 2, "vulnerabilities": {"x": {"via": None}},
                     "metadata": {}}):
            self.fails(bad, 0, fmt="npm-audit")

    def test_require_packages(self):
        self.fails(npm({}, total=0), 0, "没有扫到任何包", fmt="npm-audit",
                   require_packages=True)


# ---------------- CVSS 公式 ----------------

class Cvss(unittest.TestCase):
    KNOWN = {
        V98: 9.8, V53: 5.3,
        "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H": 10.0,
        "CVSS:3.1/AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H": 7.8,
        "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N": 6.1,
        "CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:N": 0.0,
        "CVSS:3.0/AV:N/AC:L/PR:L/UI:N/S:C/C:L/I:L/A:N": 6.4,
        "CVSS:3.1/AV:N/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N": 2.0,
        "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H/E:U/RL:O/RC:U": 9.8,
    }

    def test_known_v3(self):
        for v, s in self.KNOWN.items():
            self.assertEqual(gate.score_vector(v), s, v)

    def test_known_v2(self):
        self.assertEqual(gate.score_vector("AV:N/AC:L/Au:N/C:P/I:P/A:P"), 7.5)
        self.assertEqual(gate.score_vector("(AV:N/AC:M/Au:N/C:N/I:P/A:N)"), 4.3)

    def test_v4_not_scored(self):
        self.assertEqual(gate.score_vector(V4), 10.0)
        self.assertIsInstance(gate.score_vector(V4), gate.Invalid)

    def test_v30_roundup_integer_method(self):
        # 3.0 与 3.1 用同一整数化写法；浮点误差不应让 4.000000000000001 进位
        self.assertEqual(gate._roundup30(4.000000000000001), 4.0)
        self.assertEqual(gate._roundup30(4.02), 4.1)
        self.assertEqual(gate._roundup30(4.0), 4.0)


# ---------------- 1.1.0：代码质量官阻塞 1/2、安全官 S1 ----------------

class Unreferenced(Base):
    def test_vuln_not_in_any_group_counts(self):  # 阻塞 1 反例
        p = pkg("x", "1.0.0", "GHSA-a", "2")
        p["vulnerabilities"].append({"id": "GHSA-b", "severity": [
            {"type": "CVSS_V3", "score": V98}]})
        e = self.fails(doc(p), 1, "GHSA-b（未归组）")
        self.assertTrue(any("严重度 9.8" in x for x in e), e)

    def test_unreferenced_without_sources_is_high(self):
        p = pkg("x", "1.0.0", "GHSA-a", "2")
        p["vulnerabilities"].append({"id": "GHSA-b"})
        self.fails(doc(p), 1, "无法判定严重度")

    def test_unreferenced_low_warns(self):
        p = pkg("x", "1.0.0", "GHSA-a", "2")
        p["vulnerabilities"].append({"id": "GHSA-b", "severity": [
            {"type": "CVSS_V3", "score": V53}]})
        w = self.passes(doc(p), 1)
        self.assertTrue(any("GHSA-b（未归组）" in x for x in w), w)

    def test_alias_reference_counts_as_grouped(self):
        p = pkg("x", "1.0.0", "GHSA-a", "2")
        p["vulnerabilities"][0]["id"] = "CVE-2026-0001"
        p["vulnerabilities"][0]["aliases"] = ["GHSA-a"]
        w = self.passes(doc(p), 1)
        self.assertFalse(any("未归组" in x for x in w), w)

    def test_unreferenced_can_be_ignored(self):
        p = pkg("x", "1.0.0", "GHSA-a", "2")
        p["vulnerabilities"].append({"id": "GHSA-2v37-7h3g-55p8", "severity": [
            {"type": "CVSS_V3", "score": V98}]})
        self.passes(doc(p), 1, ignores=self.file("i.toml", GOOD))


class OsvKeys(Base):
    """osv-scanner 2.7.0 --all-packages 实测：没有漏洞的包 groups、vulnerabilities 都不出现。"""

    def test_clean_package_has_neither_key(self):
        self.passes(doc({"package": {"name": "ms", "version": "2.1.3", "ecosystem": "npm"}}), 0,
                    require_packages=True)

    def test_groups_without_vulnerabilities_key(self):
        p = pkg("x", "1.0.0", "GHSA-a", "2")
        del p["vulnerabilities"]
        self.fails(doc(p), 1, "只有 groups")

    def test_vulnerabilities_without_groups_key(self):
        p = pkg("x", "1.0.0", "GHSA-a", "2")
        del p["groups"]
        self.fails(doc(p), 1, "只有 vulnerabilities")


def entry(scope, added, until, extra=""):
    sc = "" if scope is None else f"scope = {scope}\n"
    return (f'[[IgnoredVulns]]\nid = "GHSA-2v37-7h3g-55p8"\n{sc}added = {added}\n'
            f'ignoreUntil = {until}\nreason = "无修复版本"\n{extra}')


class Scope(Base):
    def test_scope_required(self):
        e, _ = self.check(entry(None, "2026-10-21", "2026-10-30"))
        self.assertTrue(any("缺少 scope" in x for x in e), e)

    def test_scope_empty(self):
        e, _ = self.check(entry('""', "2026-10-21", "2026-10-30"))
        self.assertTrue(any("缺少 scope" in x for x in e), e)

    def test_scope_bad_value(self):
        for bad in ('"Prod"', '"production"', '"test"', "1", "true", '["prod"]'):
            e, _ = self.check(entry(bad, "2026-10-21", "2026-10-30"))
            self.assertTrue(any("scope 只能是" in x for x in e), (bad, e))

    def test_scope_with_whitespace_rejected(self):  # 代码质量官可选 2
        for bad in ('" prod"', '"prod "', '" "'):
            e, _ = self.check(entry(bad, "2026-10-21", "2026-10-30"))
            self.assertTrue(any("scope 只能是" in x for x in e), (bad, e))

    def test_prod_30_days_ok(self):
        self.assertEqual(self.check(entry('"prod"', "2026-10-21", "2026-11-20"))[0], [])

    def test_prod_31_days_fails(self):
        e, _ = self.check(entry('"prod"', "2026-10-21", "2026-11-21"))
        self.assertTrue(any("超过 30 天" in x for x in e), e)

    def test_prod_60_days_fails(self):  # 安全官 S1 fixture
        e, _ = self.check(entry('"prod"', "2026-10-01", "2026-11-30"))
        self.assertTrue(any("超过 30 天（scope = prod）" in x for x in e), e)

    def test_dev_90_ok_91_fails(self):
        self.assertEqual(self.check(entry('"dev"', "2026-10-21", "2027-01-19"))[0], [])
        e, _ = self.check(entry('"dev"', "2026-10-21", "2027-01-20"))
        self.assertTrue(any("超过 90 天（scope = dev）" in x for x in e), e)

    def test_effective_drops_scope(self):
        e, entries = self.check(entry('"prod"', "2026-10-21", "2026-11-20"))
        out = self.file("eff.toml", "")
        gate.write_effective(entries, out)
        text = pathlib.Path(out).read_text(encoding="utf-8")
        self.assertNotIn("scope", text.split("\n", 1)[1])
        self.assertNotIn("added", text.split("\n", 1)[1])

    def test_bad_ignores_fail_results(self):
        self.fails(doc(ESBUILD_LOW), 1, "超过 30 天",
                   ignores=self.file("i.toml", entry('"prod"', "2026-10-01", "2026-11-30")))


class NpmExtra(Base):
    def test_cvss_score_zero_is_a_source(self):  # 建议 2
        w = self.passes(npm({"x": npm_v(None, cvss={"score": 0, "vectorString": None})}), 1,
                        fmt="npm-audit")
        self.assertTrue(any("严重度 0.0" in x for x in w), w)

    def test_cvss_score_negative_zero_is_10(self):
        self.fails(npm({"x": npm_v("low", cvss={"score": -0.0, "vectorString": None})}), 1,
                   "不合法，按 10.0", fmt="npm-audit")

    def test_no_ghsa_says_unignorable(self):  # 建议 3
        v = npm_v("high")
        v["via"][0]["url"] = "https://npmjs.com/advisories/1"
        self.fails(npm({"x": v}), 1, "无法登记忽略", fmt="npm-audit")


if __name__ == "__main__":
    unittest.main(verbosity=1)
