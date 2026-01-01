# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kimi K2 Novelist generates novel-length Markdown books using Moonshot AI's Kimi K2 reasoning models (256k context). The project provides both a CLI and Streamlit web UI for novel generation.

## Commands

```bash
# Install dependencies
uv sync                          # preferred
pip install -e .                 # fallback

# Run the web UI
streamlit run app.py
bash run-ui.sh                   # bootstraps .env, uses uv if available

# Run the CLI
python kimi_writer.py                                           # interactive
python kimi_writer.py --prompt "..." --title "..." --out book.md  # non-interactive
python kimi_writer.py --resume                                  # continue from novel_state.json
python kimi_writer.py --chapters N                              # limit chapters

# Testing
uv run pytest                    # run all tests
uv run pytest tests/test_utils.py  # run single test file
uv run pytest -k test_name       # run specific test
```

## Architecture

**Entry Points:**
- `app.py` - Streamlit web UI with tabs for Generate, Library, and Reader
- `kimi_writer.py` - CLI with argparse, handles outline generation and chapter writing

**Shared Code:**
- `utils.py` - `extract_outline_items()` parses LLM-generated outlines into chapter lists
- Both entry points use the same prompts (`SYSTEM_PRIMER`, `OUTLINE_PROMPT`, `CHAPTER_PROMPT`) and generation logic

**State Management:**
- Novel state stored as JSON with: title, concept, model params, outline_text, outline_items (parsed chapters), chapters (written content), current_idx
- CLI saves to `novel_state.json` for resume support
- Web UI saves to `preview/<slug>_state.json` per novel

**Generation Flow:**
1. Outline phase: Send concept to LLM, parse response into chapter titles via `extract_outline_items()`
2. Chapter phase: Iterate outline items, include rolling context (last 3 chapters, 2000 chars each) for continuity
3. Streaming with exponential backoff retries via tenacity

**Directories:**
- `preview/` - Draft novels (gitignored)
- `published/` - Finalized novels (committed, web UI auto-commits on publish)
- `examples/` - Sample outputs

## API Configuration

Uses OpenAI SDK with Moonshot base URL (`https://api.moonshot.ai/v1`).

Environment variables (set in `.env`):
- `MOONSHOT_API_KEY` - Required
- `KIMI_MODEL` - Default: `kimi-k2-thinking-turbo`
- `KIMI_TEMPERATURE` - Default: `0.6`
- `KIMI_MAX_OUTPUT_TOKENS` - Default: `4096`

## Code Style

- Python 3.10+, PEP 8, type hints where they already appear
- `snake_case` for modules/functions, `UPPER_CASE` for constants, `--kebab-case` for CLI flags
- No formatter configured; avoid reformat-only diffs

## Testing

- pytest with fixtures in `tests/conftest.py`
- Tests must be deterministic; avoid live API calls
- Name tests with `test_` prefix
