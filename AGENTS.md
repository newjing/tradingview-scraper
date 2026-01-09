# AGENTS.md instructions for /Users/jingliu/NAS_Web/tradingview-scraper

<INSTRUCTIONS>
## Skills
These skills are discovered at startup from multiple local sources. Each entry includes a name, description, and file path so you can open the source for full instructions.
- skill-creator: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowledge, workflows, or tool integrations. (file: /Users/jingliu/.codex/skills/.system/skill-creator/SKILL.md)
- skill-installer: Install Codex skills into $CODEX_HOME/skills from a curated list or a GitHub repo path. Use when a user asks to list installable skills, install a curated skill, or install a skill from another repo (including private repos). (file: /Users/jingliu/.codex/skills/.system/skill-installer/SKILL.md)
- Discovery: Available skills are listed in project docs and may also appear in a runtime "## Skills" section (name + description + file path). These are the sources of truth; skill bodies live on disk at the listed paths.
- Trigger rules: If the user names a skill (with `$SkillName` or plain text) OR the task clearly matches a skill's description, you must use that skill for that turn. Multiple mentions mean use them all. Do not carry skills across turns unless re-mentioned.
- Missing/blocked: If a named skill isn't in the list or the path can't be read, say so briefly and continue with the best fallback.
- How to use a skill (progressive disclosure):
  1) After deciding to use a skill, open its `SKILL.md`. Read only enough to follow the workflow.
  2) If `SKILL.md` points to extra folders such as `references/`, load only the specific files needed for the request; don't bulk-load everything.
  3) If `scripts/` exist, prefer running or patching them instead of retyping large code blocks.
  4) If `assets/` or templates exist, reuse them instead of recreating from scratch.
- Description as trigger: The YAML `description` in `SKILL.md` is the primary trigger signal; rely on it to decide applicability. If unsure, ask a brief clarification before proceeding.
- Coordination and sequencing:
  - If multiple skills apply, choose the minimal set that covers the request and state the order you'll use them.
  - Announce which skill(s) you're using and why (one short line). If you skip an obvious skill, say why.
- Context hygiene:
  - Keep context small: summarize long sections instead of pasting them; only load extra files when needed.
  - Avoid deeply nested references; prefer one-hop files explicitly linked from `SKILL.md`.
  - When variants exist (frameworks, providers, domains), pick only the relevant reference file(s) and note that choice.
- Safety and fallback: If a skill can't be applied cleanly (missing files, unclear instructions), state the issue, pick the next-best approach, and continue.
</INSTRUCTIONS>

# Project Notes for Codex

## Overview
TradingView Scraper is a Python library that scrapes TradingView data (ideas, indicators, news, calendar)
and supports WebSocket-based real-time streaming.

## Development Commands
```bash
# Install dependencies
pip install -r requirements.txt

# Install package in dev mode
pip install -e .
```

## Testing
```bash
# Run all tests
pytest

# Run a specific test file
pytest tests/test_ideas.py
pytest tests/test_indicators.py
pytest tests/test_realtime_price.py

# Verbose output
pytest -v
```

## Code Quality
```bash
# flake8 (CI)
flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

# pylint (CI)
pylint $(git ls-files '*.py')
```

## Docs
```bash
cd docs
make html
```

## Architecture Notes
- `tradingview_scraper/symbols/`: HTTP scraping modules (`ideas.py`, `technicals.py`, `news.py`, `cal.py`)
- `tradingview_scraper/symbols/stream/`: WebSocket streaming (`streamer.py`, `price.py`, `stream_handler.py`)
- `tradingview_scraper/data/`: static config files (indicators, exchanges, timeframes, languages)

## Core Patterns
- Export pattern: classes accept `export_result` and `export_type`; `_export()` saves JSON/CSV.
- Validation: exchange/indicator names validated against data files before requests.
- WebSocket: custom `~m~{length}~m~{message}` framing with heartbeat echo; packet types `du`, `qsd`, `timescale_update`.

## Testing Strategy
- Use pytest; mock HTTP calls with `mock.patch('tradingview_scraper.symbols.ideas.requests.get')`.
- Include success cases and edge cases (invalid symbols, empty results, captcha challenges).

## Version and Dependencies
- Python 3.8+; current version 0.4.19 in `setup.py`.
- Key deps: `requests==2.32.4`, `pandas>=2.0.3`, `beautifulsoup4>=4.12.3`,
  `pydantic>=2.8.2`, `websockets>=13.1`, `websocket-client>=1.8.0`.

## CI
- GitHub Actions: `python-app.yml` (flake8 + pytest), `pylint.yml`, `release.yml`, `docs.yml`.

## Git Commit Guidelines
- No AI attribution lines.
- Use conventional commits: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`.
