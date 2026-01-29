# Kimi Book Writer Makefile
# Use 'make help' to see available targets

.PHONY: help install test web cli cli-images cli-resume clean

# Default target
help:
	@echo "Kimi Book Writer - Available targets:"
	@echo ""
	@echo "  make install      Install dependencies with uv"
	@echo "  make test         Run all tests"
	@echo "  make web          Launch the Streamlit web UI"
	@echo ""
	@echo "  CLI targets:"
	@echo "  make cli          Run CLI interactively"
	@echo "  make cli-images   Run CLI with image generation enabled"
	@echo "  make cli-resume   Resume from saved state"
	@echo ""
	@echo "  make clean        Remove generated files (novel_state.json, novel.md)"
	@echo ""
	@echo "  CLI with options:"
	@echo "    make cli PROMPT='your concept' TITLE='Novel Title' CHAPTERS=5"
	@echo "    make cli-images PROMPT='your concept' TITLE='Novel Title' CHAPTERS=2"

# Installation
install:
	uv sync

# Testing
test:
	uv run pytest

test-verbose:
	uv run pytest -v

# Web UI
web:
	uv run streamlit run app.py

# CLI targets
PROMPT ?=
TITLE ?=
CHAPTERS ?=
OUT ?= novel.md
FLUX_MODEL ?=

# Build CLI args dynamically
CLI_ARGS :=
ifdef PROMPT
CLI_ARGS += --prompt "$(PROMPT)"
endif
ifdef TITLE
CLI_ARGS += --title "$(TITLE)"
endif
ifdef CHAPTERS
CLI_ARGS += --chapters $(CHAPTERS)
endif
ifdef OUT
CLI_ARGS += --out "$(OUT)"
endif

cli:
	uv run python kimi_writer.py --no-images $(CLI_ARGS)

cli-images:
ifdef FLUX_MODEL
	uv run python kimi_writer.py --images --flux-model "$(FLUX_MODEL)" $(CLI_ARGS)
else
	uv run python kimi_writer.py --images $(CLI_ARGS)
endif

cli-resume:
	uv run python kimi_writer.py --resume --no-images $(CLI_ARGS)

cli-resume-images:
	uv run python kimi_writer.py --resume --images $(CLI_ARGS)

# Cleanup
clean:
	rm -f novel_state.json novel.md
	rm -rf images/

clean-all: clean
	rm -rf preview/*
	@echo "Note: published/ directory preserved"
