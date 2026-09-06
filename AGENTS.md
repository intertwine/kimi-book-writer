# Repository Guidelines

## Project Structure & Module Organization

- `app.py` hosts the Streamlit web UI.
- `kimi_writer.py` implements the CLI and core generation flow.
- Chapter prompts carry rolling context (last 3 chapters, 2000 chars each); changing that changes continuity behavior.
- `utils.py` provides shared helpers used by both entry points (outline parsing, path validation).
- `image_gen.py` provides FLUX.2 image generation via OpenRouter API.
- `async_image_gen.py` provides `ImageGenerationQueue` for concurrent image generation.
- `preview/` holds draft novels (gitignored); `published/` holds finalized novels (committed).
- Publishing from the web UI auto-commits to `published/`; do not run it just to test.
- `examples/` contains sample outputs; `tests/` contains pytest tests.
- `.env.example` is the config template; `pyproject.toml` defines dependencies.
- `Makefile` provides convenient targets for common operations.

## Build, Test, and Development Commands

**Make targets (recommended):**
- `make help` shows all available commands.
- `make install` installs dependencies with uv.
- `make web` launches the Streamlit web UI.
- `make novel` runs interactive CLI (text only).
- `make novel-images` runs interactive CLI with illustrations.
- `make resume` continues from saved state.
- `make test` runs the test suite.
- `make clean` removes CLI artifacts.

**Direct commands:**
- `uv sync` installs dependencies (preferred); `pip install -e .` is the fallback.
- `uv run streamlit run app.py` runs the web UI; `bash run-ui.sh` bootstraps `.env` and uses `uv` if available.
- `uv run python kimi_writer.py` runs the interactive CLI.
- `uv run python kimi_writer.py --prompt "..." --title "..." --out book.md --images` runs with images.
- `uv run pytest` runs the test suite.

## Coding Style & Naming Conventions

- Python 3.10+, 4-space indentation, and PEP 8 conventions.
- Use `snake_case` for modules and functions, `UPPER_CASE` for constants, and `--kebab-case` for CLI flags.
- Keep changes consistent with the existing structure in `kimi_writer.py` and `utils.py`; prefer type hints where they already appear.
- No formatter is configured; avoid reformat-only diffs.

## Testing Guidelines

- Framework: pytest (`tests/test_*.py`, `tests/conftest.py`).
- Name new tests with a `test_` prefix and place shared fixtures in `tests/conftest.py`.
- Keep tests deterministic and avoid live Moonshot API calls.

## Commit & Pull Request Guidelines

- Commit messages are short and imperative, often with type prefixes like `feat:` or `Fix:`.
- PRs should include a brief summary, testing notes (e.g., `pytest`), and screenshots for UI changes.
- If you change `published/`, note the specific files updated or added.

## Configuration & Secrets

- Copy `.env.example` to `.env` and set `MOONSHOT_API_KEY` (required for text generation).
- Optionally set `OPENROUTER_API_KEY` to enable FLUX.2 image generation.
- `KIMI_TEMPERATURE=1.0` is the recommended setting for K2.5 thinking mode.
- Do not commit `.env` or API keys; drafts belong in `preview/`, finalized novels in `published/`.
