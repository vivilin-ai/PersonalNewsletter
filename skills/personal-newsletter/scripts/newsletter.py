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
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DOMAINS_DIR = SKILL_DIR / "domains"
WORKSPACE_DIR = SKILL_DIR.parent.parent
VENDORED_BIRD_MJS = SCRIPT_DIR / "vendor" / "bird-search" / "bird-search.mjs"

DEFAULT_CONFIG: dict[str, Any] = {
    "language": "zh-CN",
    "provider": "bird",
    "lookback_hours": 24,
    "posts_per_account": 8,
    "max_topics": 6,
    "hotspots": {
        "expert_handles_path": "data/x-lists/swyx_ai_high_signal_expert_handles_v1.json",
        "category_experts_path": "data/x-lists/swyx_ai_high_signal_expert_categories_v1.json",
        "discovery_handles_path": "data/x-lists/swyx_ai_high_signal_handles.json",
        "exclude_handles": [],
        "max_topics": 8,
        "expert_validation_accounts_per_run": 14,
        "core_experts_per_run": 16,
        "signal_experts_per_run": 6,
        "discovery_accounts_per_run": 12,
        "expert_posts_per_account": 3,
        "discovery_posts_per_account": 2,
        "keyword_posts_per_query": 8,
        "keyword_queries": [
            "(launch OR released OR announced) (model OR multimodal OR embedding OR open weights)",
            "(benchmark OR eval OR leaderboard) (released OR introduced OR saturating OR hard)",
            "(training OR optimizer OR scaling law OR post-training) (record OR released OR improves OR faster)",
            "(inference OR serving OR GPU OR throughput OR latency) (benchmark OR released OR improves OR cost)",
            "(agent runtime OR agent harness OR MCP OR tool use OR computer use) (released OR open-sourced OR SDK OR paper)",
            "(launched OR open-sourced OR GitHub OR YC OR funding) (AI OR agent OR developer tool)",
            "(AI OR agent) (reorg OR team OR hiring OR layoffs OR workflow OR entry-level jobs)",
            "(prompt injection OR supply chain OR vulnerability OR jailbreak OR secrets) (agent OR LLM OR AI)",
        ],
    },
    "quality": {
        "min_substantive_posts": 2,
        "min_topic_score": 18,
        "min_single_account_replies": 100,
    },
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
    "something", "hope", "nice", "sorry", "read", "source", "via", "latest",
    "newsletter", "break", "free", "every", "others", "funny", "simultaneously",
    "argued", "knowledge", "speak", "merely", "mean",
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

KNOWN_TOPIC_RULES: list[tuple[tuple[str, ...], str]] = [
    (
        ("agent workflows", "durable memory", "eval loops"),
        "AI 智能体工作流正在变强，关键不只是工具调用，而是持久化记忆和评测闭环。",
    ),
    (
        ("recover from failed tool calls", "better evals"),
        "智能体要真正有用，必须能从工具调用失败中恢复；更好的评测体系是被低估的突破点。",
    ),
    (
        ("agent demos", "failure rates", "benchmarks"),
        "对智能体演示的质疑集中在失败率被隐藏，真正可靠的自动化还需要更强基准测试验证。",
    ),
    (
        ("open source models", "local inference"),
        "开源模型和本地推理能力持续提升，正在改变 AI 应用的产品形态。",
    ),
    (
        ("gpt-5.5 party", "didn't have space"),
        "OpenAI 可能会给申请 GPT-5.5 party 但没拿到名额的人提供后续安排或补偿。",
    ),
    (
        ("not yet", "coming soon"),
        "Sam Altman 表示相关功能或活动还没有上线，但很快会来。",
    ),
    (
        ("much more to come",),
        "Sam Altman 暗示后面还会有更多发布、活动或产品动作。",
    ),
    (
        ("may this energy",),
        "Sam Altman 对某个积极势头表示认同，希望这种状态扩散。",
    ),
    (
        ("tool", "claude", "anthropic", "refuse"),
        "围绕 Claude 是否应服从 Anthropic 或人类指令，讨论焦点是 AI 应该是可控工具，还是应保留拒绝能力。",
    ),
    (
        ("when i say", "tool", "does not refuse"),
        "关于“AI 是工具还是主体”的争论中，Aidan McLaughlin 认为工具的核心是不会任意拒绝人类，但仍可因法律或公司政策推回请求。",
    ),
    (
        ("deepseek v4", "best open source model"),
        "Bindu Reddy 称 DeepSeek V4 已成为最强开源模型，并认为它在成本、速度和能力上压过部分闭源模型。",
    ),
    (
        ("gemini", "flash", "cheaper", "faster"),
        "Bindu Reddy 预期 Gemini 会推出更强的 Flash 模型，主打比 GPT-5.5 或 Opus 4.7 更便宜、更快。",
    ),
    (
        ("overfit", "closed expensive model", "open source models"),
        "Bindu Reddy 认为很多团队过度绑定昂贵闭源模型，应尽快适配 Kimi、DeepSeek 等开源模型，否则会被淘汰。",
    ),
    (
        ("livebench", "gpt 5.5"),
        "Bindu Reddy 用 LiveBench 排名质疑 GPT-5.5 medium 的表现，认为它并不领先。",
    ),
    (
        ("national science foundation", "trump", "reduce the nsf budget"),
        "Yann LeCun 批评削减 NSF 预算会伤害美国科研生态、博士培养和技术创新飞轮。",
    ),
    (
        ("meta", "solar energy", "space"),
        "Rowan Cheung 关注 Meta 计划用太空太阳能为 AI 数据中心供电，核心看点是 24/7 供电和 AI 算力能源需求。",
    ),
    (
        ("oai", "valuation", "arr", "ant"),
        "swyx 对比 OpenAI 与另一家 AI 公司的估值和 ARR，并提醒两者收入确认口径不同，直接比较会失真。",
    ),
]

COMPANY_PATTERNS: list[tuple[str, str]] = [
    (r"\bopenai\b|\boai\b", "openai"),
    (r"\banthropic\b", "anthropic"),
    (r"\bgoogle\b|\bgoogle deepmind\b", "google-deepmind"),
    (r"\bdeepmind\b", "google-deepmind"),
    (r"\bmeta\b|\bfacebook\b", "meta"),
    (r"\bxai\b|\bx\.ai\b|\bx-ai\b", "x-ai"),
    (r"\bdeepseek\b", "deepseek"),
    (r"\bmoonshot\b|\bkimi\b", "moonshot-ai"),
    (r"\balibaba\b|\bqwen\b", "alibaba"),
    (r"\bmistral\b", "mistral-ai"),
    (r"\bnvidia\b", "nvidia"),
    (r"\bmicrosoft\b|\bgithub\b|\bcopilot\b", "microsoft"),
    (r"\bcursor\b", "cursor-ai"),
    (r"\blangchain\b", "langchain-ai"),
    (r"\bhugging ?face\b", "hugging-face"),
]

MODEL_PATTERNS: list[tuple[str, str]] = [
    (r"\bgpt[-\s]?5\.5\b", "gpt-5.5"),
    (r"\bgpt[-\s]?5\.4\b", "gpt-5.4"),
    (r"\bgpt[-\s]?4o\b", "gpt-4o"),
    (r"\bclaude opus 4\.7\b|\bopus 4\.7\b", "claude-opus-4.7"),
    (r"\bclaude\b", "claude"),
    (r"\bgemini\b", "gemini"),
    (r"\bgemini.*flash|\bflash model\b", "gemini-flash"),
    (r"\bdeepseek v4\b|\bdeepseek-v4\b", "deepseek-v4"),
    (r"\bkimi k2\.6\b|\bkimi\b", "kimi-k2.6"),
    (r"\bqwen[-\s]?\d|\bqwen\b", "qwen"),
    (r"\bllama[-\s]?\d|\bllama\b", "llama"),
    (r"\bgemma[-\s]?\d|\bgemma\b", "gemma"),
]

TOPIC_PATTERNS: list[tuple[str, str]] = [
    (r"\bagent|agentic|tool call|tool-use|workflow|automation\b", "agentic-ai"),
    (r"\beval|benchmark|livebench|swe-bench|terminal-bench|leaderboard\b", "benchmarking"),
    (r"\bopen source|open-source|open weight|open-weight|local inference\b", "open-models"),
    (r"\binference|latency|token|cost|cheaper|faster|pricing\b", "cost-efficiency"),
    (r"\bcontext window|long context|1m context|million token\b", "long-context"),
    (r"\bmemory|durable memory|persistent context\b", "memory"),
    (r"\bdata center|energy|solar|power|gpu|tpu|blackwell\b", "ai-infrastructure"),
    (r"\bsafety|refuse|policy|law|alignment\b", "model-safety"),
    (r"\bresearch|nsf|science|phd|academic\b", "research-policy"),
    (r"\bvaluation|arr|revenue|earnings|stock|market\b", "business"),
    (r"\bmultimodal|vision|image|audio|video\b", "multimodality"),
    (r"\bcoding|code|codex|copilot|software\b", "coding"),
]

HOTSPOT_CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "foundation_models",
        "label_zh": "基座模型",
        "label_en": "Foundation Models",
        "patterns": [
            r"\bfrontier model|foundation model|base model|open model|open-weight|open weight\b",
            r"\bgpt|claude|gemini|deepseek|qwen|kimi|llama|mistral|grok|opus|sonnet\b",
            r"\bmultimodal|vision-language|embedding|retrieval model|long context|reasoning model\b",
        ],
    },
    {
        "id": "evals_benchmarks",
        "label_zh": "评测与基准",
        "label_en": "Evals and Benchmarks",
        "patterns": [
            r"\beval|evals|benchmark|leaderboard|frontiermath|swe-bench|terminal-bench|browsecomp|medmark\b",
            r"\bhard eval|saturat|score|pass rate|win rate|tier 4|reasoning benchmark\b",
        ],
    },
    {
        "id": "training_optimization",
        "label_zh": "训练与优化",
        "label_en": "Training and Optimization",
        "patterns": [
            r"\bpre-training|pretraining|post-training|sft|rlhf|rlvr|synthetic data|data mix\b",
            r"\boptimizer|scaling law|muon|soap|nesterov|attention|gradient|token per parameter\b",
            r"\btrain|training|throughput|loss|checkpoint|fine-tun|finetun\b",
        ],
    },
    {
        "id": "inference_infra",
        "label_zh": "推理与基础设施",
        "label_en": "Inference and Infrastructure",
        "patterns": [
            r"\binference|serving|prefill|decode|kv cache|latency|throughput|token/s|cost per token\b",
            r"\bgpu|tpu|blackwell|gb200|h100|h200|b200|nvl72|cuda|kernel|roce|all-reduce\b",
            r"\bvector db|retriever|qdrant|vllm|modal|checkpointing|cache|orchestration\b",
        ],
    },
    {
        "id": "agent_engineering",
        "label_zh": "Agent 工程",
        "label_en": "Agent Engineering",
        "patterns": [
            r"\bagent(?:ic)? (?:design|engineering|workflow|workflows|system|systems|architecture|loop|loops)\b",
            r"\bagentic system|agentic systems\b",
            r"\bagent harness|agent runtime|tool use|tool-use|function calling|computer use|browser use\b",
            r"\bmcp|memory|state|checkpoint|trace|trajectory|rollout|verifier|judge|sandbox\b",
            r"\blong-running agent|multi-agent|agent environment|task mining|workflow orchestration\b",
        ],
    },
    {
        "id": "product_startups",
        "label_zh": "产品",
        "label_en": "Products",
        "patterns": [
            r"\bstartup|launch|product|app|waitlist|demo|users|adoption|pricing|api|sdk\b",
            r"\bgithub|repo|open source project|trending|developer tool|cursor|codex|claude code\b",
            r"\bseries a|seed round|funding|founder|customer|market\b",
        ],
    },
    {
        "id": "org_strategy",
        "label_zh": "组织改革",
        "label_en": "Organization and Strategy",
        "patterns": [
            r"\breorg|reorganization|org|organization|team|lab|research lab|talent|hire|hiring\b",
            r"\bceo|cto|chief scientist|vp|leadership|acqui-hire|spinout|joined|leaving\b",
            r"\bstrategy|roadmap|enterprise adoption|internal agent|workforce|workflow change\b",
        ],
    },
    {
        "id": "safety_security",
        "label_zh": "安全与治理",
        "label_en": "Safety and Security",
        "patterns": [
            r"\bsupply chain|npm|pypi|malware|exploit|vulnerability|prompt injection|secret|secrets\b",
            r"\bsecurity|secure|safety|alignment|jailbreak|policy|governance|compliance|risk\b",
            r"\bci/cd|pull_request_target|dependency|package|guardrail|sandbox escape\b",
        ],
    },
]

