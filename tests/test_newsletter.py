from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "personal-newsletter" / "scripts" / "newsletter.py"


def load_module():
    spec = importlib.util.spec_from_file_location("newsletter", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def temp_home():
    old_value = os.environ.get("PERSONAL_NEWSLETTER_HOME")
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["PERSONAL_NEWSLETTER_HOME"] = tmp
        try:
            yield Path(tmp)
        finally:
            if old_value is None:
                os.environ.pop("PERSONAL_NEWSLETTER_HOME", None)
            else:
                os.environ["PERSONAL_NEWSLETTER_HOME"] = old_value


class NewsletterTests(unittest.TestCase):
    def test_load_domain_and_merge_user_config(self):
        newsletter = load_module()
        with temp_home():
            config = newsletter.load_config()
            config["domains"] = {"ai": {"accounts": [{"handle": "custom_ai", "label": "Custom AI"}]}}

            accounts = newsletter.merged_accounts("ai", config)
            handles = {account.handle for account in accounts}

            self.assertIn("karpathy", handles)
            self.assertIn("custom_ai", handles)

    def test_build_digest_clusters_fixture_posts(self):
        newsletter = load_module()
        with temp_home():
            config = newsletter.load_config()
            accounts = newsletter.merged_accounts("ai", config)
            fixture = ROOT / "tests" / "fixtures" / "sample_posts.json"

            posts = newsletter.fixture_posts(fixture, accounts)
            digest = newsletter.build_digest("ai", posts, config, "zh-CN")

            self.assertEqual(digest["stats"]["posts"], 4)
            self.assertTrue(digest["topics"])
            self.assertTrue(any("karpathy" in topic["source_accounts"] for topic in digest["topics"]))

    def test_render_markdown_contains_source_links(self):
        newsletter = load_module()
        with temp_home():
            config = newsletter.load_config()
            accounts = newsletter.merged_accounts("ai", config)
            fixture = ROOT / "tests" / "fixtures" / "sample_posts.json"
            posts = newsletter.fixture_posts(fixture, accounts)
            digest = newsletter.build_digest("ai", posts, config, "en")

            markdown = newsletter.render_markdown(digest)

            self.assertIn("@karpathy", markdown)
            self.assertIn("https://x.com/karpathy/status/1001", markdown)
            self.assertIn("Source posts", markdown)

    def test_default_zh_markdown_translates_summary_body(self):
        newsletter = load_module()
        with temp_home():
            config = newsletter.load_config()
            accounts = newsletter.merged_accounts("ai", config)
            fixture = ROOT / "tests" / "fixtures" / "sample_posts.json"
            posts = newsletter.fixture_posts(fixture, accounts)
            digest = newsletter.build_digest("ai", posts, config, "zh-CN")

            markdown = newsletter.render_markdown(digest)

            self.assertIn("每日简报", markdown)
            self.assertIn("观点分布", markdown)
            self.assertIn("原帖链接", markdown)
            self.assertIn("智能体", markdown)
            self.assertNotIn("New AI agent workflows are getting much stronger", markdown)
            self.assertNotIn("The risk with agent demos", markdown)

    def test_cli_run_with_fixture(self):
        newsletter = load_module()
        with temp_home():
            fixture = ROOT / "tests" / "fixtures" / "sample_posts.json"
            output = io.StringIO()

            with contextlib.redirect_stdout(output):
                code = newsletter.main(["run", "ai", "--input-json", str(fixture), "--no-deliver"])

            payload = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "ok")
            self.assertTrue(Path(payload["json_path"]).exists())
            self.assertTrue(Path(payload["markdown_path"]).exists())


if __name__ == "__main__":
    unittest.main()
