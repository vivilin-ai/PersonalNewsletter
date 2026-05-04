#!/usr/bin/env python3
"""Personal newsletter CLI for curated X account pools."""

from __future__ import annotations

import argparse
import datetime as dt
import email.message
import html
import json
import os
import re
import shlex
import shutil
import smtplib
import subprocess
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DOMAINS_DIR = SKILL_DIR / "domains"

DEFAULT_CONFIG: dict[str, Any] = {
    "language": "zh-CN",
    "provider": "bird",
    "lookback_hours": 24,
    "posts_per_account": 8,
    "max_topics": 6,
    "delivery": {
        "kind": "none",
        "url": "",
    },
    "domains": {},
}

DOMAIN_ALIASES = {
    "ai": "ai",
    "artificial-intelligence": "ai",
    "us-stocks": "us-stocks",
    "stocks": "us-stocks",
    "us_stocks": "us-stocks",
    "market": "us-stocks",
    "markets": "us-stocks",
}

STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "have", "has",
    "are", "was", "were", "will", "you", "your", "they", "their", "about",
    "into", "over", "under", "than", "then", "there", "here", "what", "when",
    "where", "who", "why", "how", "not", "but", "all", "can", "just", "more",
    "new", "now", "today", "daily", "thread", "https", "com", "amp", "its",
    "it's", "our", "out", "via", "one", "two", "get", "got", "like", "make",
    "made", "use", "using", "also", "been", "after", "before", "because",
}

POSITIVE_WORDS = {
    "bull", "bullish", "breakthrough", "growth", "upside", "beat", "beats",
    "strong", "better", "improve", "improved", "launch", "record", "rally",
    "surge", "opportunity", "wins", "winner", "great", "good", "massive",
    "accelerate", "acceleration", "adoption",
}

SKEPTICAL_WORDS = {
    "bear", "bearish", "risk", "risks", "weak", "miss", "slowing", "slow",
    "bubble", "overvalued", "concern", "concerns", "problem", "problems",
    "fail", "fails", "failed", "warning", "warns", "pressure", "selloff",
    "crash", "fraud", "lawsuit", "delay", "delayed", "expensive",
}

ZH_TERM_MAP = {
    "agent": "智能体",
    "agents": "智能体",
    "workflow": "工作流",
    "workflows": "工作流",
    "tool": "工具",
    "tools": "工具",
    "memory": "记忆",
    "durable": "持久化",
    "eval": "评测",
    "evals": "评测",
    "benchmark": "基准测试",
    "benchmarks": "基准测试",
    "automation": "自动化",
    "reliable": "可靠性",
    "reliably": "可靠性",
    "recover": "失败恢复",
    "failed": "失败",
    "failure": "失败率",
    "rates": "失败率",
    "breakthrough": "突破",
    "model": "模型",
    "models": "模型",
    "open": "开放",
    "source": "开源",
    "local": "本地",
    "inference": "推理",
    "product": "产品",
    "surface": "产品形态",
    "apps": "应用",
    "ai": "AI",
    "llm": "大语言模型",
    "llms": "大语言模型",
    "strong": "强劲",
    "stronger": "更强",
    "improving": "持续改进",
    "risk": "风险",
    "risks": "风险",
    "demos": "演示",
    "calls": "调用",
    "useful": "实用性",
    "underrate": "被低估",
    "stock": "股票",
    "stocks": "股票",
    "market": "市场",
    "markets": "市场",
    "macro": "宏观",
    "fed": "美联储",
    "earnings": "财报",
    "inflation": "通胀",
    "rates": "利率",
    "equities": "美股",
    "options": "期权",
    "flows": "资金流",
    "rally": "上涨",
    "selloff": "抛售",
    "growth": "增长",
    "valuation": "估值",
    "liquidity": "流动性",
}


@dataclass
class Account:
    handle: str
    label: str = ""
    role: str = "custom"
    tier: str = "signal"
    weight: float = 0.7
    tags: list[str] = field(default_factory=list)
    rationale: str = ""
    source: str = "builtin"
    enabled: bool = True


@dataclass
class Post:
    id: str
    text: str
    url: str
    author_handle: str
    author_label: str = ""
    date: str = ""
    created_at: str = ""
    engagement: dict[str, int | None] = field(default_factory=dict)
    account_weight: float = 0.7
    account_tier: str = "signal"
    score: float = 0.0


def config_home() -> Path:
    configured = os.environ.get("PERSONAL_NEWSLETTER_HOME")
    if configured:
        return Path(configured).expanduser()
    return Path.cwd() / ".personal-newsletter"


