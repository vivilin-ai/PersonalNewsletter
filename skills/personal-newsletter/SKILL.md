---
name: personal-newsletter
description: Use this skill when the user wants to generate, preview, configure, or deliver a personalized daily newsletter from curated X/Twitter account pools for AI or US stocks. It supports user-added accounts, multilingual output, source-account citations, email delivery, and OpenClaw/Telegram/Feishu-style webhook delivery. The default X data source is the free cookie-based `bird` CLI.
---

# Personal Newsletter

Use this skill to create a daily account-pool newsletter from X posts in the `ai` or `us-stocks` domains.

## Workflow

1. Check X access:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py diagnose
```

The bundled Bird-compatible searcher requires an authenticated X session. On a local desktop, this usually comes from Chrome, Safari, or Firefox already being logged into X. On macOS, Chrome may ask for Keychain access. Safari cookie access may require Full Disk Access for the terminal/OpenClaw host app. On a server or headless OpenClaw install, browser cookies are usually unavailable, so the user must provide X cookie values through environment variables.

If the bundled searcher is unavailable or Node.js is missing, tell the user to install Node.js 22+ or configure an external Bird command:

```bash
export PERSONAL_NEWSLETTER_BIRD_CMD="bird"
python3 skills/personal-newsletter/scripts/newsletter.py diagnose
```

For server deployments, tell the user to configure X cookies in the OpenClaw process environment:

```bash
export AUTH_TOKEN="your_x_auth_token_cookie"
export CT0="your_x_ct0_cookie"
```

Cookie setup steps:

1. Log into X in a browser the user controls.
2. Open developer tools and inspect cookies for `x.com`.
3. Copy `auth_token` into `AUTH_TOKEN` and `ct0` into `CT0`.
4. Store them only in server secrets or environment variables.
5. Restart OpenClaw, then run `bird check` and `python3 skills/personal-newsletter/scripts/newsletter.py diagnose`.

Warn the user that `AUTH_TOKEN` and `CT0` are sensitive login credentials and must not be committed, logged, or shared.

2. Generate or preview:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py run ai --no-deliver
python3 skills/personal-newsletter/scripts/newsletter.py run us-stocks --no-deliver
python3 skills/personal-newsletter/scripts/newsletter.py run ai --date 2026-05-04 --no-deliver
python3 skills/personal-newsletter/scripts/newsletter.py run ai --hotspots --no-deliver
```

Default language is `zh-CN`. In Chinese mode, the generated Markdown must be a Chinese editorial newsletter: summarize and translate X content into Chinese, cite accounts and links, and avoid placing raw English tweet text in the body. Raw source text remains available in the JSON payload for grounding.

The generator uses a two-stage pipeline:

1. Build structured topic JSON from account-pool posts.
2. Render the structured topics into Markdown.

For AI hotspot discovery, prefer `run ai --hotspots`. This mode uses a wider discovery layer plus expert validation:

- The 52-account personal expert pool in `data/x-lists/swyx_ai_high_signal_expert_handles_v1.json` validates and explains topics. Core and signal experts both rotate to keep public-use request volume below common X rate-limit pressure.
- The 8-column expert registry in `data/x-lists/swyx_ai_high_signal_expert_categories_v1.json` is the preferred validation registry for `--hotspots`; it is larger than the runtime fetch set and must be sampled, not fetched in full.
- The broader `swyx/AI High Signal` candidate list is rotated as a discovery pool. Organization, project, and product accounts may be used for discovery, but they are not counted as personal expert validation unless explicitly added to the expert handles file.
- Event-style keyword searches for each column catch fast-moving discussion that may not originate from the expert pool. Prefer queries that combine topic terms with release/action terms such as released, launched, benchmark, open-sourced, funding, reorg, vulnerability, or prompt injection.
- Hotspot mode is organized into 8 fixed columns: foundation models, evals/benchmarks, training/optimization, inference/infrastructure, agent engineering, products, organization/strategy, and safety/security.

Each hotspot run includes `candidate_coverage`, an 8-column diagnostic that separates `published`, `candidate_rejected`, and `missing` columns. Each published hotspot topic includes a `category` object and a `hotspot` object in the JSON payload with discussion-account count, expert accounts, feedback total, and a combined hotspot score.

Published hotspots must pass column-specific relevance checks. For example, organization/strategy requires concrete org, workforce, leadership, hiring, layoff, lab, or strategy language; generic mentions of "agent" or "team morale" are only candidates and should not be published.

