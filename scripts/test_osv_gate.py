#!/usr/bin/env python3
"""osv-gate.py 自测（fixture 正例 + 反例）。用法：python3 scripts/test_osv_gate.py"""
import datetime as dt
import importlib.util
import json
import pathlib
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "osv_gate", pathlib.Path(__file__).with_name("osv-gate.py"))
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)

TODAY = dt.date(2026, 10, 21)


def pkg(name, ver, vid, sev, fixed=None):
    events = [{"introduced": "0"}] + ([{"fixed": fixed}] if fixed else [])
    return {"package": {"name": name, "version": ver, "ecosystem": "npm"},
            "groups": [{"ids": [vid], "aliases": [vid], "max_severity": sev}],
            "vulnerabilities": [{"id": vid, "affected": [
                {"package": {"name": name, "ecosystem": "npm"},
                 "ranges": [{"type": "SEMVER", "events": events}]}]}]}


def doc(*pkgs):
    return {"results": [{"source": {"path": "pnpm-lock.yaml"}, "packages": list(pkgs)}]}


ESBUILD_LOW = pkg("esbuild", "0.27.7", "GHSA-g7r4-m6w7-qqqr", "2.5", "0.28.1")


class Tmp:
    def __init__(self):
        self.d = tempfile.TemporaryDirectory()

    def file(self, name, text):
        p = pathlib.Path(self.d.name) / name
        p.write_text(text, encoding="utf-8")
        return str(p)


class Results(unittest.TestCase):
    def setUp(self):
        self.t = Tmp()
        self.addCleanup(self.t.d.cleanup)

    def run_doc(self, data, rc, raw=None):
        path = self.t.file("o.json", raw if raw is not None else json.dumps(data))
        return gate.check_results(path, rc)

    # 1. results 缺失 / null / 非列表 / error 字段
    def test_clean_rc0_ok(self):
        self.assertEqual(self.run_doc({"results": []}, 0), ([], []))

    def test_results_missing(self):
        e, _ = self.run_doc({}, 0)
        self.assertIn("缺少 results", e[0])

    def test_results_null(self):
        e, _ = self.run_doc({"results": None}, 0)
        self.assertIn("不是列表", e[0])

    def test_results_not_list(self):
        e, _ = self.run_doc({"results": {"a": 1}}, 1)
        self.assertIn("不是列表", e[0])

    def test_top_level_error(self):
        e, _ = self.run_doc({"results": [], "error": "boom"}, 0)
        self.assertIn("error 字段", e[0])

    def test_result_entry_error(self):
        e, _ = self.run_doc({"results": [{"error": "x"}]}, 1)
        self.assertIn("results 条目异常", e[0])

    def test_invalid_json(self):
        e, _ = self.run_doc(None, 1, raw="{not json")
        self.assertIn("读不了", e[0])

    # 2. 退出码
    def test_tool_error_rc(self):
        for rc in (2, 127, 128, -1):
            e, _ = self.run_doc({"results": []}, rc)
            self.assertIn("工具出错", e[0], rc)

    def test_rc1_without_vulns_incomplete(self):
        e, _ = self.run_doc({"results": []}, 1)
        self.assertTrue(any("JSON 不完整" in x for x in e))

    def test_rc0_with_vulns_inconsistent(self):
        e, _ = self.run_doc(doc(ESBUILD_LOW), 0)
        self.assertTrue(any("不一致" in x for x in e))

    def test_rc1_low_only_ok(self):
        e, w = self.run_doc(doc(ESBUILD_LOW), 1)
        self.assertEqual(e, [])
        self.assertEqual(len(w), 1)

    # 3. High/Critical：有修复、修复超范围、无修复都失败
    def test_high_fix_in_range_fails(self):
        e, _ = self.run_doc(doc(pkg("nanoid", "3.3.17", "GHSA-a", "8.2", "3.3.18")), 1)
        self.assertIn("可在现有范围内升级", e[0])

    def test_high_no_fix_unregistered_fails(self):
        e, _ = self.run_doc(doc(pkg("x", "1.0.0", "GHSA-b", "9.8")), 1)
        self.assertIn("未登记在 osv-scanner.toml", e[0])

    def test_high_fix_out_of_range_fails(self):
        e, _ = self.run_doc(doc(pkg("x", "1.0.0", "GHSA-c", "7.0", "2.0.0")), 1)
        self.assertIn("修复版本超出依赖范围", e[0])

    def test_no_score_treated_as_high(self):
        e, _ = self.run_doc(doc(pkg("x", "1.0.0", "GHSA-d", "")), 1)
        self.assertEqual(len(e), 1)

    def test_medium_only_warns(self):
        e, w = self.run_doc(doc(pkg("x", "1.0.0", "GHSA-e", "6.9", "1.0.1")), 1)
        self.assertEqual(e, [])
        self.assertIn("可在现有范围内升级", w[0])

    # 6. 告警文案
    def test_esbuild_out_of_range_wording(self):
        _, w = self.run_doc(doc(ESBUILD_LOW), 1)
        self.assertIn("修复版本超出依赖范围（修复于 0.28.1）", w[0])

    def test_zero_major_same_minor_in_range(self):
        _, w = self.run_doc(doc(pkg("esbuild", "0.27.7", "GHSA-f", "2.5", "0.27.9")), 1)
        self.assertIn("可在现有范围内升级", w[0])

    def test_no_fix_wording(self):
        _, w = self.run_doc(doc(pkg("x", "1.0.0", "GHSA-g", "4.0")), 1)
        self.assertIn("无修复版本", w[0])


