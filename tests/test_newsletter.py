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
            self.assertIn("各方观点与信号", markdown)
            self.assertIn("引用来源", markdown)
            self.assertIn("原帖链接", markdown)
            self.assertIn("智能体", markdown)
            self.assertNotIn("New AI agent workflows are getting much stronger", markdown)
            self.assertNotIn("The risk with agent demos", markdown)
            self.assertNotIn("该领域的最新讨论", markdown)
            self.assertNotIn("该主题", markdown)

    def test_cluster_keeps_weakly_related_posts_separate(self):
        newsletter = load_module()
        posts = [
            newsletter.Post(
                id="1",
                text=(
                    "This could have covered the entire budget of the National Science Foundation for 10 years. "
                    "Reducing the NSF budget would damage American scientific research and PhD graduates."
                ),
                url="https://x.com/ylecun/status/1",
                author_handle="ylecun",
                score=80,
            ),
            newsletter.Post(
                id="2",
                text=(
                    "Meta is planning to power its AI data centers with solar energy beamed from space. "
                    "If it works, solar farms could produce power 24/7 without batteries."
                ),
                url="https://x.com/rowancheung/status/2",
                author_handle="rowancheung",
                score=70,
            ),
        ]

        topics = newsletter.cluster_posts(posts, max_topics=6)

        self.assertEqual(len(topics), 2)
        self.assertTrue(any(topic["source_accounts"] == ["ylecun"] for topic in topics))
        self.assertTrue(any(topic["source_accounts"] == ["rowancheung"] for topic in topics))

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

    def test_date_window(self):
        newsletter = load_module()

        self.assertEqual(newsletter.date_window("2026-05-04"), ("2026-05-04", "2026-05-05"))


if __name__ == "__main__":
    unittest.main()