Each topic includes:

- `analysis`: Chinese title, summary, key points, and stance notes.
- `tags`: `companies`, `models`, `people`, and `topics`.
- `quality`: topic-level signal metadata.
- `posts`: original source posts and URLs for grounding.

If the account pool has too little substantive activity, the skill should emit a low-signal issue instead of inventing generic热点.

Chinese newsletter rendering should be concise:

- In `--hotspots` mode, render only published topics in this structure: `#【栏目】`, then `##【话题】`, then the synthesized Chinese viewpoint summary body, then `### 引用来源：`. The summary body should cover each side's view, especially meaningful disagreements, but must not include instruction text such as "总结该话题下各方的观点，特别是不同的观点。". Do not tell end users how many posts were fetched, how many columns were unpublished, or why a topic deserves publication.
- If a topic has only one source account, keep it only when the post feedback is high enough. By default, single-account topics need more than 100 replies/quote replies.
- If one account posts multiple times in the same topic, merge those posts into one account-level viewpoint instead of listing repeated viewpoints.
- Do not repeat the same post content in the summary, viewpoint section, and source section. Prefer a compact heading, one synthesized viewpoint when needed, optional tags for multi-post topics, and a compact source citation.

Use `--language en` only when the user explicitly asks for English.

3. Review the generated Markdown path printed by the command. If the user wants a richer final issue, use the JSON payload path from the command output and synthesize a polished Chinese newsletter, translating source posts into Chinese while preserving source account citations and original links.

4. Summarize historical trends:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py trend ai --days 7
python3 skills/personal-newsletter/scripts/newsletter.py history ai --days 30 --markdown
```

Trend/history commands read prior `.personal-newsletter/runs/*.json` files and summarize recurring tags, models, companies, accounts, and high-signal topics.

5. Deliver when configured:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py run ai
```

## User Configuration

Configuration lives in the current workspace at `.personal-newsletter/config.json` unless `PERSONAL_NEWSLETTER_HOME` is set.

Useful commands:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py list-domains
python3 skills/personal-newsletter/scripts/newsletter.py list-accounts ai
python3 skills/personal-newsletter/scripts/newsletter.py add-account ai handle --label "Display Name" --tier signal
python3 skills/personal-newsletter/scripts/newsletter.py trend ai --days 7
python3 skills/personal-newsletter/scripts/newsletter.py config set language zh-CN
python3 skills/personal-newsletter/scripts/newsletter.py config set delivery.kind webhook
python3 skills/personal-newsletter/scripts/newsletter.py config set delivery.url https://example.com/webhook
python3 skills/personal-newsletter/scripts/newsletter.py diagnose
```

## Delivery

Supported delivery kinds:

- `none`: generate files only.
- `webhook`: POST to OpenClaw, Telegram bridge, Feishu/Lark bot, Slack-compatible webhook, or any generic webhook URL.
- `email`: send through SMTP environment variables.

Email environment variables:

```bash
NEWSLETTER_SMTP_HOST
NEWSLETTER_SMTP_PORT
NEWSLETTER_SMTP_USER
NEWSLETTER_SMTP_PASSWORD
NEWSLETTER_EMAIL_FROM
NEWSLETTER_EMAIL_TO
```

## Account Pools

Built-in account pools live in `domains/ai.json` and `domains/us_stocks.json`. They are curated seeds, not exhaustive lists.

Each account has:

- `handle`: X handle without `@`.
- `label`: human-readable name.
- `role`: perspective category.
- `tier`: `core`, `signal`, or `edge`.
- `weight`: ranking weight.
- `tags`: topical tags.
- `rationale`: why this account belongs in the seed pool.

User-added accounts are merged on top of built-ins and are never written into the bundled domain files.

## Data Source Notes

The default provider uses `scripts/vendor/bird-search/bird-search.mjs` with queries such as `from:handle since:YYYY-MM-DD`. It first asks for JSON output and falls back to parsing human output when needed. This keeps the skill free to run, but it inherits the reliability limits of X web-cookie access.

Set `PERSONAL_NEWSLETTER_BIRD_CMD` if `bird` is installed under another command name. Set `PERSONAL_NEWSLETTER_BIRD_MJS` to use a vendored Bird-compatible `.mjs` search wrapper. For headless servers, prefer `AUTH_TOKEN` and `CT0` environment variables over browser-cookie discovery.