def config_path() -> Path:
    return config_home() / "config.json"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base))
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    return deep_merge(DEFAULT_CONFIG, load_json(path))


def save_config(config: dict[str, Any]) -> None:
    write_json(config_path(), config)


def normalize_domain(value: str) -> str:
    key = value.strip().lower().replace("_", "-")
    if key not in DOMAIN_ALIASES:
        raise SystemExit(f"Unknown domain: {value}. Try: ai, us-stocks")
    return DOMAIN_ALIASES[key]


def domain_file(domain_id: str) -> Path:
    return DOMAINS_DIR / f"{domain_id.replace('-', '_')}.json"


def load_domain(domain_id: str) -> dict[str, Any]:
    domain_id = normalize_domain(domain_id)
    path = domain_file(domain_id)
    if not path.exists():
        raise SystemExit(f"Missing domain file: {path}")
    return load_json(path)


def account_from_dict(raw: dict[str, Any], source: str) -> Account:
    return Account(
        handle=str(raw["handle"]).lstrip("@"),
        label=str(raw.get("label") or raw["handle"]).strip(),
        role=str(raw.get("role") or "custom"),
        tier=str(raw.get("tier") or "signal"),
        weight=float(raw.get("weight", 0.7)),
        tags=[str(tag) for tag in raw.get("tags", [])],
        rationale=str(raw.get("rationale") or ""),
        source=source,
        enabled=bool(raw.get("enabled", True)),
    )


def merged_accounts(domain_id: str, config: dict[str, Any]) -> list[Account]:
    domain = load_domain(domain_id)
    accounts: dict[str, Account] = {}
    for raw in domain.get("accounts", []):
        account = account_from_dict(raw, "builtin")
        accounts[account.handle.lower()] = account

    user_domain = config.get("domains", {}).get(normalize_domain(domain_id), {})
    for handle in user_domain.get("disable", []):
        if str(handle).lstrip("@").lower() in accounts:
            accounts[str(handle).lstrip("@").lower()].enabled = False

    for raw in user_domain.get("accounts", []):
        account = account_from_dict(raw, "user")
        accounts[account.handle.lower()] = account

    for raw in user_domain.get("overrides", []):
        handle = str(raw.get("handle", "")).lstrip("@").lower()
        if handle in accounts:
            current = accounts[handle]
            data = {**current.__dict__, **raw}
            accounts[handle] = account_from_dict(data, current.source)

    return sorted(
        [account for account in accounts.values() if account.enabled],
        key=lambda item: (item.source != "builtin", -item.weight, item.handle.lower()),
    )


def since_date(lookback_hours: int) -> str:
    start = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=lookback_hours)
    return start.date().isoformat()


def run_subprocess(cmd: list[str], timeout: int = 40) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def bird_command() -> list[str] | None:
    if os.environ.get("PERSONAL_NEWSLETTER_BIRD_MJS"):
        mjs = os.environ["PERSONAL_NEWSLETTER_BIRD_MJS"]
        if shutil.which("node"):
            return ["node", mjs]
    if os.environ.get("PERSONAL_NEWSLETTER_BIRD_CMD"):
        return shlex.split(os.environ["PERSONAL_NEWSLETTER_BIRD_CMD"])
    if shutil.which("bird"):
        return ["bird"]
    return None


def fetch_with_bird(accounts: list[Account], lookback_hours: int, count: int) -> list[Post]:
    command = bird_command()
    if not command:
        raise RuntimeError("bird command not found. Install/authenticate bird or set PERSONAL_NEWSLETTER_BIRD_CMD.")

    posts: list[Post] = []
    start_date = since_date(lookback_hours)
    for account in accounts:
        query = f"from:{account.handle} since:{start_date}"
        raw = run_bird_search(command, query, count)
        posts.extend(normalize_posts(raw, account))
    return dedupe_posts(posts)


def run_bird_search(command: list[str], query: str, count: int) -> Any:
    if len(command) >= 2 and command[0] == "node":
        cmd = [*command, query, "--count", str(count), "--json"]
    else:
        cmd = [*command, "search", query, "-n", str(count), "--json"]

    result = run_subprocess(cmd)
    if result.returncode == 0 and result.stdout.strip():
        parsed = parse_json_maybe(result.stdout)
        if parsed is not None:
            return parsed

    if len(command) >= 2 and command[0] == "node":
        fallback_cmd = [*command, query, "--count", str(count)]
    else:
        fallback_cmd = [*command, "search", query, "-n", str(count)]

    fallback = run_subprocess(fallback_cmd)
    if fallback.returncode != 0:
        err = fallback.stderr.strip() or result.stderr.strip() or "bird search failed"
        raise RuntimeError(err)
    return parse_human_bird_output(fallback.stdout)


