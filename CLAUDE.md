# Claude Instructions for zonaprop-ai

This document is the source of truth for how to work on this project with Claude Code.

## Environment setup

- Python 3.10+, dependencies in `requirements.txt`
- Install into `.venv` at project root: `python -m venv .venv`, then activate and `pip install -r requirements.txt`
- Secrets go in `.env` (never commit this file)
- Generated datasets go in `data/` (never commit)

## Code structure

- One entry command documented in README
- Implementation in a package (`src/`), not scripts at the root
- Names describe meaning: `created_at`, not `value_0` or `response_field_3`
- One module owns one job; don't split until a second caller needs it
- Delete unreachable code in the same change
- User-facing text in Spanish (repo language); identifiers follow the code already in place

## Performance & parallelism

- Prove one call works before parallelizing
- Default worker count and expose it as a `--workers` flag
- Each worker gets its own HTTP session
- Parallelize only after one page/batch of a slice returns records
- Count failures instead of aborting; print failures at the end

## Dependencies

- Use standard library and packages already in `requirements.txt` first
- External I/O through one small module (don't import requests/httpx in every file)
- Prove a new library with one real call before integrating
- To try an alternative: add it behind the same module, select explicitly, keep the working path
- Don't upgrade a pinned package as a side effect—if tested version is different, restore the pin unless the project now requires it

## Commits & files

- Don't commit `.venv`, `.env`, `data/`, caches, or generated datasets
- `.env` holds secrets and stays out of git
- Update docs (README, flags, output format) in the same change when command or output changes

## Skills

This repo includes a web-scraping skill (see `.claude/skills/web-scraping/SKILL.md`). Use it when asked to scrape, crawl, or download listings from a website.

---

Espejo de `.cursor/rules/writing-code.mdc` — edited for Claude Code on 2026-10-22.
