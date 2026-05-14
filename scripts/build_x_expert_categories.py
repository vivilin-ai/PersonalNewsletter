#!/usr/bin/env python3
"""Build an 8-column AI expert registry from the swyx AI High Signal list.

This is an offline profile-based classifier. It intentionally builds a larger
expert registry than the runtime fetch set; runtime code should sample from it
instead of querying every listed account.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data/x-lists/swyx_ai_high_signal_members_raw.json"
CURATED_PATH = ROOT / "data/x-lists/swyx_ai_high_signal_expert_pool_v1_curated.json"
OUTPUT_PATH = ROOT / "data/x-lists/swyx_ai_high_signal_expert_categories_v1.json"

CATEGORIES: list[dict[str, Any]] = [
    {
        "id": "foundation_models",
        "label_zh": "基座模型",
        "label_en": "Foundation Models",
        "runtime_sample": 2,
        "terms": {
            "model": 3,
            "models": 3,
            "foundation": 4,
            "frontier": 4,
            "llm": 3,
            "llms": 3,
            "multimodal": 4,
            "reasoning": 3,
            "gemini": 4,
            "deepthink": 4,
            "claude": 3,
            "gpt": 3,
            "openai": 2,
            "anthropic": 2,
            "deepseek": 4,
            "qwen": 4,
            "kimi": 4,
            "llama": 3,
            "mistral": 3,
            "pre-training": 2,
            "pretraining": 2,
        },
    },
    {
        "id": "evals_benchmarks",
        "label_zh": "评测与基准",
        "label_en": "Evals and Benchmarks",
        "runtime_sample": 2,
        "terms": {
            "eval": 5,
            "evals": 5,
            "evaluation": 4,
            "benchmark": 5,
            "benchmarks": 5,
            "leaderboard": 4,
            "swe-bench": 5,
            "swe-agent": 4,
            "frontiermath": 5,
            "arc": 3,
            "arc-agi": 5,
            "mmlu": 4,
            "hle": 4,
            "gorilla": 4,
            "openfunctions": 4,
            "medarc": 4,
            "sophont": 4,
            "red-teaming": 3,
        },
    },
    {
        "id": "training_optimization",
        "label_zh": "训练与优化",
        "label_en": "Training and Optimization",
        "runtime_sample": 2,
        "terms": {
            "training": 5,
            "train": 3,
            "pretraining": 5,
            "pre-training": 5,
            "post-training": 5,
            "posttraining": 5,
            "rl": 4,
            "rlhf": 5,
            "rlvr": 5,
            "optimization": 4,
            "optimizer": 4,
            "scaling": 4,
            "scaling laws": 5,
            "fine-tuning": 4,
            "finetuning": 4,
            "synthetic data": 4,
            "data curation": 4,
            "distillation": 4,
            "gradient": 3,
            "bitsandbytes": 4,
            "axolotl": 4,
        },
    },
    {
        "id": "inference_infra",
        "label_zh": "推理与基础设施",
        "label_en": "Inference and Infrastructure",
        "runtime_sample": 2,
        "terms": {
            "inference": 5,
            "serving": 5,
            "latency": 4,
            "throughput": 4,
            "kernel": 5,
            "kernels": 5,
            "cuda": 5,
            "gpu": 4,
            "tpu": 4,
            "lpu": 4,
            "hardware": 4,
            "compute": 4,
            "vllm": 5,
            "transformers": 3,
            "rust": 2,
            "compiler": 3,
            "systems": 3,
            "performance": 4,
            "databricks": 2,
            "mosaicml": 3,
            "cerebras": 4,
            "groq": 4,
            "nvidia": 3,
        },
    },
    {
        "id": "agent_engineering",
        "label_zh": "Agent 工程",
        "label_en": "Agent Engineering",
        "runtime_sample": 2,
        "terms": {
            "agent": 5,
            "agents": 5,
            "agentic": 5,
            "multi-agent": 5,
            "tool": 3,
            "tools": 3,
            "function calling": 5,
            "openfunctions": 5,
            "gorilla": 4,
            "coding agent": 5,
            "codex": 4,
            "copilot": 4,
            "claude engineer": 4,
            "mcp": 4,
            "workflow": 3,
            "workflows": 3,
            "automation": 3,
            "openhands": 5,
            "devin": 4,
            "software agents": 5,
        },
    },
    {
        "id": "product_startups",
        "label_zh": "产品",
        "label_en": "Products",
        "runtime_sample": 2,
        "terms": {
            "founder": 4,
            "cofounder": 4,
            "co-founder": 4,
            "ceo": 4,
            "cto": 3,
            "vp": 2,
            "product": 5,
            "startup": 4,
            "building": 3,
            "creator": 3,
            "maintainer": 3,
            "open source": 3,
            "oss": 3,
            "github": 3,
            "developer": 3,
            "devtools": 4,
            "app": 2,
            "api": 2,
            "sdk": 2,
            "cursor": 3,
            "replicate": 3,
            "huggingface": 2,
            "wandb": 3,
        },
    },
    {
        "id": "org_strategy",
        "label_zh": "组织改革",
        "label_en": "Organization and Strategy",
        "runtime_sample": 1,
        "terms": {
            "ceo": 5,
            "cto": 4,
            "vp": 4,
            "director": 4,
            "head of": 5,
            "chief": 5,
            "president": 4,
            "lead": 3,
            "leading": 3,
            "team": 3,
            "teams": 3,
            "lab": 3,
            "labs": 3,
            "strategy": 4,
            "product": 2,
            "applications": 4,
            "board": 3,
            "investor": 3,
            "vc": 3,
            "startup": 2,
            "enterprise": 3,
        },
    },
    {
        "id": "safety_security",
        "label_zh": "安全与治理",
        "label_en": "Safety and Security",
        "runtime_sample": 1,
        "terms": {
            "safety": 5,
            "alignment": 5,
            "interpretability": 5,
            "interp": 4,
            "security": 5,
            "secure": 4,
            "red-teaming": 5,
            "redwood": 5,
            "policy": 4,
            "ethics": 4,
            "governance": 4,
            "risk": 4,
            "risks": 4,
            "rogue": 4,
            "jailbreak": 4,
            "vulnerability": 4,
            "privacy": 3,
            "explainability": 3,
            "understanding ai": 3,
        },
    },
]

PERSONAL_TERMS = [
    "opinions",
    "views",
    "prev",
    "previously",
    "ex-",
    "phd",
    "professor",
    "researcher",
    "scientist",
    "engineer",
    "founder",
    "cofounder",
    "co-founder",
    "ceo",
    "cto",
    "vp",
    "director",
    "head of",
    "lead",
    "mts",
    "mots",
    "creator",
    "maintainer",
    "author",
    "student",
]

ORG_STARTS = (
    "we ",
    "we are",
    "we're",
    "built by",
    "makers of",
    "the ai ",
    "the fastest",
    "a high-throughput",
    "an autonomous",
    "an ai ",
)

ORG_TERMS = [
    "official",
    "community account",
    "company",
    "platform",
    "research-optimized platform",
    "foundation models for",
    "join the waitlist",
    "discord",
    "powered by",
]

HANDLE_CATEGORY_OVERRIDES: dict[str, dict[str, int]] = {
    "sama": {"foundation_models": 8, "product_startups": 6, "org_strategy": 10},
    "karpathy": {"foundation_models": 5, "agent_engineering": 8, "product_startups": 4},
    "swyx": {"agent_engineering": 8, "product_startups": 6, "evals_benchmarks": 4},
    "simonw": {"agent_engineering": 9, "product_startups": 8, "safety_security": 3},
    "goodside": {"foundation_models": 4, "safety_security": 7, "product_startups": 4},
    "idavidrein": {"evals_benchmarks": 12, "foundation_models": 3},
    "ofirpress": {"evals_benchmarks": 12, "agent_engineering": 6},
    "fchollet": {"evals_benchmarks": 9, "foundation_models": 5, "product_startups": 4},
    "hendrycks": {"evals_benchmarks": 10, "safety_security": 8},
    "nabla_theta": {"evals_benchmarks": 8, "safety_security": 8, "training_optimization": 4},
    "random_walker": {"safety_security": 9, "org_strategy": 4},
    "yoshua_bengio": {"safety_security": 12, "org_strategy": 6, "foundation_models": 3},
    "mmitchell_ai": {"safety_security": 10, "evals_benchmarks": 3},
    "owencm": {"safety_security": 9, "org_strategy": 4},
    "thekaransinghal": {"safety_security": 6, "foundation_models": 3, "evals_benchmarks": 3},
    "ryanpgreenblatt": {"safety_security": 12},
    "lilianweng": {"safety_security": 6, "product_startups": 7, "org_strategy": 5, "agent_engineering": 4},
    "shishirpatil_": {"agent_engineering": 12, "evals_benchmarks": 10},
    "_nerdai_": {"agent_engineering": 12},
    "lukehoban": {"agent_engineering": 10, "product_startups": 7, "org_strategy": 5},
    "jeffintime": {"agent_engineering": 8, "product_startups": 4},
    "bfirsh": {"agent_engineering": 7, "product_startups": 5},
    "skirano": {"agent_engineering": 8, "product_startups": 8},
    "gneubig": {"agent_engineering": 7, "product_startups": 5, "evals_benchmarks": 3},
    "edwardsun0909": {"agent_engineering": 10, "training_optimization": 6},
    "xikun_zhang_": {"agent_engineering": 10, "training_optimization": 7},
    "millionint": {"agent_engineering": 8, "foundation_models": 6, "product_startups": 8},
    "tonywu_71": {"agent_engineering": 6, "foundation_models": 5, "inference_infra": 3},
    "jon_lee0": {"foundation_models": 10, "training_optimization": 7, "evals_benchmarks": 4},
    "lmthang": {"foundation_models": 10, "evals_benchmarks": 6},
    "yitayml": {"foundation_models": 10},
    "theophaneweber": {"foundation_models": 8},
    "jhyuxm": {"foundation_models": 8},
    "alex_conneau": {"foundation_models": 6, "product_startups": 7},
    "jack_w_rae": {"foundation_models": 8, "training_optimization": 5},
    "mononofu": {"foundation_models": 6, "training_optimization": 6, "evals_benchmarks": 4},
    "shuchaobi": {"training_optimization": 9, "agent_engineering": 7, "foundation_models": 4},
    "mobav0": {"training_optimization": 9},
    "tim_dettmers": {"training_optimization": 8, "inference_infra": 4},
    "danielhanchen": {"training_optimization": 8, "inference_infra": 5, "product_startups": 5},
    "eliebakouch": {"training_optimization": 7},
    "winglian": {"training_optimization": 6, "product_startups": 8, "agent_engineering": 5},
    "realDanFu".lower(): {"inference_infra": 12, "training_optimization": 4},
    "jonathanross321": {"inference_infra": 12, "product_startups": 5, "org_strategy": 4},
    "zhuohan123": {"inference_infra": 10, "foundation_models": 4},
    "narsilou": {"inference_infra": 9},
    "ml_hardware": {"inference_infra": 9},
    "lateinteraction": {"inference_infra": 7, "evals_benchmarks": 4},
    "yuchenj_uw": {"inference_infra": 6, "product_startups": 7},
    "fraser": {"product_startups": 10, "org_strategy": 8},
    "mikeyk": {"product_startups": 8, "org_strategy": 9},
    "kevinweil": {"org_strategy": 10, "product_startups": 6},
    "fidjissimo": {"org_strategy": 10, "product_startups": 6},
    "russelljkaplan": {"org_strategy": 8, "product_startups": 7, "agent_engineering": 4},
    "realsharonzhou": {"org_strategy": 8, "product_startups": 7, "inference_infra": 3},
    "percyliang": {"evals_benchmarks": 5, "product_startups": 6, "foundation_models": 4},
}


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def norm_handle(value: str) -> str:
    return value.lstrip("@").strip()


def term_score(text: str, terms: dict[str, int]) -> int:
    score = 0
    haystack = f" {text.lower()} "
    for term, weight in terms.items():
        if " " in term or "-" in term:
            if term in haystack:
                score += weight
            continue
        if re.search(rf"(?<![a-z0-9_]){re.escape(term)}(?![a-z0-9_])", haystack):
            score += weight
    return score


def has_any(text: str, terms: list[str]) -> bool:
    lowered = f" {text.lower()} "
    return any(term in lowered for term in terms)


def likely_org(user: dict[str, Any], curated_kind: str) -> bool:
    if curated_kind == "expert_personal":
        return False
    description = str(user.get("description") or "").strip().lower()
    text = f"{user.get('name', '')} {description}".lower()
    if has_any(text, PERSONAL_TERMS):
        return False
    if description.startswith(ORG_STARTS):
        return True
    return has_any(text, ORG_TERMS)


def profile_score(user: dict[str, Any], curated: dict[str, Any] | None) -> int:
    if curated:
        return int(curated.get("profileScore", 0) or 0)
    text = f"{user.get('name', '')} {user.get('description', '')}".lower()
    personal = sum(1 for term in PERSONAL_TERMS if term in f" {text} ")
    technical = sum(
        1
        for term in (
            "ai",
            "ml",
            "llm",
            "research",
            "training",
            "inference",
            "agent",
            "eval",
            "benchmark",
            "model",
            "safety",
            "open source",
            "multimodal",
            "reasoning",
        )
        if term in text
    )
    return personal + technical * 2


def source_tier(handle: str, curated: dict[str, Any] | None) -> tuple[str, int]:
    if not curated:
        return "profile_match", 0
    tier = str(curated.get("tier") or "")
    if tier == "core":
        return "curated_core", 50
    if tier == "signal":
        return "curated_signal", 40
    return "curated_borderline", 20


def category_tier(source: str, category_score: int, final_score: float) -> str:
    if source == "curated_core" or (category_score >= 10 and final_score >= 60):
        return "anchor"
    if source in {"curated_signal", "curated_borderline"} or category_score >= 6:
        return "specialist"
    return "watchlist"


def rationale_for(category_id: str, user: dict[str, Any], category_score: int, source: str) -> str:
    desc = str(user.get("description") or "").strip()
    if len(desc) > 150:
        desc = desc[:149].rstrip() + "..."
    return f"profile matched {category_id} terms (score={category_score}); source={source}; bio={desc}"


def main() -> None:
    raw = load_json(RAW_PATH)
    curated_raw = load_json(CURATED_PATH)
    curated_items = [
        *curated_raw.get("experts", []),
        *curated_raw.get("borderline", []),
    ]
    curated_by_handle = {norm_handle(item["handle"]).lower(): item for item in curated_items}
    org_handles = {
        norm_handle(item["handle"]).lower()
        for item in curated_raw.get("org_signal_pool", [])
        if isinstance(item, dict) and item.get("handle")
    }

    users = raw.get("users", [])
    category_entries: dict[str, list[dict[str, Any]]] = {category["id"]: [] for category in CATEGORIES}
    seen_personal_handles: set[str] = set()

    for user in users:
        handle = norm_handle(str(user.get("username") or ""))
        if not handle:
            continue
        lowered = handle.lower()
        curated = curated_by_handle.get(lowered)
        curated_kind = str(curated.get("kind") or "") if curated else ""
        if lowered in org_handles or likely_org(user, curated_kind):
            continue

        pscore = profile_score(user, curated)
        overrides = HANDLE_CATEGORY_OVERRIDES.get(lowered, {})
        if not curated and pscore < 7 and not overrides:
            continue

        text = f"{handle} {user.get('name', '')} {user.get('description', '')}".lower()
        source, source_bonus = source_tier(handle, curated)
        followers = int(user.get("followersCount") or 0)
        follower_bonus = math.log10(max(followers, 10)) * 2

        matched_any = False
        for category in CATEGORIES:
            cscore = term_score(text, category["terms"])
            cscore += int(overrides.get(category["id"], 0))
            if cscore <= 0:
                continue
            matched_any = True
            final_score = round(source_bonus + cscore * 6 + pscore * 1.5 + follower_bonus, 2)
            category_entries[category["id"]].append(
                {
                    "handle": handle,
                    "label": str(user.get("name") or handle),
                    "tier": category_tier(source, cscore, final_score),
                    "source": source,
                    "category_score": cscore,
                    "profile_score": pscore,
                    "rank_score": final_score,
                    "followersCount": followers,
                    "description": str(user.get("description") or ""),
                    "rationale": rationale_for(category["id"], user, cscore, source),
                }
            )
        if matched_any:
            seen_personal_handles.add(handle)

    categories: list[dict[str, Any]] = []
    all_handles: set[str] = set()
    for category in CATEGORIES:
        entries = sorted(
            category_entries[category["id"]],
            key=lambda item: (
                {"anchor": 2, "specialist": 1, "watchlist": 0}[item["tier"]],
                item["rank_score"],
                item["followersCount"],
            ),
            reverse=True,
        )
        selected: list[dict[str, Any]] = []
        selected_handles: set[str] = set()
        for entry in entries:
            lowered = entry["handle"].lower()
            if lowered in selected_handles:
                continue
            selected_handles.add(lowered)
            selected.append(entry)
            all_handles.add(entry["handle"])
            if len(selected) >= 28:
                break
        categories.append(
            {
                "id": category["id"],
                "label_zh": category["label_zh"],
                "label_en": category["label_en"],
                "runtime_sample": category["runtime_sample"],
                "count": len(selected),
                "experts": selected,
            }
        )

    output = {
        "source": {
            "input_path": str(RAW_PATH.relative_to(ROOT)),
            "curated_path": str(CURATED_PATH.relative_to(ROOT)),
            "output_path": str(OUTPUT_PATH.relative_to(ROOT)),
            "input_count": len(users),
            "personal_candidate_count": len(seen_personal_handles),
            "unique_expert_count": len(all_handles),
        },
        "policy": {
            "purpose": "Large expert registry for 8-column AI hotspot validation. Do not query all accounts in one run.",
            "runtime_default": "Sample by category under a fixed request budget; use organization/project accounts for discovery only, not personal expert validation.",
            "recommended_query_budget": {
                "category_keyword_queries": 8,
                "rotated_discovery_accounts": 8,
                "expert_validation_accounts": 8,
                "total_target_queries": 24,
            },
        },
        "categories": categories,
        "all_handles": sorted(all_handles, key=str.lower),
    }
    write_json(OUTPUT_PATH, output)
    print(json.dumps({
        "output_path": str(OUTPUT_PATH),
        "unique_expert_count": len(all_handles),
        "category_counts": {item["id"]: item["count"] for item in categories},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
