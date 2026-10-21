#!/usr/bin/env python3
"""track 仓专用：security.yml 的审查要求（代码质量官 9cf50f1 复核、清单 3.13）。
共享门禁本身的测试在 test_vuln_gate.py（共享文件）。"""
import pathlib
import unittest


class SecurityWorkflow(unittest.TestCase):
    """security.yml 的审查要求（代码质量官 9cf50f1 复核）。"""
    text = (pathlib.Path(__file__).resolve().parent.parent
            / ".github/workflows/security.yml").read_text(encoding="utf-8")

    def test_notify_on_failure_or_cancelled(self):
        self.assertIn("if: (failure() || cancelled()) && github.event_name == 'schedule'", self.text)

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


if __name__ == "__main__":
    unittest.main(verbosity=1)