CATEGORY_BY_ID = {category["id"]: category for category in HOTSPOT_CATEGORIES}


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


def date_window(target_date: str) -> tuple[str, str]:
    try:
        start = dt.date.fromisoformat(target_date)
    except ValueError as exc:
        raise RuntimeError(f"Invalid --date value: {target_date}. Use YYYY-MM-DD.") from exc
    return start.isoformat(), (start + dt.timedelta(days=1)).isoformat()


def run_subprocess(cmd: list[str], timeout: int = 40) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def bird_command() -> list[str] | None:
    if os.environ.get("PERSONAL_NEWSLETTER_BIRD_MJS"):
        mjs = os.environ["PERSONAL_NEWSLETTER_BIRD_MJS"]
        if shutil.which("node"):
            return ["node", mjs]
    if VENDORED_BIRD_MJS.exists() and shutil.which("node"):
        return ["node", str(VENDORED_BIRD_MJS)]
    if os.environ.get("PERSONAL_NEWSLETTER_BIRD_CMD"):
        return shlex.split(os.environ["PERSONAL_NEWSLETTER_BIRD_CMD"])
    if shutil.which("bird"):
        return ["bird"]
    return None


def fetch_with_bird(
    accounts: list[Account],
    lookback_hours: int,
    count: int,
    target_date: str | None = None,
) -> list[Post]:
    command = bird_command()
    if not command:
        raise RuntimeError("bird command not found. Install/authenticate bird or set PERSONAL_NEWSLETTER_BIRD_CMD.")

    posts: list[Post] = []
    if target_date:
        start_date, end_date = date_window(target_date)
    else:
        start_date, end_date = since_date(lookback_hours), ""
    for account in accounts:
        query = f"from:{account.handle} since:{start_date}"
        if end_date:
            query += f" until:{end_date}"
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


def resolve_workspace_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return WORKSPACE_DIR / path


def load_handle_pool(path_value: str | Path, key: str | None = None) -> list[str]:
    path = resolve_workspace_path(path_value)
    if not path.exists():
        return []
    raw = load_json(path)
    values: Any
    if key:
        values = raw.get(key, [])
    else:
        values = raw.get("all_handles") or raw.get("handles") or raw.get("core_handles") or []
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    handles: list[str] = []
    for value in values:
        handle = str(value).lstrip("@").strip()
        lowered = handle.lower()
        if not handle or lowered in seen:
            continue
        seen.add(lowered)
        handles.append(handle)
    return handles


def rotate_handles(handles: list[str], limit: int, target_date: str | None = None) -> list[str]:
    if limit <= 0 or len(handles) <= limit:
        return handles[:]
    if target_date:
        try:
            anchor = dt.date.fromisoformat(target_date)
        except ValueError:
            anchor = dt.date.today()
    else:
        anchor = dt.date.today()
    offset = (anchor.toordinal() * limit) % len(handles)
    rotated = handles[offset:] + handles[:offset]
    return rotated[:limit]


def pool_account(handle: str, existing: dict[str, Account], tier: str, weight: float, source: str) -> Account:
    current = existing.get(handle.lower())
    if current:
        data = {**current.__dict__, "tier": tier, "weight": weight, "source": source}
        return account_from_dict(data, source)
    return Account(handle=handle, label=handle, role=source, tier=tier, weight=weight, source=source)


