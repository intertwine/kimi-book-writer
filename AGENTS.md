# Repository Guidelines

## Project Structure & Module Organization

- `app.py` hosts the Streamlit web UI.
- `kimi_writer.py` implements the CLI and core generation flow.
- `utils.py` provides shared helpers used by both entry points.
- `preview/` holds draft novels (gitignored); `published/` holds finalized novels (committed).
- `examples/` contains sample outputs; `tests/` contains pytest tests.
- `.env.example` is the config template; `pyproject.toml` defines dependencies.

## Build, Test, and Development Commands

- `uv sync` installs dependencies (preferred); `pip install -e .` is the fallback.
- `streamlit run app.py` runs the web UI; `bash run-ui.sh` bootstraps `.env` and uses `uv` if available.
- `python kimi_writer.py` runs the interactive CLI.
- `python kimi_writer.py --prompt "..." --title "..." --out book.md` runs the CLI non-interactively.
- `pytest` runs the test suite; `uv run pytest` if you are using uv.

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

- Copy `.env.example` to `.env` and set `MOONSHOT_API_KEY`.
- Do not commit `.env` or API keys; drafts belong in `preview/`, finalized novels in `published/`.
