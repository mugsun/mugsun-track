#!/usr/bin/env python3
"""track 仓专用：security.yml 的审查要求（代码质量官 9cf50f1 复核、清单 3.13）。
共享门禁本身的测试在 test_vuln_gate.py（共享文件）。"""
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "check_workflows", ROOT / "scripts/check-workflows.py")
check_workflows = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_workflows)


class SecurityWorkflow(unittest.TestCase):
    """security.yml 的审查要求（代码质量官 9cf50f1 复核）。"""
    text = (pathlib.Path(__file__).resolve().parent.parent
            / ".github/workflows/security.yml").read_text(encoding="utf-8")

    def test_notify_on_failure_or_cancelled(self):
        self.assertIn("if: (failure() || cancelled()) && github.event_name == 'schedule' "
                      "&& github.ref == 'refs/heads/main'", self.text)

    def test_every_checkout_drops_credentials(self):
        blocks = self.text.split("uses: actions/checkout@")[1:]
        self.assertGreaterEqual(len(blocks), 3)
        for b in blocks:
            head = b.split("\n      - ")[0]
            self.assertIn("persist-credentials: false", head)

    def test_gitleaks_runs_on_schedule_and_is_notified(self):
        job = self.text.split("\n  gitleaks:")[1].split("\n  notify:")[0]
        self.assertNotIn("\n    if:", job)
        self.assertIn("needs: [osv, audit, gitleaks]", self.text)
        self.assertIn("gitleaks 发现", self.text)


    def test_shared_gate_hash_verified_before_use(self):
        for job in ("\n  osv:", "\n  audit:"):
            body = self.text.split(job)[1]
            first = body.index("sha256sum -c scripts/vuln-gate.sha256")
            self.assertLess(first, body.index("scripts/vuln-gate.py"))

    def gate_audit_job(self):
        return self.text.split("\n  gate-audit:")[1].split("\n  gate-audit-notify:")[0]

    def test_gate_audit_on_push_and_pr(self):
        job = self.gate_audit_job()
        self.assertIn("if: github.event_name == 'push' || github.event_name == 'pull_request'", job)
        self.assertIn("fetch-depth: 0", job)
        self.assertIn("github.event.pull_request.base.sha || github.event.before", job)
        self.assertIn('BASE_SHA=$(git merge-base "$BASE_SHA" HEAD)', job)

    def test_gate_audit_prefers_base_copy(self):
        job = self.gate_audit_job()
        show = job.index('git show "${BASE_SHA}:scripts/gate-audit.py"')
        self.assertLess(show, job.index('python3 "$script" --base "$BASE_SHA"'))
        self.assertNotIn("python3 scripts/gate-audit.py", job)

    def test_gate_audit_bad_base_exits_before_head_script(self):  # 代码质量官 A2
        job = self.gate_audit_job()
        cp = job.index("cp scripts/gate-audit.py")
        for guard in ('*) echo "::error::base 全 0', 'git cat-file -e "${BASE_SHA}^{commit}"'):
            self.assertLess(job.index(guard), cp)
        head = job[:cp]
        self.assertGreaterEqual(head.count("exit 1"), 2)
        self.assertIn('git cat-file -e "${BASE_SHA}:scripts/gate-audit.py"', head)

    def test_gate_audit_first_introduction_is_red(self):
        job = self.gate_audit_job()
        fallback = job.split("cp scripts/gate-audit.py")[0].rsplit("else", 1)[1]
        self.assertIn("::error::", fallback)
        self.assertNotIn("::notice::", job)
        self.assertIn('if [ "$first" -eq 1 ]; then exit 1; fi', job)
        self.assertIn('exit "$rc"', job)

    def test_gate_audit_failure_opens_issue(self):  # 安全官 G1-3
        job = self.text.split("\n  gate-audit-notify:")[1].split("\n  # 清单 3.2")[0]
        self.assertIn("needs: [gate-audit]", job)
        self.assertIn("if: failure() && github.event_name == 'push' "
                      "&& github.ref == 'refs/heads/main'", job)
        perms = job.split("permissions:")[1].split("steps:")[0].split()
        self.assertEqual(perms, ["issues:", "write"])
        self.assertNotIn("actions/checkout", job)

    def test_self_tests_include_audit_and_mutation(self):
        osv = self.text.split("\n  osv:")[1].split("\n  audit:")[0]
        for t in ("test_vuln_gate.py", "test_gate_audit.py", "mutate_vuln_gate.py"):
            self.assertIn(f"python3 scripts/{t}", osv)

    def test_codeowners_marks_gate_files(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        co = (root / ".github/CODEOWNERS").read_text(encoding="utf-8")
        for pat in ("/scripts/vuln-gate*", "/scripts/test_vuln_gate.py", "/scripts/gate-audit.py",
                    "/scripts/test_gate_audit.py", "/scripts/mutate_vuln_gate.py",
                    "/.github/workflows/", "/.gitleaks.toml", "/.gitleaksignore",
                    "/.github/CODEOWNERS"):
            self.assertIn(f"{pat} @mugsun", co)

    def test_branch_push_uses_merge_base_with_main(self):  # 清单 3.16
        job = self.gate_audit_job()
        branch = job.index('if [ "$EVENT" = push ] && [ "$REF" != refs/heads/main ]; then')
        mb = job.index("BASE_SHA=$(git merge-base origin/main HEAD)")
        zero = job.index('*) echo "::error::base 全 0')
        self.assertLess(branch, mb)
        self.assertLess(mb, zero)  # 先换成 merge-base，再走 A2 的全 0 / 不可达检查
        self.assertIn("算不出和 origin/main 的 merge-base", job[mb:zero])
        self.assertIn("exit 1", job[mb:zero])
        self.assertIn("REF: ${{ github.ref }}", job)


class Triggers(unittest.TestCase):
    """清单 3.16：分支先绿再进 main。ci.yml 和 security.yml 推任意分支都跑。"""

    def wf(self, name):
        return (ROOT / ".github/workflows" / name).read_text(encoding="utf-8")

    def test_push_any_branch_pr_and_dispatch(self):
        for name in ("ci.yml", "security.yml"):
            on = self.wf(name).split("\non:\n")[1].split("\n\n")[0]
            with self.subTest(name=name):
                self.assertIn("  push:\n    branches: ['**']", on)
                self.assertIn("  pull_request:\n    branches: [main]", on)
                self.assertIn("  workflow_dispatch:", on)

    def test_concurrency_cancels_old_runs_except_main(self):
        for name in ("ci.yml", "security.yml"):
            with self.subTest(name=name):
                t = self.wf(name)
                self.assertIn("\nconcurrency:\n  group: ${{ github.workflow }}-${{ github.event_name }}"
                              "-${{ github.ref }}\n  cancel-in-progress: ${{ github.ref != "
                              "'refs/heads/main' }}", t)

    def test_release_still_main_only(self):
        t = self.wf("release.yml")
        self.assertIn("  push:\n    branches: [main]\n    paths: [package.json]", t)

    def test_changelog_branch_push_uses_merge_base(self):
        job = self.wf("ci.yml").split("\n  changelog:")[1].split("\n  build:")[0]
        self.assertIn("fetch-depth: 0", job)
        self.assertIn("BASE=$(git merge-base origin/main HEAD)", job)
        self.assertIn('[ "$REF" != refs/heads/main ]', job)


class CheckWorkflows(unittest.TestCase):
    """check-workflows.py 的规则 5、6（清单 3.16）。"""
    BASE = ("name: x\non:\n  push:\n    branches: ['**']\npermissions:\n  contents: read\n"
            "{conc}jobs:\n  n:\n    {cond}runs-on: ubuntu-latest\n    permissions:\n"
            "      issues: write\n    steps:\n      - run: true\n")
    CONC = "concurrency:\n  group: g\n"
    MAIN = "if: failure() && github.ref == 'refs/heads/main'\n    "

    def errs(self, text):
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / "w.yml"
            f.write_text(text, encoding="utf-8")
            return check_workflows.check(f)

    def test_ok(self):
        self.assertEqual(self.errs(self.BASE.format(conc=self.CONC, cond=self.MAIN)), [])

    def test_push_without_concurrency(self):
        e = self.errs(self.BASE.format(conc="", cond=self.MAIN))
        self.assertTrue(any("缺少顶层 concurrency" in x for x in e), e)

    def test_issues_write_without_main_guard(self):
        for cond in ("", "if: failure()\n    "):
            e = self.errs(self.BASE.format(conc=self.CONC, cond=cond))
            self.assertTrue(any("refs/heads/main" in x for x in e), (cond, e))

    def test_repo_workflows_pass(self):
        for f in sorted((ROOT / ".github/workflows").glob("*.yml")):
            with self.subTest(f=f.name):
                self.assertEqual(check_workflows.check(f), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
