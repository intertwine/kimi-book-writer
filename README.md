# Kimi K2.5 Novelist

Generate novel-length Markdown books using **Moonshot AI's Kimi K2.5 reasoning models** (262k context, 1T parameters).

✨ **New**: FLUX.2 image generation for cover and chapter illustrations!
🚀 **One-click launch** in GitHub Codespaces!

**Two ways to use:**

- 🖥️ **Web UI** - Streamlit-based interface for easy novel generation and management
- 💻 **CLI** - Command-line interface for automated workflows

**Features:**

- 📖 **Novel generation** with Kimi K2.5 (262k context, multi-step reasoning)
- 🎨 **Optional illustrations** via FLUX.2 models on OpenRouter (cover + chapter images)
- ⚡ **Async image generation** - images generate concurrently with text, not blocking
- ⏸️ **Pause/Resume** - stop anytime and continue later
- 📊 **Live progress** - real-time updates during generation

**API essentials:**

- Base URL: `https://api.moonshot.ai/v1`
- Install OpenAI SDK `>=1.x`
- Recommended model: `kimi-k2.5` (262k context, 1T parameters)
- Image generation: FLUX.2 via OpenRouter (optional)

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
- 🎨 **Illustrations** - Optional FLUX.2 cover and chapter images (async generation)
- ⏸️ **Pause/Resume** - Stop generation anytime and continue later
- 📊 **Live Progress** - Real-time sidebar progress panel with chapter-by-chapter updates
- 🔄 **Background Generation** - Non-blocking UI; generation runs in background thread
- 📚 **Library** - Manage preview and published novels
- 📖 **Reader** - Read novels with chapter navigation and images
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
# Text generation (Moonshot)
KIMI_MODEL=kimi-k2.5
KIMI_TEMPERATURE=1.0
KIMI_TOP_P=0.95
KIMI_MAX_OUTPUT_TOKENS=8192

# Image generation (OpenRouter) - optional
OPENROUTER_API_KEY=sk-or-v1-...
FLUX_MODEL=black-forest-labs/flux.2-klein-4b  # or flux.2-max for higher quality
IMAGE_GENERATION_TIMEOUT=180  # seconds, increase for slower models
```

#### 3) Generate a book

**Using Make targets (recommended):**

```bash
make help          # See all available commands
make web           # Launch Streamlit web UI
make novel         # Interactive CLI (text only)
make novel-images  # Interactive CLI with illustrations
make resume        # Continue from saved state
make clean         # Remove CLI artifacts
```

**Direct CLI usage:**

```bash
python kimi_writer.py                                    # Interactive
python kimi_writer.py --prompt "..." --title "..." --out book.md  # Non-interactive
python kimi_writer.py --images                           # Enable image generation
python kimi_writer.py --no-images                        # Disable images (faster)
python kimi_writer.py --flux-model black-forest-labs/flux.2-max  # Use specific FLUX model
```

**CLI flags:**

- `--resume` Continue from `novel_state.json`
- `--chapters N` Limit chapters:
  - **Without `--resume`**: Write up to N chapters total
  - **With `--resume`**: Write N _more_ chapters from current progress
- `--images` Enable FLUX.2 image generation (requires `OPENROUTER_API_KEY`)
- `--no-images` Disable image generation
- `--flux-model MODEL` Specify FLUX model (`flux.2-klein-4b` or `flux.2-max`)

**Artifacts:**

- `novel.md` - full Markdown output (title, outline, chapters, images) — customizable via `--out`
- `novel_state.json` - checkpoint/resume state for the CLI
- `<slug>_images/` - generated cover and chapter images (if enabled)

---

## How it works

### Novel Generation Process

1. **Outline phase.** Asks K2.5 to create a 20-40 chapter outline as a numbered Markdown list.
2. **Cover image** (if enabled). Submits cover image generation to async queue.
3. **Chapter phase.** Iterates over chapter titles, requesting ~1.5-2.5k-word chapters.
   A short rolling context (last few chapter snippets) is sent to preserve continuity without exhausting context.
4. **Chapter images** (if enabled). Each chapter image is submitted to async queue after text completes.
5. **Image completion.** At end, waits for all pending images to finish.
6. **Streaming + retries.** Output streams to console (dots), with exponential backoff for robustness.

**Async Image Generation:** Images generate concurrently with text (up to 2 simultaneous image requests). This means chapter writing isn't blocked waiting for images, significantly reducing total generation time when images are enabled.

### Web UI Workflow

1. **Generate Tab**

   - Enter novel concept, title, and settings
   - Generation runs in background thread (UI stays responsive)
   - Live progress panel in sidebar shows current chapter
   - Pause anytime with the pause button; resume from Library
   - Novels auto-saved to `preview/` directory after each chapter

2. **Library Tab**

   - Browse preview and published novels
   - Continue incomplete novels with one click
   - Read novels with chapter navigation
   - Download as Markdown files
   - Publish complete novels (moves to `published/`, commits to repo)
   - Delete unwanted novels

3. **Reader Mode**
   - Clean reading interface
   - Chapter-by-chapter navigation with dropdown selector
   - Previous/Next chapter buttons
   - Full markdown rendering

### Why Kimi K2.5?

- **262K context** for long novel projects
- **1T parameters** with multi-step reasoning
- **Optimized temperature=1.0** for creative writing
- High throughput for chapter generation

## Project Structure

```
kimi-book-writer/
├── app.py                 # Streamlit web UI (background thread generation)
├── kimi_writer.py         # CLI novel generator
├── utils.py               # Shared utilities (outline parsing, validation)
├── image_gen.py           # FLUX.2 image generation via OpenRouter
├── async_image_gen.py     # Async image queue with ThreadPoolExecutor
├── Makefile               # Make targets for common operations
├── run-ui.sh              # Helper script to launch web UI
├── tests/                 # pytest test suite
│   ├── conftest.py        # Test fixtures
│   ├── test_kimi_writer.py
│   ├── test_image_gen.py
│   └── test_utils.py
├── preview/               # Draft novels (gitignored)
│   └── <slug>_images/     # Generated images per novel
├── published/             # Published novels (committed)
├── examples/              # Example generated novels
├── .devcontainer/         # Codespaces configuration
├── .env.example           # Environment template
├── pyproject.toml         # Dependencies (Python 3.10+, Streamlit 1.37+)
├── AGENTS.md              # Repository guidelines for AI assistants
└── CLAUDE.md              # Project-specific instructions
```

## Notes

- Both the CLI and Web UI share the same core generation logic and prompts
- Prompts in `kimi_writer.py` can be customized for different genres/styles
- The Web UI runs generation in a background thread, so the UI remains responsive
- Progress is saved after each chapter, enabling safe pause/resume
- Requires **Streamlit 1.37.0+** for the `@st.fragment(run_every=...)` auto-refresh feature
- Supports **Kimi K2.5** which returns content via `delta.thinking` and `delta.content` streaming
- Image generation is **async** - images generate concurrently with text (2 workers)
- Images are optional; generation works without `OPENROUTER_API_KEY`
- CLI is useful for automation, scripting, and headless server workflows

## Testing

Run the test suite with:

```bash
uv run pytest        # Using uv (recommended)
pytest               # Using pip-installed pytest
```

Tests are deterministic and do not make live API calls.

## License

MIT