def load_category_expert_handles(path_value: str | Path, target_date: str | None = None) -> list[str]:
    path = resolve_workspace_path(path_value)
    if not path.exists():
        return []
    raw = load_json(path)
    categories = raw.get("categories", [])
    if not isinstance(categories, list):
        return []

    selected: list[str] = []
    seen: set[str] = set()
    for category in categories:
        if not isinstance(category, dict):
            continue
        sample_size = int(category.get("runtime_sample", 1) or 1)
        experts = category.get("experts", [])
        if not isinstance(experts, list):
            continue
        handles = [
            str(item.get("handle", "")).lstrip("@").strip()
            for item in experts
            if isinstance(item, dict) and item.get("handle") and str(item.get("tier", "")) != "watchlist"
        ]
        for handle in rotate_handles(handles, sample_size, target_date):
            lowered = handle.lower()
            if handle and lowered not in seen:
                seen.add(lowered)
                selected.append(handle)
    return selected


def select_hotspot_expert_handles(config: dict[str, Any], target_date: str | None = None) -> list[str]:
    hotspot_config = config.get("hotspots", {})
    category_path = hotspot_config.get("category_experts_path", "")
    max_accounts = int(hotspot_config.get("expert_validation_accounts_per_run", 14))
    if category_path:
        category_handles = load_category_expert_handles(category_path, target_date)
        if category_handles:
            return category_handles[:max_accounts]

    expert_path = hotspot_config.get("expert_handles_path", "")
    core_handles = rotate_handles(
        load_handle_pool(expert_path, "core_handles"),
        int(hotspot_config.get("core_experts_per_run", 16)),
        target_date,
    )
    signal_handles = rotate_handles(
        load_handle_pool(expert_path, "signal_handles"),
        int(hotspot_config.get("signal_experts_per_run", 12)),
        target_date,
    )
    expert_handles = core_handles + [handle for handle in signal_handles if handle.lower() not in {h.lower() for h in core_handles}]
    return expert_handles[:max_accounts]


def fetch_hotspots_with_bird(
    domain_id: str,
    accounts: list[Account],
    config: dict[str, Any],
    lookback_hours: int,
    target_date: str | None = None,
) -> tuple[list[Post], dict[str, Any]]:
    command = bird_command()
    if not command:
        raise RuntimeError("bird command not found. Install/authenticate bird or set PERSONAL_NEWSLETTER_BIRD_CMD.")

    hotspot_config = config.get("hotspots", {})
    existing = {account.handle.lower(): account for account in accounts}
    expert_path = hotspot_config.get("expert_handles_path", "")
    category_expert_path = hotspot_config.get("category_experts_path", "")
    discovery_path = hotspot_config.get("discovery_handles_path", "")
    expert_handles = select_hotspot_expert_handles(config, target_date)
    expert_set = {handle.lower() for handle in expert_handles}
    org_exclusions = {
        str(handle).lstrip("@").lower()
        for handle in hotspot_config.get("exclude_handles", [])
    }

    discovery_handles = [
        handle
        for handle in load_handle_pool(discovery_path, "handles")
        if handle.lower() not in expert_set and handle.lower() not in org_exclusions
    ]
    selected_discovery = rotate_handles(
        discovery_handles,
        int(hotspot_config.get("discovery_accounts_per_run", 60)),
        target_date,
    )

    if target_date:
        start_date, end_date = date_window(target_date)
    else:
        start_date, end_date = since_date(lookback_hours), ""

    posts: list[Post] = []
    errors: list[dict[str, str]] = []
    fetch_stats: dict[str, Any] = {
        "expert_accounts": len(expert_handles),
        "discovery_accounts": len(selected_discovery),
        "keyword_queries": len(hotspot_config.get("keyword_queries", [])),
        "expert_handles_path": str(resolve_workspace_path(expert_path)) if expert_path else "",
        "category_experts_path": str(resolve_workspace_path(category_expert_path)) if category_expert_path else "",
        "discovery_handles_path": str(resolve_workspace_path(discovery_path)) if discovery_path else "",
        "excluded_accounts": len(org_exclusions),
        "errors": errors,
    }

    def collect_query(query: str, count: int, account: Account) -> None:
        try:
            normalized = normalize_posts(run_bird_search(command, query, count), account)
            posts.extend(post for post in normalized if post.author_handle.lower() not in org_exclusions)
        except RuntimeError as exc:
            errors.append({"query": query[:160], "error": str(exc)[:240]})

    expert_count = int(hotspot_config.get("expert_posts_per_account", 3))
    for handle in expert_handles:
        account = pool_account(handle, existing, "core", 1.0, "category_expert_pool")
        query = f"from:{account.handle} since:{start_date}"
        if end_date:
            query += f" until:{end_date}"
        collect_query(query, expert_count, account)

    discovery_count = int(hotspot_config.get("discovery_posts_per_account", 2))
    for handle in selected_discovery:
        account = pool_account(handle, existing, "edge", 0.45, "discovery_pool")
        query = f"from:{account.handle} since:{start_date}"
        if end_date:
            query += f" until:{end_date}"
        collect_query(query, discovery_count, account)

    keyword_count = int(hotspot_config.get("keyword_posts_per_query", 20))
    search_account = Account(handle="search", label="X Search", role="keyword_search", tier="edge", weight=0.35, source="search")
    for raw_query in hotspot_config.get("keyword_queries", []):
        query = f"{raw_query} since:{start_date}"
        if end_date:
            query += f" until:{end_date}"
        collect_query(query, keyword_count, search_account)

    return dedupe_posts(posts), fetch_stats


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
    author_label = account.label or handle
    if account.source == "search" and handle.lower() != account.handle.lower():
        author_label = handle
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
        author_label=author_label,
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


def is_substantive_post(post: Post) -> bool:
    text = re.sub(r"\s+", " ", post.text).strip()
    lowered = text.lower()
    if "source via" in lowered and "newsletter" in lowered:
        return False
    if "https://t.co" in lowered and "newsletter" in lowered and len(text) < 180:
        return False
    if len(text) < 70:
        return False
    if text.startswith("@") and len(text) < 140:
        return False
    useful_markers = (
        "ai", "agent", "model", "gpt", "deepseek", "gemini", "claude",
        "anthropic", "openai", "meta", "nsf", "research", "data center",
        "solar", "inference", "open source", "benchmark", "eval",
    )
    if any(marker in lowered for marker in useful_markers):
        return True
    return len(tokenize(text)) >= 8


def hotspot_category_scores(text: str) -> list[tuple[int, dict[str, Any]]]:
    scores: list[tuple[int, dict[str, Any]]] = []
    for category in HOTSPOT_CATEGORIES:
        score = 0
        for pattern in category["patterns"]:
            score += len(re.findall(pattern, text, flags=re.IGNORECASE))
        scores.append((score, category))
    return scores


def hotspot_category_for_post(post: Post) -> dict[str, Any] | None:
    text = f"{post.author_handle} {post.author_label} {post.text}"
    scored = hotspot_category_scores(text)
    best_score, best_category = max(scored, key=lambda item: item[0])
    if best_score <= 0:
        return None
    return best_category


def tokenize(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9_+\-.]{2,}", text.lower())
    return {word.strip(".-_") for word in words if word not in STOPWORDS and len(word) > 2}


def cluster_hotspot_posts(posts: list[Post], max_topics: int, expert_handles: set[str]) -> list[dict[str, Any]]:
    categorized_posts: dict[str, list[Post]] = {category["id"]: [] for category in HOTSPOT_CATEGORIES}
    for post in posts:
        category = hotspot_category_for_post(post)
        if not category:
            continue
        categorized_posts[category["id"]].append(post)

    topics_by_category: dict[str, list[dict[str, Any]]] = {}
    for category in HOTSPOT_CATEGORIES:
        category_posts = categorized_posts[category["id"]]
        if not category_posts:
            topics_by_category[category["id"]] = []
            continue
        category_topics = cluster_posts(category_posts, max_topics=3)
        annotated = annotate_hotspot_topics(category_topics, expert_handles)
        for topic in annotated:
            topic["category"] = {
                "id": category["id"],
                "label_zh": category["label_zh"],
                "label_en": category["label_en"],
            }
        topics_by_category[category["id"]] = annotated

    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    for category in HOTSPOT_CATEGORIES:
        category_topics = topics_by_category.get(category["id"], [])
        if category_topics and len(selected) < max_topics:
            selected.append(category_topics[0])
            selected_ids.add(id(category_topics[0]))

    extras = [
        topic
        for category_topics in topics_by_category.values()
        for topic in category_topics[1:]
        if id(topic) not in selected_ids
    ]
    extras.sort(key=lambda item: item.get("hotspot", {}).get("score", item.get("score", 0)), reverse=True)
    for topic in extras:
        if len(selected) >= max_topics:
            break
        selected.append(topic)
    for index, topic in enumerate(selected, start=1):
        topic["id"] = f"H{index}"
    return selected


