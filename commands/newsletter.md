# Personal Newsletter

Generate a daily newsletter from curated AI or US stocks X account pools.

Use:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py run ai
python3 skills/personal-newsletter/scripts/newsletter.py run us-stocks
```

Preview without delivery:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py run ai --no-deliver
```

Common configuration:

```bash
python3 skills/personal-newsletter/scripts/newsletter.py config set language zh-CN
python3 skills/personal-newsletter/scripts/newsletter.py config set delivery.kind webhook
python3 skills/personal-newsletter/scripts/newsletter.py config set delivery.url https://example.com/webhook
```