def parse_json_maybe(text: str) -> Any | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def parse_human_bird_output(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    url_re = re.compile(r"https?://(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/(\d+)")
    chunks = re.split(r"\n(?=@|\d+\.|\- |\*)", text)
    for chunk in chunks:
        match = url_re.search(chunk)
        if not match:
            continue
        handle, tweet_id = match.groups()
        cleaned = url_re.sub("", chunk)
        cleaned = re.sub(r"^\s*(?:\d+\.|\-|\*)\s*", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        items.append(
            {
                "id": tweet_id,
                "text": cleaned[:700],
                "url": f"https://x.com/{handle}/status/{tweet_id}",
                "author_handle": handle,
                "engagement": {},
            }
        )
    return items


def fixture_posts(path: Path, accounts: list[Account]) -> list[Post]:
    by_handle = {account.handle.lower(): account for account in accounts}
    raw = load_json(path)
    items = raw.get("items", raw.get("tweets", raw if isinstance(raw, list) else []))
    posts: list[Post] = []
    for item in items:
        handle = extract_handle(item) or ""
        account = by_handle.get(handle.lower(), Account(handle=handle, label=handle, source="fixture"))
        post = normalize_post(item, account)
        if post:
            posts.append(post)
    return dedupe_posts(posts)


def normalize_posts(raw: Any, account: Account) -> list[Post]:
    if isinstance(raw, dict):
        items = raw.get("items", raw.get("tweets", raw.get("data", [])))
    else:
        items = raw
    if not isinstance(items, list):
        return []
    return [post for item in items if (post := normalize_post(item, account))]


def normalize_post(item: dict[str, Any], account: Account) -> Post | None:
    if not isinstance(item, dict):
        return None
    text = str(
        item.get("text")
        or item.get("full_text")
        or item.get("content")
        or item.get("body")
        or ""
    ).strip()
    url = str(item.get("url") or item.get("permanent_url") or "")
    tweet_id = str(item.get("id") or item.get("tweet_id") or "")
    handle = extract_handle(item) or account.handle
    if not url and handle and tweet_id:
        url = f"https://x.com/{handle}/status/{tweet_id}"
    if not text and not url:
        return None

    engagement = normalize_engagement(item)
    created_at = str(item.get("createdAt") or item.get("created_at") or item.get("date") or "")
    date = parse_date(created_at)
    post = Post(
        id=tweet_id or url or f"{handle}:{hash(text)}",
        text=text[:1200],
        url=url,
        author_handle=handle.lstrip("@"),
        author_label=account.label or handle,
        date=date,
        created_at=created_at,
        engagement=engagement,
        account_weight=account.weight,
        account_tier=account.tier,
    )
    post.score = score_post(post)
    return post


def extract_handle(item: dict[str, Any]) -> str | None:
    author = item.get("author") or item.get("user") or {}
    if isinstance(author, dict):
        value = author.get("username") or author.get("screen_name") or author.get("handle")
        if value:
            return str(value).lstrip("@")
    for key in ("author_handle", "handle", "username", "screen_name"):
        if item.get(key):
            return str(item[key]).lstrip("@")
    url = str(item.get("url") or item.get("permanent_url") or "")
    match = re.search(r"(?:x|twitter)\.com/([A-Za-z0-9_]+)/status/", url)
    return match.group(1) if match else None


def normalize_engagement(item: dict[str, Any]) -> dict[str, int | None]:
    raw = item.get("engagement") if isinstance(item.get("engagement"), dict) else item
    mapping = {
        "likes": ("likes", "likeCount", "like_count", "favorite_count"),
        "reposts": ("reposts", "retweets", "retweetCount", "retweet_count"),
        "replies": ("replies", "replyCount", "reply_count"),
        "quotes": ("quotes", "quoteCount", "quote_count"),
        "views": ("views", "viewCount", "view_count"),
        "bookmarks": ("bookmarks", "bookmarkCount", "bookmark_count"),
    }
    engagement: dict[str, int | None] = {}
    for target, keys in mapping.items():
        value = next((raw.get(key) for key in keys if raw.get(key) is not None), None)
        engagement[target] = safe_int(value)
    return engagement


def safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_date(value: str) -> str:
    if not value:
        return ""
    try:
        if len(value) > 10 and value[10] == "T":
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        return dt.datetime.strptime(value, "%a %b %d %H:%M:%S %z %Y").date().isoformat()
    except ValueError:
        return value[:10] if re.match(r"\d{4}-\d{2}-\d{2}", value) else ""


def score_post(post: Post) -> float:
    likes = post.engagement.get("likes") or 0
    reposts = post.engagement.get("reposts") or 0
    replies = post.engagement.get("replies") or 0
    quotes = post.engagement.get("quotes") or 0
    views = post.engagement.get("views") or 0
    bookmarks = post.engagement.get("bookmarks") or 0
    tier_bonus = {"core": 25, "signal": 15, "edge": 8}.get(post.account_tier, 10)
    engagement_score = likes + reposts * 3 + replies * 2 + quotes * 4 + bookmarks * 3 + views / 500
    return round(engagement_score * max(post.account_weight, 0.1) + tier_bonus, 2)


def dedupe_posts(posts: list[Post]) -> list[Post]:
    seen: set[str] = set()
    result: list[Post] = []
    for post in sorted(posts, key=lambda item: item.score, reverse=True):
        key = post.url or f"{post.author_handle}:{post.text[:80]}"
        if key in seen:
            continue
        seen.add(key)
        result.append(post)
    return result


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_+\-.]{2,}", text.lower())
    return {word.strip(".-_") for word in words if word not in STOPWORDS and len(word) > 2}


def cluster_posts(posts: list[Post], max_topics: int) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for post in sorted(posts, key=lambda item: item.score, reverse=True):
        tokens = tokenize(post.text)
        if not tokens:
            tokens = {post.author_handle.lower()}
        best: dict[str, Any] | None = None
        best_overlap = 0
        for cluster in clusters:
            overlap = len(tokens & cluster["tokens"])
            if overlap > best_overlap:
                best = cluster
                best_overlap = overlap
        if best is not None and best_overlap >= 2:
            best["posts"].append(post)
            best["tokens"] |= tokens
            best["score"] += post.score
        else:
            clusters.append({"posts": [post], "tokens": set(tokens), "score": post.score})

    clusters = sorted(clusters, key=lambda item: item["score"], reverse=True)[:max_topics]
    topics: list[dict[str, Any]] = []
    for index, cluster in enumerate(clusters, start=1):
        top_posts = sorted(cluster["posts"], key=lambda item: item.score, reverse=True)
        topic_tokens = top_keywords(top_posts, limit=5)
        perspectives = build_perspectives(top_posts)
        topics.append(
            {
                "id": f"T{index}",
                "title": title_from_keywords(topic_tokens, top_posts[0]),
                "keywords": topic_tokens,
                "score": round(cluster["score"], 2),
                "source_accounts": sorted({post.author_handle for post in top_posts}),
                "posts": [post_to_dict(post) for post in top_posts[:8]],
                "perspectives": perspectives,
                "summary_seed": summarize_seed(top_posts),
            }
        )
    return topics


def top_keywords(posts: list[Post], limit: int) -> list[str]:
    counts: dict[str, float] = {}
    for post in posts:
        for token in tokenize(post.text):
            counts[token] = counts.get(token, 0.0) + max(post.score, 1.0) ** 0.5
    return [word for word, _ in sorted(counts.items(), key=lambda pair: pair[1], reverse=True)[:limit]]


def title_from_keywords(keywords: list[str], fallback: Post) -> str:
    if keywords:
        return " / ".join(word.upper() if len(word) <= 4 else word.title() for word in keywords[:3])
    return fallback.text[:64] or f"@{fallback.author_handle}"


def zh_keyword(word: str) -> str:
    normalized = word.lower().strip(".-_")
    if normalized in ZH_TERM_MAP:
        return ZH_TERM_MAP[normalized]
    if re.fullmatch(r"[A-Z]{2,6}", word):
        return word
    if re.search(r"[\u4e00-\u9fff]", word):
        return word
    return ""


def zh_keywords(words: list[str], limit: int = 5) -> list[str]:
    translated: list[str] = []
    for word in words:
        value = zh_keyword(word)
        if value and value not in translated:
            translated.append(value)
        if len(translated) >= limit:
            break
    return translated


def zh_topic_title(topic: dict[str, Any]) -> str:
    keywords = zh_keywords(topic.get("keywords", []), limit=3)
    if keywords:
        return " / ".join(keywords)
    accounts = "、".join(f"@{handle}" for handle in topic.get("source_accounts", [])[:2])
    return f"{accounts} 关注的热点"


def zh_topic_summary(topic: dict[str, Any]) -> str:
    accounts = "、".join(f"@{handle}" for handle in topic.get("source_accounts", [])[:4])
    keywords = zh_keywords(topic.get("keywords", []), limit=5)
    focus = "、".join(keywords) if keywords else "该领域的最新讨论"
    post_count = len(topic.get("posts", []))
    return f"{accounts} 等账号集中讨论了「{focus}」。该主题在账号池内出现 {post_count} 条相关内容，值得作为今天的重点信号跟踪。"


def zh_view_summary(view: dict[str, str], stance: str, topic: dict[str, Any]) -> str:
    keywords = zh_keywords(topic.get("keywords", []), limit=4)
    focus = "、".join(keywords) if keywords else "该主题"
    account = f"@{view['account']}"
    if stance == "supportive":
        return f"{account} 的观点偏积极，认为「{focus}」正在带来新的进展或机会。"
    if stance == "skeptical":
        return f"{account} 的观点偏谨慎，重点提醒「{focus}」仍存在可靠性、风险或验证不足的问题。"
    return f"{account} 主要提供了关于「{focus}」的事实观察和趋势信号。"


def classify_view(text: str) -> str:
    tokens = tokenize(text)
    if tokens & SKEPTICAL_WORDS:
        return "skeptical"
    if tokens & POSITIVE_WORDS:
        return "supportive"
    return "observational"


def build_perspectives(posts: list[Post]) -> dict[str, list[dict[str, str]]]:
    buckets = {"supportive": [], "skeptical": [], "observational": []}
    for post in posts:
        bucket = classify_view(post.text)
        if len(buckets[bucket]) >= 3:
            continue
        buckets[bucket].append(
            {
                "account": post.author_handle,
                "label": post.author_label,
                "text": trim_sentence(post.text),
                "url": post.url,
            }
        )
    return buckets


def trim_sentence(text: str, limit: int = 220) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def summarize_seed(posts: list[Post]) -> str:
    handles = ", ".join(f"@{post.author_handle}" for post in posts[:3])
    return f"{handles} discussed this cluster; top signal: {trim_sentence(posts[0].text, 180)}"


def post_to_dict(post: Post) -> dict[str, Any]:
    return {
        "id": post.id,
        "text": post.text,
        "url": post.url,
        "author_handle": post.author_handle,
        "author_label": post.author_label,
        "date": post.date,
        "created_at": post.created_at,
        "engagement": post.engagement,
        "score": post.score,
    }


def build_digest(domain_id: str, posts: list[Post], config: dict[str, Any], language: str) -> dict[str, Any]:
    domain = load_domain(domain_id)
    topics = cluster_posts(posts, int(config.get("max_topics", 6)))
    return {
        "schema_version": "0.1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "domain": {
            "id": normalize_domain(domain_id),
            "display_name": domain["display_name"],
            "description": domain["description"],
        },
        "language": language,
        "stats": {
            "posts": len(posts),
            "topics": len(topics),
            "accounts": len({post.author_handle.lower() for post in posts}),
        },
        "topics": topics,
    }


