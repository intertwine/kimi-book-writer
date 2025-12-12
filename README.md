# Kimi K2 Novelist

Generate novel-length Markdown books using **Moonshot AI's Kimi K2 reasoning models** (256k context, multi-step reasoning).

✨ **New**: Web UI for generating, managing, and reading novels!
🚀 **One-click launch** in GitHub Codespaces!

**Two ways to use:**

- 🖥️ **Web UI** - Streamlit-based interface for easy novel generation and management
- 💻 **CLI** - Command-line interface for automated workflows

**API essentials straight from the docs on this page:**

- Base URL: `https://api.moonshot.ai/v1`
- Install OpenAI SDK `>=1.x`
- Recommended K2 models: `kimi-k2-thinking`, `kimi-k2-thinking-turbo` (long-thinking, 256k; turbo is faster).
- K2 is text-only; use _Kimi Latest_ for images.

---

## Quickstart

### Option A: Web UI (Codespaces - Recommended!)

The easiest way to get started is using GitHub Codespaces:

1. **Fork this repository first** (click the **Fork** button at the top right)
2. In your fork, click the **Code** button → **Codespaces** → **Create codespace on `main`**
3. Wait for the environment to set up (automatic)
4. Create a `.env` file with your Moonshot API key:

   ```bash
   cp .env.example .env
   # Edit .env and add: MOONSHOT_API_KEY=sk-...
   ```

5. Start the web UI:

   ```bash
   # Option 1: Direct launch
   streamlit run app.py

   # Option 2: Using helper script (auto-installs dependencies)
   bash run-ui.sh
   ```

6. Click the notification to open the UI (or go to the Ports tab and open port 8501)

> **Why fork first?** Forking gives you your own copy of the repository where you can save your generated novels. The "Publish" feature commits novels to your fork, preserving your work.

**Web UI Features:**

- 📝 **Generate** - Create new novels with a user-friendly form
- 📚 **Library** - Manage preview and published novels
- 📖 **Reader** - Read novels with chapter navigation
- ✅ **Publish** - Move novels from preview to published (auto-commits to repo)
- ⬇️ **Download** - Export novels as Markdown files

**Directory Structure:**

- `preview/` - Novels being worked on (gitignored)
- `published/` - Finalized novels (committed to repo)

### Option B: Local CLI

If you prefer the command-line interface:

#### 1) Prereqs

- Python 3.10+
- [pip](https://pip.pypa.io/) or [uv](https://github.com/astral-sh/uv) (recommended)

#### 2) Install & configure

```bash
# Using pip
pip install -e .

# Or using uv (recommended)
uv sync

# Configure
cp .env.example .env
# Edit .env and paste your Moonshot key:
# MOONSHOT_API_KEY=sk-...
```

Optional `.env` overrides:

```env
KIMI_MODEL=kimi-k2-thinking-turbo
KIMI_TEMPERATURE=0.6
KIMI_MAX_OUTPUT_TOKENS=4096
```

#### 3) Generate a book

Interactive:

```bash
python kimi_writer.py
# Or with uv: uv run kimi_writer.py
```

Non-interactive:

```bash
python kimi_writer.py --prompt "A near-future techno-thriller about..." --title "Ghosts in the Wire" --out book.md
```

Useful flags:

- `--resume` Continue from `novel_state.json`
- `--chapters N` Limit number of chapters to write:
  - **Without `--resume`**: Write up to N chapters total (e.g., `--chapters 3` writes chapters 1-3)
  - **With `--resume`**: Write N *more* chapters from current progress (e.g., if 5 chapters exist, `--resume --chapters 3` writes chapters 6-8)

Artifacts:

- `book.md` - full Markdown (title, outline, chapters)
- `novel_state.json` - checkpoint/resume state

---

## How it works

### Novel Generation Process

1. **Outline phase.** Asks K2 to create a 20-40 chapter outline as a numbered Markdown list.
2. **Chapter phase.** Iterates over chapter titles, requesting ~1.5-2.5k-word chapters.
   A short rolling context (last few chapter snippets) is sent to preserve continuity without exhausting context.
3. **Streaming + retries.** Output streams to console (dots), with exponential backoff for robustness.

### Web UI Workflow

1. **Generate Tab**

   - Enter novel concept, title, and settings
   - Watch real-time generation progress
   - Novels saved to `preview/` directory (gitignored)
   - Resume incomplete novels anytime

2. **Library Tab**

   - Browse preview and published novels
   - Read novels with chapter navigation
   - Download as Markdown files
   - Publish to move from preview → published (commits to repo)
   - Delete unwanted novels

3. **Reader Mode**
   - Clean reading interface
   - Chapter-by-chapter navigation
   - Full markdown rendering

### Why K2 _thinking/turbo_?

From the quickstart:

- **256K context** for long projects.
- **Multi-step reasoning/tool use** for complex tasks.
- Turbo variants can reach **60-100 tok/s**.

## Project Structure

```
kimi-book-writer/
├── app.py                 # Streamlit web UI
├── kimi_writer.py         # CLI novel generator
├── utils.py               # Helper utilities
├── preview/               # Draft novels (gitignored)
├── published/             # Published novels (committed)
├── examples/              # Example generated novels
├── .devcontainer/         # Codespaces configuration
├── .env.example           # Environment template
└── pyproject.toml         # Dependencies
```

## Notes

- Both the CLI and Web UI share the same core generation logic
- Prompts in `kimi_writer.py` can be customized for different genres/styles
- The Web UI provides better progress tracking and novel management
- CLI is useful for automation and scripting workflows

## License

MIT
