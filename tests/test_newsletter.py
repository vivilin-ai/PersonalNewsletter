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
            topic = digest["topics"][0]
            self.assertIn("analysis", topic)
            self.assertIn("tags", topic)
            self.assertIn("topics", topic["tags"])
            self.assertIn("quality", topic)

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
            self.assertIn("引用来源", markdown)
            self.assertIn("https://x.com/karpathy/status/1001", markdown)
            self.assertIn("智能体", markdown)
            self.assertNotIn("New AI agent workflows are getting much stronger", markdown)
            self.assertNotIn("The risk with agent demos", markdown)
            self.assertNotIn("该领域的最新讨论", markdown)
            self.assertNotIn("该主题", markdown)
            self.assertNotIn("各方观点与信号", markdown)

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

    def test_low_signal_digest_does_not_force_topics(self):
        newsletter = load_module()
        with temp_home():
            config = newsletter.load_config()
            posts = [
                newsletter.Post(
                    id="1",
                    text="nice!",
                    url="https://x.com/example/status/1",
                    author_handle="example",
                    score=10,
                )
            ]

            digest = newsletter.build_digest("ai", posts, config, "zh-CN")
            markdown = newsletter.render_markdown(digest)

            self.assertEqual(digest["quality"]["status"], "low_signal")
            self.assertEqual(digest["topics"], [])
            self.assertIn("未强行生成热点", markdown)

    def test_single_account_low_feedback_topic_is_filtered(self):
        newsletter = load_module()
        with temp_home():
            config = newsletter.load_config()
            posts = [
                newsletter.Post(
                    id="1",
                    text="Open source models keep improving. Strong local inference changes the product surface for AI apps.",
                    url="https://x.com/natfriedman/status/1",
                    author_handle="natfriedman",
                    author_label="Nat Friedman",
                    engagement={"likes": 500, "reposts": 50, "replies": 20, "quotes": 5},
                    score=500,
                ),
                newsletter.Post(
                    id="2",
                    text="New AI agent workflows are getting much stronger. Durable memory and eval loops matter.",
                    url="https://x.com/karpathy/status/2",
                    author_handle="karpathy",
                    author_label="Andrej Karpathy",
                    engagement={"likes": 500, "reposts": 50, "replies": 150, "quotes": 0},
                    score=500,
                ),
            ]

            digest = newsletter.build_digest("ai", posts, config, "zh-CN")
            titles = [topic["analysis"]["title_zh"] for topic in digest["topics"]]

            self.assertEqual(len(digest["topics"]), 1)
            self.assertTrue(any("智能体" in title for title in titles))

    def test_compact_markdown_collapses_same_account_posts(self):
        newsletter = load_module()
        with temp_home():
            config = newsletter.load_config()
            posts = [
                newsletter.Post(
                    id="1",
                    text="DeepSeek V4 Beats Opus 4.7 And GPT 5.5 To Become The World's Best Open Source Model.",
                    url="https://x.com/bindureddy/status/1",
                    author_handle="bindureddy",
                    author_label="Bindu Reddy",
                    engagement={"likes": 500, "reposts": 50, "replies": 150, "quotes": 0},
                    score=500,
                ),
                newsletter.Post(
                    id="2",
                    text="Gemini is overdue. Expect a really good Flash model that beats GPT 5.5 but is cheaper and faster.",
                    url="https://x.com/bindureddy/status/2",
                    author_handle="bindureddy",
                    author_label="Bindu Reddy",
                    engagement={"likes": 300, "reposts": 20, "replies": 20, "quotes": 0},
                    score=300,
                ),
            ]

            digest = newsletter.build_digest("ai", posts, config, "zh-CN")
            markdown = newsletter.render_markdown(digest)

            self.assertIn("他预期 Gemini", markdown)
            self.assertIn("@bindureddy（2条", markdown)
            self.assertNotIn("各方观点与信号", markdown)

    def test_trend_reads_recent_structured_runs(self):
        newsletter = load_module()
        with temp_home() as home:
            config = newsletter.load_config()
            accounts = newsletter.merged_accounts("ai", config)
            fixture = ROOT / "tests" / "fixtures" / "sample_posts.json"
            posts = newsletter.fixture_posts(fixture, accounts)
            digest = newsletter.build_digest("ai", posts, config, "zh-CN")
            today = newsletter.dt.date.today()
            runs = home / "runs"
            newsletter.write_json(runs / f"{today.isoformat()}-ai.json", digest)
            newsletter.write_json(runs / f"{(today - newsletter.dt.timedelta(days=1)).isoformat()}-ai.json", digest)

            report = newsletter.build_trend_report("ai", 7)
            markdown = newsletter.render_trend_markdown(report)

            self.assertEqual(report["runs"], 2)
            self.assertGreater(report["stats"]["topics"], 0)
            self.assertIn("高频标签", markdown)
            self.assertIn("agentic-ai", markdown)

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