def render_markdown(digest: dict[str, Any]) -> str:
    language = digest.get("language", "zh-CN").lower()
    if language.startswith("en"):
        return render_markdown_en(digest)
    return render_markdown_zh(digest)


def render_markdown_zh(digest: dict[str, Any]) -> str:
    domain_name = digest["domain"]["display_name"]
    today = dt.datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# {domain_name} 每日简报 - {today}",
        "",
        f"今日从账号池中抓取 {digest['stats']['posts']} 条帖子，聚合出 {digest['stats']['topics']} 个热点主题。",
        "",
    ]
    if not digest["topics"]:
        lines.extend(["今天账号池内没有足够的新内容生成热点。", ""])
        return "\n".join(lines)

    lines.append("## 今日要点")
    for topic in digest["topics"]:
        accounts = ", ".join(f"@{handle}" for handle in topic["source_accounts"][:5])
        lines.append(f"- {zh_topic_title(topic)}: 引用账号 {accounts}")
    lines.append("")

    for topic in digest["topics"]:
        lines.extend([f"## {topic['id']}. {zh_topic_title(topic)}", "", zh_topic_summary(topic), ""])
        lines.append("观点分布:")
        for key, label in (
            ("supportive", "偏积极/支持"),
            ("skeptical", "偏谨慎/质疑"),
            ("observational", "中性观察"),
        ):
            views = topic["perspectives"].get(key, [])
            if views:
                rendered = "; ".join(zh_view_summary(view, key, topic) for view in views)
                lines.append(f"- {label}: {rendered}")
        lines.append("")
        lines.append("引用来源:")
        for post in topic["posts"][:5]:
            link = post["url"] or f"https://x.com/{post['author_handle']}"
            lines.append(f"- @{post['author_handle']}: 原帖链接 {link}")
        lines.append("")
    return "\n".join(lines)


