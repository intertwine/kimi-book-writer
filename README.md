# Kimi K2 Novelist

Generate novel-length Markdown books using **Moonshot AI's Kimi K2 reasoning models** (256k context, multi-step reasoning).  
This project uses the OpenAI SDK (v1) in **Moonshot-compatible** mode and is set up to run with **uv**.

**API essentials straight from the docs on this page:**

- Base URL: `https://api.moonshot.ai/v1`
- Install OpenAI SDK `>=1.x`
- Recommended K2 models: `kimi-k2-thinking`, `kimi-k2-thinking-turbo` (long-thinking, 256k; turbo is faster).
- K2 is text-only; use _Kimi Latest_ for images.

---

## Quickstart

### 1) Prereqs

- Python 3.10+
- [uv](https://github.com/astral-sh/uv) installed (`pipx install uv` or `brew install uv`)

### 2) Install & configure

```bash
uv sync
cp .env.example .env
# Paste your Moonshot key:
# MOONSHOT_API_KEY=sk-...
```

Optional `.env` overrides:

```env
KIMI_MODEL=kimi-k2-thinking-turbo
KIMI_TEMPERATURE=0.6
KIMI_MAX_OUTPUT_TOKENS=4096
```

### 3) Generate a book

Interactive:

```bash
uv run kimi_writer.py
```

Non-interactive:

```bash
uv run kimi_writer.py --prompt "A near-future techno-thriller about..." --title "Ghosts in the Wire" --out book.md
```

Useful flags:

- `--resume` Continue from `novel_state.json`
- `--chapters N` Limit number of chapters (smoke test)

Artifacts:

- `book.md` - full Markdown (title, outline, chapters)
- `novel_state.json` - checkpoint/resume state

### How it works

1. **Outline phase.** Asks K2 to create a 20-40 chapter outline as a numbered Markdown list.
2. **Chapter phase.** Iterates over chapter titles, requesting ~1.5-2.5k-word chapters.  
   A short rolling context (last few chapter snippets) is sent to preserve continuity without exhausting context.
3. **Streaming + retries.** Output streams to console (dots), with exponential backoff for robustness.

### Why K2 _thinking/turbo_?

From the quickstart:

- **256K context** for long projects.
- **Multi-step reasoning/tool use** for complex tasks.
- Turbo variants can reach **60-100 tok/s**.

### Notes

- This script is intentionally small and easy to modify. Tweak prompts inside `kimi_writer.py` to shape genre/voice/length.
- If you need JSON mode guardrails or chapter-per-file output, we can add that quickly.

## License

MIT
