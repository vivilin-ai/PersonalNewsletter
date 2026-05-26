# AI Hotspot Newsletter Iterations

Last updated: 2026-05-26

This document records the major iterations made while turning the AI X newsletter from an expert-post leaderboard into a column-based hotspot digest.

## Goals

- Build a public-user-safe AI hotspot newsletter from X without aggressively increasing X request volume.
- Separate broad hotspot discovery from personal expert validation.
- Keep the final newsletter concise, Chinese-first, source-cited, and free of internal diagnostics.

## Expert Pool And Source Strategy

- Started from the `swyx/AI High Signal` X list with 606 accounts.
- Built a 52-account personal expert pool for high-quality validation.
- Expanded this into an 8-column expert registry with 97 unique personal experts.
- Kept organization, project, and product accounts available for discovery, but not as personal expert validation.
- Added runtime sampling from the larger registry so the default run does not fetch all experts.

## Eight Hotspot Columns

The hotspot mode uses 8 fixed columns:

- Foundation models
- Evals and benchmarks
- Training and optimization
- Inference and infrastructure
- Agent engineering
- Products
- Organization and strategy
- Safety and security

Each published topic is assigned to one of these columns. The JSON keeps `candidate_coverage` for diagnostics, but the Markdown only renders published topics.

## Discovery And Quality Iterations

- Replaced broad keyword queries with event-style queries that combine topic terms with actions such as `released`, `launched`, `benchmark`, `open-sourced`, `funding`, `reorg`, and `vulnerability`.
- Added `candidate_coverage` to distinguish `published`, `candidate_rejected`, and `missing` columns.
- Added column-specific relevance checks to avoid publishing high-engagement but irrelevant posts.
- Added an AI-context requirement for categories that are prone to false positives, such as training, inference, product, organization, and safety.
- Added regression tests for false positives:
  - Non-AI movie/sports `training` posts must not publish as training and optimization.
  - Generic `agent/team morale` chatter must not publish as organization strategy.

## Newsletter Rendering Iterations

- Removed public-facing diagnostics from Markdown:
  - Number of fetched posts
  - Number of unpublished columns
  - Candidate rejection reasons
  - Internal "why this topic is worth publishing" explanations
- Standardized the public Markdown format:

```markdown
#【栏目】

##【话题】

中文综合段落，总结各方观点和有意义的分歧。

### 引用来源：
- ...
```

- Replaced per-tweet bullet summaries with Chinese editorial paragraphs.
- Added deterministic editorial templates for recurring topic shapes, including:
  - Claude for Legal / Claude Agent SDK
  - Symbolic learning as a learning substrate
  - Verifiable coding/math tasks
  - GitHub Copilot context and developer workflow

## Current Known Limitations

- The current renderer is still rule/template based, so topic titles and summaries can be uneven for new topic shapes.
- Low-budget X search can find candidates across all columns, but it cannot guarantee every column has a publishable topic every day.
- Quality depends heavily on query design and the relevance gate. Broad terms such as `training`, `agent`, or `released` require strict AI-context filtering.
- Future improvement should route candidate topics through a stronger summarization step before Markdown rendering.

## Verification

- Latest unit test run after these changes: `python3.13 -m unittest tests/test_newsletter.py`
- Current result: 15 tests passing.