def render_markdown_en(digest: dict[str, Any]) -> str:
    domain_name = digest["domain"]["display_name"]
    today = dt.datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# {domain_name} Daily Newsletter - {today}",
        "",
        f"Collected {digest['stats']['posts']} posts from the account pool and grouped them into {digest['stats']['topics']} hotspots.",
        "",
    ]
    if not digest["topics"]:
        lines.extend(["There was not enough new account-pool activity to build a meaningful issue.", ""])
        return "\n".join(lines)

    lines.append("## Brief")
    for topic in digest["topics"]:
        accounts = ", ".join(f"@{handle}" for handle in topic["source_accounts"][:5])
        lines.append(f"- {topic['title']}: cited accounts {accounts}")
    lines.append("")

    for topic in digest["topics"]:
        lines.extend([f"## {topic['id']}. {topic['title']}", "", topic["summary_seed"], ""])
        lines.append("Perspective map:")
        for key, label in (
            ("supportive", "Supportive"),
            ("skeptical", "Skeptical"),
            ("observational", "Observational"),
        ):
            views = topic["perspectives"].get(key, [])
            if views:
                rendered = "; ".join(f"@{view['account']}: {view['text']}" for view in views)
                lines.append(f"- {label}: {rendered}")
        lines.append("")
        lines.append("Source posts:")
        for post in topic["posts"][:5]:
            link = post["url"] or f"https://x.com/{post['author_handle']}"
            lines.append(f"- @{post['author_handle']}: {trim_sentence(post['text'], 180)} ({link})")
        lines.append("")
    return "\n".join(lines)