def cluster_posts(posts: list[Post], max_topics: int) -> list[dict[str, Any]]:
    substantive_posts = [post for post in posts if is_substantive_post(post)]
    if len(substantive_posts) >= 3:
        posts = substantive_posts
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
        if best is not None and should_merge_cluster(tokens, best["tokens"], best_overlap):
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
        post_dicts = [post_to_dict(post) for post in top_posts[:8]]
        analysis = analyze_topic(top_posts, perspectives)
        tags = extract_topic_tags(top_posts)
        topics.append(
            {
                "id": f"T{index}",
                "title": analysis["title_zh"],
                "keywords": topic_tokens,
                "score": round(cluster["score"], 2),
                "source_accounts": sorted({post.author_handle for post in top_posts}),
                "posts": post_dicts,
                "perspectives": perspectives,
                "analysis": analysis,
                "tags": tags,
                "companies": tags["companies"],
                "models": tags["models"],
                "people": tags["people"],
                "topics": tags["topics"],
                "summary_seed": analysis["summary_zh"],
                "quality": topic_quality(top_posts, cluster["score"], tags),
            }
        )
    return topics


def should_merge_cluster(tokens: set[str], cluster_tokens: set[str], overlap: int) -> bool:
    if overlap < 2:
        return False
    smaller = max(1, min(len(tokens), len(cluster_tokens)))
    union = max(1, len(tokens | cluster_tokens))
    if smaller <= 10:
        return overlap / smaller >= 0.3
    if smaller <= 18:
        return overlap >= 3 and overlap / smaller >= 0.22
    return overlap >= 5 and overlap / union >= 0.08


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


def first_sentence(text: str, limit: int = 260) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return ""
    parts = re.split(r"(?<=[.!?。！？])\s+", compact, maxsplit=1)
    sentence = parts[0] if parts else compact
    return trim_sentence(sentence, limit)


def extract_entities(text: str, limit: int = 5) -> list[str]:
    candidates = re.findall(
        r"\b(?:[A-Z][A-Za-z0-9.+-]{1,}(?:\s+[A-Z0-9][A-Za-z0-9.+-]{1,}){0,3}|GPT[-\s]?\d(?:\.\d)?|Opus\s+\d(?:\.\d)?|DeepSeek\s+V\d|Kimi\s+\d(?:\.\d)?|Gemini|Claude|Anthropic|OpenAI|Meta|NSF)\b",
        text,
    )
    entities: list[str] = []
    for value in candidates:
        cleaned = value.strip(" .,:;!?()[]")
        if cleaned and cleaned.lower() not in STOPWORDS and cleaned not in entities:
            entities.append(cleaned)
        if len(entities) >= limit:
            break
    return entities


def rough_zh_snippet(text: str, limit: int = 220) -> str:
    snippet = first_sentence(text, limit)
    replacements = {
        "open source": "开源",
        "closed source": "闭源",
        "closed expensive model": "昂贵闭源模型",
        "data centers": "数据中心",
        "solar energy": "太阳能",
        "space": "太空",
        "coming soon": "很快会来",
        "not yet": "还没有",
        "best open source model": "最强开源模型",
        "cheaper": "更便宜",
        "faster": "更快",
        "budget": "预算",
        "scientific research": "科学研究",
        "PhD graduates": "博士毕业生",
    }
    rendered = snippet
    for old, new in replacements.items():
        rendered = re.sub(re.escape(old), new, rendered, flags=re.IGNORECASE)
    return rendered


def post_gist_zh(text: str) -> str:
    lowered = text.lower()
    for needles, gist in KNOWN_TOPIC_RULES:
        if all(needle in lowered for needle in needles):
            return gist
    entities = extract_entities(text)
    if entities:
        return f"围绕 {'、'.join(entities)} 的讨论：{rough_zh_snippet(text)}"
    return f"这条帖子关注的是：{rough_zh_snippet(text)}"


def sentence_with_period(text: str) -> str:
    cleaned = text.rstrip("。.!?！？")
    return cleaned + "。"


def topic_title_zh_from_posts(posts: list[dict[str, Any]]) -> str:
    if not posts:
        return "未命名主题"
    top = posts[0]
    gist = post_gist_zh(str(top.get("text", "")))
    title = re.split(r"[，。：；]", gist, maxsplit=1)[0]
    return trim_sentence(title, 72)


def normalize_tag(value: str) -> str:
    return re.sub(r"[^a-z0-9.+-]+", "-", value.lower()).strip("-")


def ordered_unique(values: list[str], limit: int | None = None) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = normalize_tag(value)
        if normalized and normalized not in result:
            result.append(normalized)
        if limit and len(result) >= limit:
            break
    return result


def regex_tags(text: str, patterns: list[tuple[str, str]]) -> list[str]:
    found: list[str] = []
    for pattern, tag in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            found.append(tag)
    return found


def extract_topic_tags(posts: list[Post]) -> dict[str, list[str]]:
    text = "\n".join(post.text for post in posts)
    people = [post.author_handle for post in posts]
    for entity in extract_entities(text, limit=12):
        lowered = entity.lower().replace(" ", "_")
        if lowered in {"sam_altman", "sama"}:
            people.append("sama")
        elif lowered in {"yann_lecun", "ylecun"}:
            people.append("ylecun")
    return {
        "companies": ordered_unique(regex_tags(text, COMPANY_PATTERNS), limit=10),
        "models": ordered_unique(regex_tags(text, MODEL_PATTERNS), limit=10),
        "people": ordered_unique(people, limit=10),
        "topics": ordered_unique(regex_tags(text, TOPIC_PATTERNS), limit=10),
    }


def analyze_topic(posts: list[Post], perspectives: dict[str, list[dict[str, str]]]) -> dict[str, Any]:
    gists = [post_gist_zh(post.text) for post in posts]
    key_points = ordered_text(gists, limit=3)
    title = re.split(r"[，。：；]", key_points[0], maxsplit=1)[0] if key_points else "未命名主题"
    stance_notes = {
        "supportive": [zh_view_summary(view, "supportive", {}) for view in perspectives.get("supportive", [])],
        "skeptical": [zh_view_summary(view, "skeptical", {}) for view in perspectives.get("skeptical", [])],
        "observational": [zh_view_summary(view, "observational", {}) for view in perspectives.get("observational", [])],
    }
    return {
        "title_zh": trim_sentence(title, 72),
        "summary_zh": build_topic_summary_zh(posts, key_points),
        "key_points_zh": key_points,
        "stance_notes_zh": stance_notes,
    }


