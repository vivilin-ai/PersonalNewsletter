# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A Python CLI that generates daily newsletters from curated X (Twitter) account pools for two domains: AI and US stocks. The default output language is Chinese (zh-CN). The skill can be invoked from Claude Code, OpenClaw, or Codex.

## Commands

### Run tests

```bash
pytest
# or a single test:
pytest tests/test_newsletter.py::NewsletterTests::test_build_digest_clusters_fixture_posts
```

Tests use Python's stdlib `unittest` and run under `pytest`. No external Python dependencies are required.

### Run the newsletter (requires Node.js 22+ and an authenticated X session)

```bash
# Check X auth and environment
python3 skills/personal-newsletter/scripts/newsletter.py diagnose

# Preview without delivery
python3 skills/personal-newsletter/scripts/newsletter.py run ai --no-deliver
python3 skills/personal-newsletter/scripts/newsletter.py run us-stocks --no-deliver

# AI hotspot mode (uses wider discovery pool + expert validation)
python3 skills/personal-newsletter/scripts/newsletter.py run ai --hotspots --no-deliver

# Specific date
python3 skills/personal-newsletter/scripts/newsletter.py run ai --date 2026-05-04 --no-deliver

# Trend / history summary from prior runs
python3 skills/personal-newsletter/scripts/newsletter.py trend ai --days 7
python3 skills/personal-newsletter/scripts/newsletter.py history ai --days 30 --markdown

# Account pool management
python3 skills/personal-newsletter/scripts/newsletter.py list-accounts ai
python3 skills/personal-newsletter/scripts/newsletter.py add-account ai karpathy --label "Andrej Karpathy" --tier core
python3 skills/personal-newsletter/scripts/newsletter.py disable-account ai somehandle

# Config
python3 skills/personal-newsletter/scripts/newsletter.py config show
python3 skills/personal-newsletter/scripts/newsletter.py config set language zh-CN
python3 skills/personal-newsletter/scripts/newsletter.py config set delivery.kind webhook
python3 skills/personal-newsletter/scripts/newsletter.py config set delivery.url https://example.com/webhook
```

## Architecture

All logic lives in a single self-contained file: `skills/personal-newsletter/scripts/newsletter.py` (~2600 lines, no external Python dependencies).

### Data flow

1. **Fetch** — `fetch_with_bird()` or `fetch_hotspots_with_bird()` calls the Bird searcher (`scripts/vendor/bird-search/bird-search.mjs` via Node.js, or an external `bird` CLI) to retrieve posts from configured X accounts.
2. **Normalize / Score** — `normalize_post()` and `score_post()` standardize the raw JSON and compute a weighted engagement score (tier bonus + likes/replies/quotes/reposts/views).
3. **Cluster** — `cluster_posts()` tokenizes post text, groups posts with overlapping keywords into topics, and selects the top-scored clusters.
4. **Quality gate** — `apply_quality_gate()` / `apply_hotspot_quality_gate()` drops low-signal topics before they reach the digest.
5. **Render** — `render_markdown()` dispatches to a language/mode-specific renderer (`render_markdown_zh_compact`, `render_markdown_zh_hotspots`, `render_markdown_en`).
6. **Deliver** — `deliver()` sends the Markdown via webhook, SMTP email, or Telegram.

### Hotspot mode (`--hotspots`)

Used for the AI domain only. Replaces the standard per-account pool with three parallel fetch layers:

- **Category expert pool** (`data/x-lists/swyx_ai_high_signal_expert_categories_v1.json`): per-column experts sampled each run according to `runtime_sample` values.
- **Discovery pool** (`data/x-lists/swyx_ai_high_signal_handles.json`): wider candidate list rotated daily.
- **Keyword searches**: 8 fixed queries targeting each of the 8 hotspot columns.

Topics are clustered per column (`HOTSPOT_CATEGORIES`), annotated with expert-validation and discussion-account scores (`annotate_hotspot_topics()`), and filtered by a stricter quality gate that also checks column-specific relevance (`hotspot_category_publish_relevance_ok()`).

### Account pools

Built-in pools live in `skills/personal-newsletter/domains/ai.json` and `domains/us_stocks.json`. User-added accounts are stored in `.personal-newsletter/config.json` and merged on top of builtins by `merged_accounts()`. Builtin files should not be edited for personal customization.

### Configuration

Config is loaded by `load_config()` which deep-merges `DEFAULT_CONFIG` with `.personal-newsletter/config.json` (or the directory set by `PERSONAL_NEWSLETTER_HOME`). All `config set` writes go to the user config only; builtins are untouched.

### Output

Each run writes two files to `.personal-newsletter/runs/`:
- `YYYY-MM-DD-{domain}.json` — full structured digest (schema version 0.2)
- `YYYY-MM-DD-{domain}.md` — rendered Markdown newsletter

`trend` / `history` writes to `.personal-newsletter/trends/`.

## Key environment variables

| Variable | Purpose |
|---|---|
| `AUTH_TOKEN` / `CT0` | X cookie values for headless / server deployments |
| `PERSONAL_NEWSLETTER_HOME` | Override config + output directory (useful in tests) |
| `PERSONAL_NEWSLETTER_BIRD_CMD` | Use a custom external `bird` CLI command |
| `PERSONAL_NEWSLETTER_BIRD_MJS` | Use a custom vendored `.mjs` Bird wrapper |
| `NEWSLETTER_SMTP_HOST/PORT/USER/PASSWORD` | SMTP email delivery |
| `NEWSLETTER_EMAIL_FROM/TO` | Email delivery addresses |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | Telegram delivery |

## Testing notes

Tests import `newsletter.py` via `importlib` rather than installing it as a package. Use `PERSONAL_NEWSLETTER_HOME` (via the `temp_home()` context manager) to isolate config and output from the real workspace. Fixture posts live in `tests/fixtures/sample_posts.json`; pass them with `--input-json` or `fixture_posts()` to avoid needing live X access.