def output_paths(domain_id: str) -> tuple[Path, Path]:
    stamp = dt.datetime.now().strftime("%Y-%m-%d")
    out_dir = config_home() / "runs"
    return out_dir / f"{stamp}-{domain_id}.json", out_dir / f"{stamp}-{domain_id}.md"


def write_outputs(domain_id: str, digest: dict[str, Any], markdown: str) -> tuple[Path, Path]:
    json_path, md_path = output_paths(domain_id)
    write_json(json_path, digest)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def deliver(markdown: str, subject: str, config: dict[str, Any]) -> dict[str, Any]:
    delivery = config.get("delivery", {})
    kind = str(delivery.get("kind") or "none").lower()
    if kind == "none":
        return {"status": "skipped", "kind": "none"}
    if kind == "webhook":
        url = str(delivery.get("url") or "")
        if not url:
            return {"status": "failed", "kind": "webhook", "error": "delivery.url is empty"}
        return send_webhook(url, markdown, subject)
    if kind == "email":
        return send_email(markdown, subject)
    if kind == "telegram":
        return send_telegram(markdown)
    return {"status": "failed", "kind": kind, "error": f"Unsupported delivery kind: {kind}"}


def send_webhook(url: str, markdown: str, subject: str) -> dict[str, Any]:
    if "open.feishu.cn" in url or "larksuite" in url:
        payload = {"msg_type": "text", "content": {"text": markdown}}
    elif "hooks.slack.com" in url:
        payload = {"text": markdown}
    else:
        payload = {
            "source": "personal-newsletter",
            "subject": subject,
            "message": markdown,
            "text": markdown,
            "timestamp": time.time(),
        }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {"status": "sent", "kind": "webhook", "code": response.status}
    except urllib.error.URLError as exc:
        return {"status": "failed", "kind": "webhook", "error": str(exc)}


def send_telegram(markdown: str) -> dict[str, Any]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return {
            "status": "failed",
            "kind": "telegram",
            "error": "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, or use delivery.kind=webhook.",
        }
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": markdown[:4000], "disable_web_page_preview": True}
    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return {"status": "sent", "kind": "telegram", "code": response.status}
    except urllib.error.URLError as exc:
        return {"status": "failed", "kind": "telegram", "error": str(exc)}


