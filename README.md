# Personal Newsletter Skill

Generate daily newsletters from curated X account pools for AI and US stocks.

The default X provider is `bird`, which uses the user's own browser cookies or configured engine. That keeps the project open-source friendly and avoids requiring a paid X API key. The implementation is intentionally dependency-free Python so it can run inside OpenClaw, Codex, Claude Code, or a local cron job.

## Quick Start

Install and authenticate `bird` first:

```bash
openclaw skill add steipete/bird
bird check
```

Bird must have access to an authenticated X session. On a local desktop this usually means Chrome/Firefox is already logged into X. On a headless server, there is usually no browser session, so `bird check` will fail unless you provide X cookies manually.

## Server / OpenClaw Auth

For a server deployment, configure X cookies as environment variables in the OpenClaw process environment:

```bash
export AUTH_TOKEN="your_x_auth_token_cookie"
export CT0="your_x_ct0_cookie"
```

How to get them:

1. Log into X in a browser you control.
2. Open developer tools and inspect cookies for `x.com`.
3. Copy the values of `auth_token` and `ct0`.
4. Put them into the server's secret manager, service environment, or shell profile as `AUTH_TOKEN` and `CT0`.
5. Restart OpenClaw and run `bird check`.

Treat these cookie values like passwords. Do not commit them to git, do not paste them into shared logs, and rotate them by logging out of X if they leak.

Preview a newsletter:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py run ai --no-deliver
python3 skills/personal-newsletter/scripts/newsletter.py run us-stocks --no-deliver
```

Run a specific day:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py run ai --date 2026-05-04 --no-deliver
```

The default newsletter language is Chinese. The Markdown output summarizes and translates X content into Chinese by default, while the JSON output keeps original source text for grounding and later refinement by an agent.

Add a personal account:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py add-account ai karpathy --label "Andrej Karpathy" --tier core
```

Configure delivery:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py config set language zh-CN
python3 skills/personal-newsletter/scripts/newsletter.py config set delivery.kind webhook
python3 skills/personal-newsletter/scripts/newsletter.py config set delivery.url https://example.com/webhook
```

Email delivery uses SMTP environment variables:

```bash
NEWSLETTER_SMTP_HOST=smtp.example.com
NEWSLETTER_SMTP_PORT=587
NEWSLETTER_SMTP_USER=you@example.com
NEWSLETTER_SMTP_PASSWORD=...
NEWSLETTER_EMAIL_FROM=you@example.com
NEWSLETTER_EMAIL_TO=you@example.com
```

User config is stored in the current workspace at `.personal-newsletter/config.json` unless `PERSONAL_NEWSLETTER_HOME` is set.