class Config(unittest.TestCase):
    def setUp(self):
        self.t = Tmp()
        self.addCleanup(self.t.d.cleanup)

    def check(self, text):
        return gate.check_config(self.t.file("c.toml", text), today=TODAY)

    GOOD = ('[[IgnoredVulns]]\nid = "GHSA-x"\nadded = 2026-10-21\n'
            'ignoreUntil = 2027-01-19\nreason = "无修复版本"\n')

    def test_empty_ok(self):
        self.assertEqual(self.check("# only comments\n"), ([], []))

    def test_good_entry_ok_and_effective_drops_added(self):
        e, entries = self.check(self.GOOD)
        self.assertEqual(e, [])
        out = self.t.file("eff.toml", "")
        gate.write_effective(entries, out)
        text = pathlib.Path(out).read_text(encoding="utf-8")
        self.assertNotIn("added", text.replace("去掉 added", ""))
        self.assertIn("ignoreUntil = 2027-01-19T00:00:00Z", text)

    # 4. added 必填，90 天从 added 算
    def test_missing_added(self):
        e, _ = self.check(self.GOOD.replace("added = 2026-10-21\n", ""))
        self.assertIn("缺少 added", e[0])

    def test_over_90_days_from_added(self):
        e, _ = self.check(self.GOOD.replace("2027-01-19", "2027-01-20"))
        self.assertTrue(any("超过 90 天" in x for x in e))

    def test_90_days_from_added_not_today(self):
        # added 早于今天：今天起算不到 90 天，但从 added 算已超过
        e, _ = self.check(self.GOOD.replace("added = 2026-10-21", "added = 2026-09-01")
                          .replace("2027-01-19", "2026-12-15"))
        self.assertTrue(any("超过 90 天" in x for x in e))

    def test_expired(self):
        e, _ = self.check(self.GOOD.replace("added = 2026-10-21", "added = 2026-08-01")
                          .replace("2027-01-19", "2026-10-20"))
        self.assertTrue(any("过期" in x for x in e))

    def test_missing_reason(self):
        e, _ = self.check(self.GOOD.replace('reason = "无修复版本"\n', ""))
        self.assertIn("缺少 reason", e[0])

    # 5. 字符串 / 格式错误的日期给出清楚报错，不崩
    def test_quoted_date(self):
        e, _ = self.check(self.GOOD.replace("ignoreUntil = 2027-01-19", 'ignoreUntil = "2027-01-19"'))
        self.assertTrue(any("写成了字符串" in x and "不要加引号" in x for x in e))

    def test_quoted_bad_format(self):
        e, _ = self.check(self.GOOD.replace("added = 2026-10-21", 'added = "21/10/2026"'))
        self.assertTrue(any("应为 YYYY-MM-DD" in x for x in e))

    def test_number_date(self):
        e, _ = self.check(self.GOOD.replace("added = 2026-10-21", "added = 20261021"))
        self.assertTrue(any("类型不对" in x for x in e))

    def test_invalid_toml(self):
        e, _ = self.check("[[IgnoredVulns]\nid=")
        self.assertIn("TOML 解析失败", e[0])

    def test_unknown_key(self):
        e, _ = self.check(self.GOOD + 'severity = "low"\n')
        self.assertTrue(any("不认识的键" in x for x in e))


if __name__ == "__main__":
    unittest.main(verbosity=1)