def send_email(markdown: str, subject: str) -> dict[str, Any]:
    required = {
        "host": os.environ.get("NEWSLETTER_SMTP_HOST"),
        "port": os.environ.get("NEWSLETTER_SMTP_PORT", "587"),
        "user": os.environ.get("NEWSLETTER_SMTP_USER"),
        "password": os.environ.get("NEWSLETTER_SMTP_PASSWORD"),
        "from": os.environ.get("NEWSLETTER_EMAIL_FROM"),
        "to": os.environ.get("NEWSLETTER_EMAIL_TO"),
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        return {"status": "failed", "kind": "email", "error": f"Missing env: {', '.join(missing)}"}

    message = email.message.EmailMessage()
    message["Subject"] = subject
    message["From"] = required["from"]
    message["To"] = required["to"]
    message.set_content(markdown)
    message.add_alternative(markdown_to_html(markdown), subtype="html")

    try:
        with smtplib.SMTP(str(required["host"]), int(str(required["port"])), timeout=20) as smtp:
            smtp.starttls()
            smtp.login(str(required["user"]), str(required["password"]))
            smtp.send_message(message)
        return {"status": "sent", "kind": "email"}
    except Exception as exc:
        return {"status": "failed", "kind": "email", "error": str(exc)}


def markdown_to_html(markdown: str) -> str:
    body_lines: list[str] = []
    for line in markdown.splitlines():
        escaped = html.escape(line)
        if line.startswith("# "):
            body_lines.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_lines.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("- "):
            body_lines.append(f"<li>{html.escape(line[2:])}</li>")
        elif line.strip():
            body_lines.append(f"<p>{escaped}</p>")
        else:
            body_lines.append("")
    return "<html><body>" + "\n".join(body_lines) + "</body></html>"


def cmd_run(args: argparse.Namespace) -> None:
    config = load_config()
    domain_id = normalize_domain(args.domain)
    if args.language:
        language = args.language
    else:
        language = str(config.get("language") or load_domain(domain_id).get("default_language") or "zh-CN")

    accounts = merged_accounts(domain_id, config)
    if args.input_json:
        posts = fixture_posts(Path(args.input_json), accounts)
    else:
        posts = fetch_with_bird(
            accounts,
            int(args.lookback_hours or config.get("lookback_hours", 24)),
            int(args.posts_per_account or config.get("posts_per_account", 8)),
        )

    digest = build_digest(domain_id, posts, config, language)
    markdown = render_markdown(digest)
    json_path, md_path = write_outputs(domain_id, digest, markdown)

    delivery_result = {"status": "skipped", "kind": "none"}
    if not args.no_deliver:
        subject = f"{digest['domain']['display_name']} Daily Newsletter"
        delivery_result = deliver(markdown, subject, config)

    print(
        json.dumps(
            {
                "status": "ok",
                "domain": domain_id,
                "posts": digest["stats"]["posts"],
                "topics": digest["stats"]["topics"],
                "json_path": str(json_path),
                "markdown_path": str(md_path),
                "delivery": delivery_result,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def cmd_list_domains(_: argparse.Namespace) -> None:
    domains = []
    for path in sorted(DOMAINS_DIR.glob("*.json")):
        domain = load_json(path)
        domains.append(
            {
                "id": domain["domain_id"],
                "display_name": domain["display_name"],
                "accounts": len(domain.get("accounts", [])),
            }
        )
    print(json.dumps({"domains": domains}, ensure_ascii=False, indent=2))


def cmd_list_accounts(args: argparse.Namespace) -> None:
    config = load_config()
    accounts = [account.__dict__ for account in merged_accounts(args.domain, config)]
    print(json.dumps({"domain": normalize_domain(args.domain), "accounts": accounts}, ensure_ascii=False, indent=2))


def cmd_add_account(args: argparse.Namespace) -> None:
    config = load_config()
    domain_id = normalize_domain(args.domain)
    domain_config = config.setdefault("domains", {}).setdefault(domain_id, {})
    accounts = domain_config.setdefault("accounts", [])
    handle = args.handle.lstrip("@")
    accounts[:] = [item for item in accounts if str(item.get("handle", "")).lstrip("@").lower() != handle.lower()]
    accounts.append(
        {
            "handle": handle,
            "label": args.label or handle,
            "role": args.role or "custom",
            "tier": args.tier or "signal",
            "weight": args.weight,
            "tags": args.tag or [],
            "rationale": args.rationale or "User-added account.",
        }
    )
    save_config(config)
    print(json.dumps({"status": "added", "domain": domain_id, "handle": handle, "config": str(config_path())}))


def cmd_disable_account(args: argparse.Namespace) -> None:
    config = load_config()
    domain_id = normalize_domain(args.domain)
    domain_config = config.setdefault("domains", {}).setdefault(domain_id, {})
    disabled = domain_config.setdefault("disable", [])
    handle = args.handle.lstrip("@")
    if handle not in disabled:
        disabled.append(handle)
    save_config(config)
    print(json.dumps({"status": "disabled", "domain": domain_id, "handle": handle, "config": str(config_path())}))


def set_nested(config: dict[str, Any], dotted_key: str, value: str) -> None:
    cursor = config
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    parsed: Any = value
    if value.lower() in {"true", "false"}:
        parsed = value.lower() == "true"
    else:
        try:
            parsed = int(value)
        except ValueError:
            try:
                parsed = float(value)
            except ValueError:
                parsed = value
    cursor[parts[-1]] = parsed


def cmd_config(args: argparse.Namespace) -> None:
    config = load_config()
    if args.config_command == "show":
        print(json.dumps(config, ensure_ascii=False, indent=2))
        return
    set_nested(config, args.key, args.value)
    save_config(config)
    print(json.dumps({"status": "saved", "key": args.key, "value": args.value, "config": str(config_path())}))


def cmd_diagnose(_: argparse.Namespace) -> None:
    command = bird_command()
    has_auth_token = bool(os.environ.get("AUTH_TOKEN"))
    has_ct0 = bool(os.environ.get("CT0"))
    result: dict[str, Any] = {
        "config_path": str(config_path()),
        "config_exists": config_path().exists(),
        "bird_command": command,
        "bird_found": bool(command),
        "x_cookie_env": {
            "AUTH_TOKEN": has_auth_token,
            "CT0": has_ct0,
            "ready_for_headless_server": has_auth_token and has_ct0,
        },
        "auth_note": "Bird needs a logged-in browser session or AUTH_TOKEN/CT0 cookies. On servers, configure AUTH_TOKEN and CT0 as secrets.",
        "domains": [path.stem.replace("_", "-") for path in sorted(DOMAINS_DIR.glob("*.json"))],
    }
    if command and command[0] != "node":
        try:
            check = run_subprocess([*command, "check"], timeout=20)
            result["bird_check_returncode"] = check.returncode
            result["bird_check_output"] = (check.stdout or check.stderr).strip()[:800]
        except Exception as exc:
            result["bird_check_error"] = str(exc)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate personal newsletters from curated X account pools.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              newsletter.py run ai --no-deliver
              newsletter.py run us-stocks --language en
              newsletter.py add-account ai karpathy --label "Andrej Karpathy"
              newsletter.py config set delivery.kind webhook
              newsletter.py config set delivery.url https://example.com/webhook
            """
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run")
    run.add_argument("domain")
    run.add_argument("--language")
    run.add_argument("--lookback-hours", type=int)
    run.add_argument("--posts-per-account", type=int)
    run.add_argument("--input-json", help="Use a fixture JSON file instead of calling bird.")
    run.add_argument("--no-deliver", action="store_true")
    run.set_defaults(func=cmd_run)

    list_domains = sub.add_parser("list-domains")
    list_domains.set_defaults(func=cmd_list_domains)

    list_accounts = sub.add_parser("list-accounts")
    list_accounts.add_argument("domain")
    list_accounts.set_defaults(func=cmd_list_accounts)

    add = sub.add_parser("add-account")
    add.add_argument("domain")
    add.add_argument("handle")
    add.add_argument("--label")
    add.add_argument("--role")
    add.add_argument("--tier", choices=["core", "signal", "edge"], default="signal")
    add.add_argument("--weight", type=float, default=0.7)
    add.add_argument("--tag", action="append")
    add.add_argument("--rationale")
    add.set_defaults(func=cmd_add_account)

    disable = sub.add_parser("disable-account")
    disable.add_argument("domain")
    disable.add_argument("handle")
    disable.set_defaults(func=cmd_disable_account)

    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    config_show = config_sub.add_parser("show")
    config_show.set_defaults(func=cmd_config)
    config_set = config_sub.add_parser("set")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_set.set_defaults(func=cmd_config)

    diagnose = sub.add_parser("diagnose")
    diagnose.set_defaults(func=cmd_diagnose)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
        return 0
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