def ordered_text(values: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in result:
            result.append(cleaned)
        if len(result) >= limit:
            break
    return result


def build_topic_summary_zh(posts: list[Post], key_points: list[str]) -> str:
    accounts = "、".join(f"@{handle}" for handle in unique_post_handles(posts)[:4])
    if not key_points:
        return f"{accounts} 等账号贡献了 {len(posts)} 条相关内容。"
    return f"{accounts} 等账号贡献了 {len(posts)} 条相关内容。核心信息是：{'; '.join(key_points[:2])}"


def unique_post_handles(posts: list[Post]) -> list[str]:
    handles: list[str] = []
    for post in posts:
        if post.author_handle not in handles:
            handles.append(post.author_handle)
    return handles


def engagement_feedback(engagement: dict[str, Any]) -> int:
    return int(engagement.get("replies") or 0) + int(engagement.get("quotes") or 0)


def topic_max_feedback(topic: dict[str, Any]) -> int:
    return max((engagement_feedback(post.get("engagement", {})) for post in topic.get("posts", [])), default=0)


def is_single_account_low_feedback_topic(topic: dict[str, Any], threshold: int) -> bool:
    accounts = set(topic.get("source_accounts", []))
    if len(accounts) != 1:
        return False
    return topic_max_feedback(topic) <= threshold


def topic_quality(posts: list[Post], score: float, tags: dict[str, list[str]]) -> dict[str, Any]:
    tag_count = sum(len(values) for values in tags.values())
    substantive_count = sum(1 for post in posts if is_substantive_post(post))
    max_feedback = max((engagement_feedback(post.engagement) for post in posts), default=0)
    if len(posts) >= 2:
        level = "high"
    elif score >= 18 and tag_count >= 2 and substantive_count >= 1:
        level = "medium"
    else:
        level = "low"
    return {
        "level": level,
        "post_count": len(posts),
        "substantive_posts": substantive_count,
        "tag_count": tag_count,
        "score": round(score, 2),
        "max_feedback": max_feedback,
    }


def apply_quality_gate(topics: list[dict[str, Any]], posts: list[Post], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    quality_config = config.get("quality", {})
    min_substantive_posts = int(quality_config.get("min_substantive_posts", 2))
    min_topic_score = float(quality_config.get("min_topic_score", 18))
    min_single_account_replies = int(quality_config.get("min_single_account_replies", 100))
    substantive_posts = [post for post in posts if is_substantive_post(post)]
    accepted = [
        topic
        for topic in topics
        if topic["quality"]["level"] != "low" and float(topic.get("score", 0)) >= min_topic_score
        and not is_single_account_low_feedback_topic(topic, min_single_account_replies)
    ]
    is_low_signal = len(substantive_posts) < min_substantive_posts or not accepted
    report = {
        "status": "low_signal" if is_low_signal else "ok",
        "substantive_posts": len(substantive_posts),
        "min_substantive_posts": min_substantive_posts,
        "min_topic_score": min_topic_score,
        "min_single_account_replies": min_single_account_replies,
        "rejected_topics": len(topics) - len(accepted),
        "reason": "",
    }
    if len(substantive_posts) < min_substantive_posts:
        report["reason"] = "账号池内有效信息不足，未强行生成热点。"
    elif not accepted:
        report["reason"] = "候选主题质量分不足，未强行生成热点。"
    return ([] if is_low_signal else accepted), report


def apply_hotspot_quality_gate(topics: list[dict[str, Any]], posts: list[Post], config: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    quality_config = config.get("quality", {})
    min_substantive_posts = int(quality_config.get("min_substantive_posts", 2))
    min_hotspot_score = float(quality_config.get("min_hotspot_score", 28))
    substantive_posts = [post for post in posts if is_substantive_post(post)]
    accepted: list[dict[str, Any]] = []
    for topic in topics:
        hotspot = topic.get("hotspot", {})
        hotspot_score = float(hotspot.get("score", topic.get("score", 0)) or 0)
        discussion_accounts = int(hotspot.get("discussion_accounts", 0) or 0)
        expert_count = int(hotspot.get("expert_account_count", 0) or 0)
        feedback_total = int(hotspot.get("feedback_total", 0) or 0)
        has_validation = discussion_accounts >= 2 or expert_count >= 1 or feedback_total >= 200
        if (
            topic["quality"]["level"] != "low"
            and hotspot_score >= min_hotspot_score
            and has_validation
            and hotspot_category_publish_relevance_ok(topic)
        ):
            accepted.append(topic)

    is_low_signal = len(substantive_posts) < min_substantive_posts or not accepted
    report = {
        "status": "low_signal" if is_low_signal else "ok",
        "substantive_posts": len(substantive_posts),
        "min_substantive_posts": min_substantive_posts,
        "min_hotspot_score": min_hotspot_score,
        "rejected_topics": len(topics) - len(accepted),
        "reason": "",
    }
    if len(substantive_posts) < min_substantive_posts:
        report["reason"] = "候选池内有效信息不足，未强行生成热点。"
    elif not accepted:
        report["reason"] = "候选热点缺少足够讨论热度或专家验证，未强行生成热点。"
    return ([] if is_low_signal else accepted), report


def topic_feedback_total(topic: dict[str, Any]) -> int:
    total = 0
    for post in topic.get("posts", []):
        engagement = post.get("engagement", {})
        total += int(engagement.get("likes") or 0)
        total += int(engagement.get("reposts") or 0) * 3
        total += int(engagement.get("replies") or 0) * 2
        total += int(engagement.get("quotes") or 0) * 4
        total += int(engagement.get("bookmarks") or 0) * 3
    return total


def topic_source_text(topic: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(str(topic.get("analysis", {}).get("title_zh") or ""))
    parts.extend(str(value) for value in topic.get("keywords", []))
    for post in topic.get("posts", []):
        parts.append(str(post.get("author_handle") or ""))
        parts.append(str(post.get("author_label") or ""))
        parts.append(str(post.get("text") or ""))
    return "\n".join(parts)


def has_pattern(text: str, pattern: str) -> bool:
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def hotspot_category_publish_relevance_ok(topic: dict[str, Any]) -> bool:
    category_id = str(topic.get("category", {}).get("id") or "")
    text = topic_source_text(topic)
    rules = {
        "foundation_models": r"\b(model|models|multimodal|embedding|open weights?|claude|gpt|gemini|deepseek|qwen|kimi|llama|mistral|anthropic|openai)\b",
        "evals_benchmarks": r"\b(eval|evals|benchmark|benchmarks|leaderboard|score|pass rate|frontiermath|swe-bench|arc-agi|mmlu|hle)\b",
        "training_optimization": r"\b(training|train|pretraining|post-training|posttraining|optimizer|scaling law|gradient|rlhf|rlvr|synthetic data|fine-tun|distillation)\b",
        "inference_infra": r"\b(inference|serving|latency|throughput|gpu|tpu|kernel|cuda|vllm|compute|prefill|decode|cost per token)\b",
        "agent_engineering": r"\b(agent runtime|agent harness|tool use|tool-use|mcp|sdk|function calling|computer use|browser use|workflow|workflows|verifier|sandbox|coding agent)\b",
        "product_startups": r"\b(launch|launched|released|open-sourced|github|repo|startup|funding|yc|product|api|sdk|developer tool|users|customers)\b",
        "org_strategy": r"\b(reorg|reorganization|hiring|layoffs?|entry-level jobs?|workforce|organization|org chart|leadership|ceo|cto|chief scientist|vp|lab|labs|team structure|talent|strategy)\b",
        "safety_security": r"\b(prompt injection|supply chain|vulnerability|malware|jailbreak|secret|secrets|security|secure|safety|alignment|policy|governance|risk|sandbox escape)\b",
    }
    pattern = rules.get(category_id)
    return True if not pattern else has_pattern(text, pattern)


def hotspot_rejection_reason(topic: dict[str, Any]) -> str:
    hotspot = topic.get("hotspot", {})
    quality = topic.get("quality", {})
    if not hotspot_category_publish_relevance_ok(topic):
        return "候选存在，但栏目相关性不足，避免把泛泛高互动帖误发布。"
    return (
        f"候选存在，但未达到发布门槛：质量={quality.get('level', 'unknown')}，"
        f"讨论账号={hotspot.get('discussion_accounts', 0)}，"
        f"专家验证={hotspot.get('expert_account_count', 0)}，"
        f"互动反馈={hotspot.get('feedback_total', 0)}。"
    )


def annotate_hotspot_topics(topics: list[dict[str, Any]], expert_handles: set[str]) -> list[dict[str, Any]]:
    annotated: list[dict[str, Any]] = []
    for topic in topics:
        source_accounts = [str(handle) for handle in topic.get("source_accounts", [])]
        expert_accounts = sorted({handle for handle in source_accounts if handle.lower() in expert_handles})
        feedback_total = topic_feedback_total(topic)
        discussion_accounts = len(set(source_accounts))
        expert_validation_score = min(40, len(expert_accounts) * 18)
        source_diversity_score = min(25, max(0, discussion_accounts - 1) * 8)
        discussion_score = min(60, feedback_total / 80)
        hotspot_score = round(
            float(topic.get("score", 0)) + expert_validation_score + source_diversity_score + discussion_score,
            2,
        )
        topic["hotspot"] = {
            "score": hotspot_score,
            "discussion_accounts": discussion_accounts,
            "expert_accounts": expert_accounts,
            "expert_account_count": len(expert_accounts),
            "feedback_total": feedback_total,
            "expert_validation_score": expert_validation_score,
            "source_diversity_score": source_diversity_score,
            "discussion_score": round(discussion_score, 2),
        }
        annotated.append(topic)
    return sorted(annotated, key=lambda item: item.get("hotspot", {}).get("score", item.get("score", 0)), reverse=True)


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
    analysis_title = topic.get("analysis", {}).get("title_zh")
    if analysis_title:
        return str(analysis_title)
    title = topic_title_zh_from_posts(topic.get("posts", []))
    if title and title != "未命名主题":
        return title
    keywords = zh_keywords(topic.get("keywords", []), limit=3)
    if keywords:
        return " / ".join(keywords)
    accounts = "、".join(f"@{handle}" for handle in topic.get("source_accounts", [])[:2])
    return f"{accounts} 关注的热点"


def zh_topic_summary(topic: dict[str, Any]) -> str:
    summary = topic.get("analysis", {}).get("summary_zh")
    if summary:
        return str(summary)
    accounts = "、".join(f"@{handle}" for handle in topic.get("source_accounts", [])[:4])
    posts = topic.get("posts", [])
    post_count = len(posts)
    key_points = [post_gist_zh(str(post.get("text", ""))) for post in posts[:2]]
    if key_points:
        return f"{accounts} 等账号在这个主题下贡献了 {post_count} 条相关内容。核心信息是：{'; '.join(key_points)}"
    return f"{accounts} 等账号在这个主题下贡献了 {post_count} 条相关内容。"


def zh_view_summary(view: dict[str, str], stance: str, topic: dict[str, Any]) -> str:
    account = f"@{view['account']}"
    gist = post_gist_zh(view.get("text", ""))
    if stance == "supportive":
        return f"{account} 偏积极：{gist}"
    if stance == "skeptical":
        return f"{account} 偏谨慎：{gist}"
    return f"{account} 提供信号：{gist}"


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


def build_hotspot_candidate_coverage(
    candidate_topics: list[dict[str, Any]],
    published_topics: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    published_ids = {str(topic.get("id")) for topic in published_topics}
    topics_by_category: dict[str, list[dict[str, Any]]] = {category["id"]: [] for category in HOTSPOT_CATEGORIES}
    for topic in candidate_topics:
        category = topic_category(topic)
        topics_by_category.setdefault(category["id"], []).append(topic)

    coverage: list[dict[str, Any]] = []
    for category in HOTSPOT_CATEGORIES:
        category_topics = topics_by_category.get(category["id"], [])
        if not category_topics:
            coverage.append(
                {
                    "category": {
                        "id": category["id"],
                        "label_zh": category["label_zh"],
                        "label_en": category["label_en"],
                    },
                    "status": "missing",
                    "candidate_count": 0,
                    "summary": "本次没有抓到候选主题。",
                }
            )
            continue

        top = category_topics[0]
        status = "published" if str(top.get("id")) in published_ids else "candidate_rejected"
        reason = ""
        if status == "candidate_rejected":
            reason = hotspot_rejection_reason(top)
        coverage.append(
            {
                "category": {
                    "id": category["id"],
                    "label_zh": category["label_zh"],
                    "label_en": category["label_en"],
                },
                "status": status,
                "candidate_count": len(category_topics),
                "summary": "已发布为正式主题。" if status == "published" else reason,
                "top_candidate": {
                    "id": top.get("id"),
                    "title_zh": top.get("analysis", {}).get("title_zh") or zh_topic_title(top),
                    "source_accounts": top.get("source_accounts", []),
                    "post_count": len(top.get("posts", [])),
                    "quality": top.get("quality", {}),
                    "hotspot": top.get("hotspot", {}),
                    "source_urls": [
                        str(post.get("url"))
                        for post in top.get("posts", [])[:3]
                        if post.get("url")
                    ],
                },
            }
        )
    return coverage


def build_digest(domain_id: str, posts: list[Post], config: dict[str, Any], language: str) -> dict[str, Any]:
    domain = load_domain(domain_id)
    hotspot_mode = bool(config.get("_hotspot_mode"))
    if hotspot_mode:
        max_topics = int(config.get("hotspots", {}).get("max_topics", config.get("max_topics", 6)))
        expert_handles = {str(handle).lower() for handle in config.get("_runtime_expert_handles", [])}
        candidate_topics = cluster_hotspot_posts(posts, max_topics, expert_handles)
        topics, quality = apply_hotspot_quality_gate(candidate_topics, posts, config)
        candidate_coverage = build_hotspot_candidate_coverage(candidate_topics, topics)
    else:
        max_topics = int(config.get("max_topics", 6))
        candidate_topics = cluster_posts(posts, max_topics)
        topics, quality = apply_quality_gate(candidate_topics, posts, config)
        candidate_coverage = []
    digest = {
        "schema_version": "0.2",
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
        "quality": quality,
        "candidate_topics": len(candidate_topics),
        "topics": topics,
    }
    if hotspot_mode:
        digest["mode"] = "hotspots"
        digest["candidate_coverage"] = candidate_coverage
        digest["hotspot_categories"] = [
            {
                "id": category["id"],
                "label_zh": category["label_zh"],
                "label_en": category["label_en"],
            }
            for category in HOTSPOT_CATEGORIES
        ]
        digest["hotspot_fetch"] = config.get("_hotspot_fetch", {})
    return digest


def render_markdown(digest: dict[str, Any]) -> str:
    language = digest.get("language", "zh-CN").lower()
    if language.startswith("en"):
        return render_markdown_en(digest)
    if digest.get("mode") == "hotspots":
        return render_markdown_zh_hotspots(digest)
    return render_markdown_zh_compact(digest)


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
        reason = digest.get("quality", {}).get("reason") or "今天账号池内没有足够的新内容生成热点。"
        lines.extend([str(reason), ""])
        return "\n".join(lines)

    lines.append("## 今日要点")
    for topic in digest["topics"]:
        accounts = ", ".join(f"@{handle}" for handle in topic["source_accounts"][:5])
        lines.append(f"- {zh_topic_title(topic)}: 引用账号 {accounts}")
    lines.append("")

    for topic in digest["topics"]:
        lines.extend([f"## {topic['id']}. {zh_topic_title(topic)}", "", zh_topic_summary(topic), ""])
        tags = topic.get("tags", {})
        tag_parts = []
        for key, label in (
            ("companies", "公司"),
            ("models", "模型"),
            ("people", "人物/账号"),
            ("topics", "主题标签"),
        ):
            values = tags.get(key, [])
            if values:
                tag_parts.append(f"{label}: {', '.join(values)}")
        if tag_parts:
            lines.extend(["标签: " + " | ".join(tag_parts), ""])
        lines.append("各方观点与信号:")
        for key, label in (
            ("supportive", "偏积极/支持"),
            ("skeptical", "偏谨慎/质疑"),
            ("observational", "中性观察"),
        ):
            views = topic["perspectives"].get(key, [])
            if views:
                lines.append(f"- {label}:")
                for view in views:
                    lines.append(f"  - {zh_view_summary(view, key, topic)}")
        lines.append("")
        lines.append("引用来源:")
        for post in topic["posts"][:5]:
            link = post["url"] or f"https://x.com/{post['author_handle']}"
            lines.append(f"- @{post['author_handle']}: {sentence_with_period(post_gist_zh(post['text']))}原帖链接: {link}")
        lines.append("")
    return "\n".join(lines)


def compact_topic_title_zh(topic: dict[str, Any]) -> str:
    posts = topic.get("posts", [])
    if len(posts) == 1 and len(topic.get("source_accounts", [])) == 1:
        post = posts[0]
        label = str(post.get("author_label") or post.get("author_handle") or "").strip()
        gist = post_gist_zh(str(post.get("text", ""))).rstrip("。")
        if label and not gist.lower().startswith(label.lower()):
            return f"{label}表示{gist}"
    return zh_topic_title(topic)


def display_author(post: dict[str, Any]) -> str:
    return str(post.get("author_label") or post.get("author_handle") or "").strip()


def concise_gist_for_author(text: str, author: str, index: int) -> str:
    gist = post_gist_zh(text).rstrip("。")
    if index == 0 or not author:
        return gist
    if gist.startswith(author):
        return "他" + gist[len(author):].lstrip()
    return gist


def compact_account_views(topic: dict[str, Any]) -> list[str]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for post in topic.get("posts", []):
        grouped.setdefault(str(post.get("author_handle")), []).append(post)

    lines: list[str] = []
    for handle, posts in grouped.items():
        author = display_author(posts[0])
        gists = [
            concise_gist_for_author(str(post.get("text", "")), author, index)
            for index, post in enumerate(posts)
        ]
        summary = "；".join(ordered_text(gists, limit=5))
        prefix = author if author else f"@{handle}"
        if len(grouped) == 1:
            lines.append(sentence_with_period(summary))
        else:
            lines.append(f"- @{handle}: {sentence_with_period(summary)}")
    return lines


def compact_source_citation(topic: dict[str, Any]) -> str:
    by_handle: dict[str, list[str]] = {}
    for post in topic.get("posts", []):
        handle = str(post.get("author_handle"))
        link = str(post.get("url") or f"https://x.com/{handle}")
        if link not in by_handle.setdefault(handle, []):
            by_handle[handle].append(link)

    rendered: list[str] = []
    for handle, links in by_handle.items():
        if len(links) == 1:
            rendered.append(f"[@{handle}]({links[0]})")
        else:
            link_refs = "、".join(f"[{index + 1}]({link})" for index, link in enumerate(links))
            rendered.append(f"@{handle}（{len(links)}条：{link_refs}）")
    return "引用来源：" + "；".join(rendered)


def compact_tag_line(topic: dict[str, Any]) -> str:
    tags = topic.get("tags", {})
    tag_parts = []
    for key, label in (
        ("companies", "公司"),
        ("models", "模型"),
        ("people", "人物/账号"),
        ("topics", "主题标签"),
    ):
        values = tags.get(key, [])
        if values:
            tag_parts.append(f"{label}: {', '.join(values)}")
    return "标签: " + " | ".join(tag_parts) if tag_parts else ""


def topic_category(topic: dict[str, Any]) -> dict[str, str]:
    raw = topic.get("category", {})
    category_id = str(raw.get("id") or "")
    fallback = CATEGORY_BY_ID.get(category_id, {})
    return {
        "id": category_id or str(fallback.get("id") or "uncategorized"),
        "label_zh": str(raw.get("label_zh") or fallback.get("label_zh") or "其他"),
        "label_en": str(raw.get("label_en") or fallback.get("label_en") or "Other"),
    }


def hotspot_validation_line(topic: dict[str, Any]) -> str:
    hotspot = topic.get("hotspot", {})
    experts = [f"@{handle}" for handle in hotspot.get("expert_accounts", [])]
    parts = [
        f"讨论账号 {int(hotspot.get('discussion_accounts', 0) or 0)} 个",
        f"互动反馈 {int(hotspot.get('feedback_total', 0) or 0)}",
        f"热点分 {float(hotspot.get('score', topic.get('score', 0)) or 0):.1f}",
    ]
    if experts:
        parts.insert(1, "专家验证 " + "、".join(experts[:4]))
    return "信源质量：" + "；".join(parts) + "。"


def hotspot_coverage_line(item: dict[str, Any]) -> str:
    category = item.get("category", {})
    label = str(category.get("label_zh") or "其他")
    status = str(item.get("status") or "")
    top = item.get("top_candidate", {})
    title = str(top.get("title_zh") or "无候选")
    if status == "published":
        return f"- 【{label}】正式发布：{title}"
    if status == "candidate_rejected":
        accounts = "、".join(f"@{handle}" for handle in top.get("source_accounts", [])[:3])
        suffix = f"（{accounts}）" if accounts else ""
        return f"- 【{label}】候选未发布：{title}{suffix}"
    return f"- 【{label}】未抓到候选主题"


def source_citation_lines(topic: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    by_handle: dict[str, list[str]] = {}
    for post in topic.get("posts", []):
        handle = str(post.get("author_handle"))
        link = str(post.get("url") or f"https://x.com/{handle}")
        if link not in by_handle.setdefault(handle, []):
            by_handle[handle].append(link)

    for handle, links in by_handle.items():
        if len(links) == 1:
            lines.append(f"- [@{handle}]({links[0]})")
        else:
            rendered = "、".join(f"[{index + 1}]({link})" for index, link in enumerate(links))
            lines.append(f"- @{handle}: {rendered}")
    return lines


def render_hotspot_topic_viewpoint_summary(topic: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    views = compact_account_views(topic)
    if views:
        lines.extend(views)
    else:
        summary = zh_topic_summary(topic)
        if summary:
            lines.append(summary)
    stance_notes = topic.get("analysis", {}).get("stance_notes_zh", {})
    differing_views: list[str] = []
    for key in ("skeptical", "supportive", "observational"):
        for note in stance_notes.get(key, []):
            if note and note not in differing_views:
                differing_views.append(str(note))
    if len(differing_views) >= 2:
        lines.append("不同观点：" + "；".join(differing_views[:3]))
    return lines


def render_markdown_zh_hotspots(digest: dict[str, Any]) -> str:
    categories = digest.get("hotspot_categories") or [
        {
            "id": category["id"],
            "label_zh": category["label_zh"],
            "label_en": category["label_en"],
        }
        for category in HOTSPOT_CATEGORIES
    ]
    topics_by_category: dict[str, list[dict[str, Any]]] = {str(category["id"]): [] for category in categories}
    for topic in digest.get("topics", []):
        category = topic_category(topic)
        topics_by_category.setdefault(category["id"], []).append(topic)

    lines: list[str] = []
    if not digest["topics"]:
        reason = digest.get("quality", {}).get("reason") or "今天候选池内没有足够的新内容生成热点。"
        lines.extend(["# AI 热点简报", "", str(reason), ""])
        return "\n".join(lines)

    for category in categories:
        category_topics = topics_by_category.get(str(category["id"]), [])
        if not category_topics:
            continue
        lines.extend([f"#【{category['label_zh']}】", ""])
        for topic in category_topics:
            lines.extend([f"##【{compact_topic_title_zh(topic)}】", ""])
            lines.extend(render_hotspot_topic_viewpoint_summary(topic))
            lines.extend(["", "###引用来源："])
            lines.extend(source_citation_lines(topic))
            lines.append("")
    return "\n".join(lines)


def render_markdown_zh_compact(digest: dict[str, Any]) -> str:
    domain_name = digest["domain"]["display_name"]
    today = dt.datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# {domain_name} 每日简报 - {today}",
        "",
        f"今日从账号池中抓取 {digest['stats']['posts']} 条帖子，筛选出 {digest['stats']['topics']} 个高信号主题。",
        "",
    ]
    if not digest["topics"]:
        reason = digest.get("quality", {}).get("reason") or "今天账号池内没有足够的新内容生成热点。"
        lines.extend([str(reason), ""])
        return "\n".join(lines)

    lines.append("## 今日要点")
    for topic in digest["topics"]:
        accounts = ", ".join(f"@{handle}" for handle in topic["source_accounts"][:5])
        lines.append(f"- {compact_topic_title_zh(topic)}（{accounts}）")
    lines.append("")

    for topic in digest["topics"]:
        lines.extend([f"## {topic['id']}. {compact_topic_title_zh(topic)}", ""])
        if len(topic.get("posts", [])) > 1 or len(topic.get("source_accounts", [])) > 1:
            lines.extend(compact_account_views(topic))
            tag_line = compact_tag_line(topic)
            if tag_line:
                lines.extend(["", tag_line])
            lines.append("")
        lines.extend([compact_source_citation(topic), ""])
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


def trend_output_paths(domain_id: str, days: int) -> tuple[Path, Path]:
    stamp = dt.datetime.now().strftime("%Y-%m-%d")
    out_dir = config_home() / "trends"
    return out_dir / f"{stamp}-{domain_id}-{days}d.json", out_dir / f"{stamp}-{domain_id}-{days}d.md"


def write_trend_outputs(domain_id: str, days: int, report: dict[str, Any], markdown: str) -> tuple[Path, Path]:
    json_path, md_path = trend_output_paths(domain_id, days)
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    return json_path, md_path


def digest_date(path: Path, digest: dict[str, Any]) -> dt.date | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})-", path.name)
    if match:
        return dt.date.fromisoformat(match.group(1))
    generated_at = str(digest.get("generated_at") or "")
    if generated_at[:10]:
        try:
            return dt.date.fromisoformat(generated_at[:10])
        except ValueError:
            return None
    return None


def load_recent_digests(domain_id: str, days: int) -> list[tuple[Path, dict[str, Any]]]:
    runs_dir = config_home() / "runs"
    if not runs_dir.exists():
        return []
    cutoff = dt.date.today() - dt.timedelta(days=days - 1)
    result: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(runs_dir.glob(f"*-{domain_id}.json")):
        try:
            digest = load_json(path)
        except (json.JSONDecodeError, OSError):
            continue
        date = digest_date(path, digest)
        if date and date >= cutoff and digest.get("domain", {}).get("id") == domain_id:
            result.append((path, digest))
    return result


def build_trend_report(domain_id: str, days: int) -> dict[str, Any]:
    digests = load_recent_digests(domain_id, days)
    topic_counter: Counter[str] = Counter()
    company_counter: Counter[str] = Counter()
    model_counter: Counter[str] = Counter()
    people_counter: Counter[str] = Counter()
    account_counter: Counter[str] = Counter()
    titles: list[dict[str, Any]] = []
    total_posts = 0
    for path, digest in digests:
        total_posts += int(digest.get("stats", {}).get("posts", 0))
        for topic in digest.get("topics", []):
            title = zh_topic_title(topic)
            titles.append(
                {
                    "date": path.name[:10],
                    "title": title,
                    "score": topic.get("score", 0),
                    "accounts": topic.get("source_accounts", []),
                    "tags": topic.get("tags", {}),
                }
            )
            tags = topic.get("tags", {})
            topic_counter.update(tags.get("topics", []))
            company_counter.update(tags.get("companies", []))
            model_counter.update(tags.get("models", []))
            people_counter.update(tags.get("people", []))
            account_counter.update(topic.get("source_accounts", []))
    return {
        "schema_version": "0.2",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "domain": normalize_domain(domain_id),
        "days": days,
        "runs": len(digests),
        "stats": {
            "posts": total_posts,
            "topics": len(titles),
        },
        "top_tags": {
            "topics": topic_counter.most_common(12),
            "companies": company_counter.most_common(12),
            "models": model_counter.most_common(12),
            "people": people_counter.most_common(12),
            "accounts": account_counter.most_common(12),
        },
        "recent_topics": sorted(titles, key=lambda item: float(item.get("score", 0)), reverse=True)[:20],
    }


def render_trend_markdown(report: dict[str, Any]) -> str:
    domain = report["domain"]
    days = report["days"]
    lines = [
        f"# {domain} 最近 {days} 天趋势",
        "",
        f"共读取 {report['runs']} 次历史运行，覆盖 {report['stats']['posts']} 条帖子、{report['stats']['topics']} 个主题。",
        "",
    ]
    if not report["runs"] or not report["recent_topics"]:
        lines.extend(["历史数据不足，暂时无法生成趋势总结。请先运行几天 newsletter。", ""])
        return "\n".join(lines)

    lines.append("## 高频标签")
    for key, label in (
        ("topics", "主题"),
        ("companies", "公司"),
        ("models", "模型"),
        ("people", "人物/账号"),
        ("accounts", "引用账号"),
    ):
        values = report["top_tags"].get(key, [])
        if values:
            rendered = ", ".join(f"{tag}({count})" for tag, count in values[:8])
            lines.append(f"- {label}: {rendered}")
    lines.append("")

    lines.append("## 主要趋势")
    top_topic_tags = [tag for tag, _ in report["top_tags"].get("topics", [])[:5]]
    top_models = [tag for tag, _ in report["top_tags"].get("models", [])[:5]]
    top_companies = [tag for tag, _ in report["top_tags"].get("companies", [])[:5]]
    if top_topic_tags:
        lines.append(f"- 讨论主轴集中在 {', '.join(top_topic_tags)}。")
    if top_models:
        lines.append(f"- 被反复提及的模型包括 {', '.join(top_models)}。")
    if top_companies:
        lines.append(f"- 公司/组织层面的高频对象包括 {', '.join(top_companies)}。")
    if not (top_topic_tags or top_models or top_companies):
        lines.append("- 历史主题较分散，尚未形成稳定趋势。")
    lines.append("")

    lines.append("## 高信号历史主题")
    for item in report["recent_topics"][:10]:
        accounts = ", ".join(f"@{handle}" for handle in item.get("accounts", [])[:4])
        lines.append(f"- {item['date']} {item['title']} | {accounts}")
    lines.append("")
    return "\n".join(lines)


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
    hotspot_mode = bool(args.hotspots)
    if hotspot_mode:
        config["_hotspot_mode"] = True
        config["_runtime_expert_handles"] = select_hotspot_expert_handles(config, args.date)
    if args.input_json:
        posts = fixture_posts(Path(args.input_json), accounts)
        if hotspot_mode:
            config["_hotspot_fetch"] = {"source": "fixture", "input_json": args.input_json}
    elif hotspot_mode:
        posts, fetch_stats = fetch_hotspots_with_bird(
            domain_id,
            accounts,
            config,
            int(args.lookback_hours or config.get("lookback_hours", 24)),
            args.date,
        )
        config["_hotspot_fetch"] = fetch_stats
    else:
        posts = fetch_with_bird(
            accounts,
            int(args.lookback_hours or config.get("lookback_hours", 24)),
            int(args.posts_per_account or config.get("posts_per_account", 8)),
            args.date,
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


def cmd_trend(args: argparse.Namespace) -> None:
    domain_id = normalize_domain(args.domain)
    days = int(args.days)
    report = build_trend_report(domain_id, days)
    markdown = render_trend_markdown(report)
    json_path, md_path = write_trend_outputs(domain_id, days, report, markdown)
    if args.markdown:
        print(markdown)
        return
    print(
        json.dumps(
            {
                "status": "ok",
                "domain": domain_id,
                "days": days,
                "runs": report["runs"],
                "topics": report["stats"]["topics"],
                "json_path": str(json_path),
                "markdown_path": str(md_path),
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
    run.add_argument("--date", help="Fetch a specific UTC date using YYYY-MM-DD, e.g. 2026-05-04.")
    run.add_argument("--lookback-hours", type=int)
    run.add_argument("--posts-per-account", type=int)
    run.add_argument("--input-json", help="Use a fixture JSON file instead of calling bird.")
    run.add_argument("--hotspots", action="store_true", help="Use wide discovery plus expert validation for AI hotspots.")
    run.add_argument("--no-deliver", action="store_true")
    run.set_defaults(func=cmd_run)

    trend = sub.add_parser("trend")
    trend.add_argument("domain")
    trend.add_argument("--days", type=int, default=7, choices=[7, 30])
    trend.add_argument("--markdown", action="store_true", help="Print the trend Markdown instead of the output paths.")
    trend.set_defaults(func=cmd_trend)

    history = sub.add_parser("history")
    history.add_argument("domain")
    history.add_argument("--days", type=int, default=30, choices=[7, 30])
    history.add_argument("--markdown", action="store_true", help="Print the history Markdown instead of the output paths.")
    history.set_defaults(func=cmd_trend)

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
