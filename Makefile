# Kimi Book Writer Makefile
# Use 'make help' to see available targets

.PHONY: help install test test-verbose web novel novel-images resume clean clean-preview

# Colors for pretty output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
BOLD := \033[1m
RESET := \033[0m

# Default target
help:
	@echo ""
	@printf "$(BOLD)$(CYAN)Kimi Book Writer$(RESET) - AI Novel Generation\n"
	@echo ""
	@printf "$(BOLD)Setup & Testing:$(RESET)\n"
	@printf "  $(GREEN)make install$(RESET)        Install dependencies with uv\n"
	@printf "  $(GREEN)make test$(RESET)           Run all tests\n"
	@echo ""
	@printf "$(BOLD)Run the App:$(RESET)\n"
	@printf "  $(GREEN)make web$(RESET)            Launch the Streamlit web UI\n"
	@printf "  $(GREEN)make novel$(RESET)          Generate a novel (interactive, text only)\n"
	@printf "  $(GREEN)make novel-images$(RESET)   Generate a novel with illustrations\n"
	@printf "  $(GREEN)make resume$(RESET)         Continue from last saved state\n"
	@echo ""
	@printf "$(BOLD)Cleanup:$(RESET)\n"
	@printf "  $(GREEN)make clean$(RESET)          Remove CLI artifacts (with confirmation)\n"
	@printf "  $(GREEN)make clean-preview$(RESET)  Remove all preview novels (with confirmation)\n"
	@echo ""

# Installation
install:
	@printf "$(CYAN)Installing dependencies...$(RESET)\n"
	@uv sync
	@printf "$(GREEN)✓ Dependencies installed$(RESET)\n"
	@echo ""
	@printf "$(YELLOW)Next steps:$(RESET)\n"
	@printf "  1. Copy .env.example to .env and add your MOONSHOT_API_KEY\n"
	@printf "  2. (Optional) Add OPENROUTER_API_KEY for image generation\n"
	@printf "  3. Run 'make web' for the web UI or 'make novel' for CLI\n"

# Testing
test:
	@printf "$(CYAN)Running tests...$(RESET)\n"
	@uv run pytest
	@printf "$(GREEN)✓ All tests passed$(RESET)\n"

test-verbose:
	@uv run pytest -v

# Web UI
web:
	@printf "$(CYAN)Launching Streamlit web UI...$(RESET)\n"
	@printf "$(YELLOW)Press Ctrl+C to stop$(RESET)\n"
	@echo ""
	@uv run streamlit run app.py

# Interactive novel generation
novel:
	@printf "$(BOLD)$(CYAN)Generate a New Novel$(RESET)\n"
	@printf "$(YELLOW)─────────────────────$(RESET)\n"
	@echo ""
	@read -p "Novel title [My Novel]: " title; \
	title=$${title:-My Novel}; \
	echo ""; \
	printf "Enter your novel concept (theme, characters, setting, etc.):\n"; \
	read -p "> " concept; \
	if [ -z "$$concept" ]; then \
		printf "$(RED)Error: Concept is required$(RESET)\n"; \
		exit 1; \
	fi; \
	echo ""; \
	read -p "Max chapters [30]: " chapters; \
	chapters=$${chapters:-30}; \
	read -p "Output file [novel.md]: " output; \
	output=$${output:-novel.md}; \
	echo ""; \
	printf "$(CYAN)Starting generation...$(RESET)\n"; \
	printf "  Title: $$title\n"; \
	printf "  Chapters: $$chapters\n"; \
	printf "  Output: $$output\n"; \
	echo ""; \
	uv run python kimi_writer.py --title "$$title" --prompt "$$concept" --chapters "$$chapters" --out "$$output" --no-images

novel-images:
	@printf "$(BOLD)$(CYAN)Generate a Novel with Illustrations$(RESET)\n"
	@printf "$(YELLOW)────────────────────────────────────$(RESET)\n"
	@echo ""
	@if [ -z "$$OPENROUTER_API_KEY" ] && ! grep -q "OPENROUTER_API_KEY" .env 2>/dev/null; then \
		printf "$(YELLOW)Warning: OPENROUTER_API_KEY not found in environment or .env$(RESET)\n"; \
		printf "Image generation requires an OpenRouter API key.\n"; \
		read -p "Continue anyway? [y/N]: " cont; \
		if [ "$$cont" != "y" ] && [ "$$cont" != "Y" ]; then \
			exit 0; \
		fi; \
		echo ""; \
	fi; \
	read -p "Novel title [My Novel]: " title; \
	title=$${title:-My Novel}; \
	echo ""; \
	printf "Enter your novel concept (theme, characters, setting, etc.):\n"; \
	read -p "> " concept; \
	if [ -z "$$concept" ]; then \
		printf "$(RED)Error: Concept is required$(RESET)\n"; \
		exit 1; \
	fi; \
	echo ""; \
	read -p "Max chapters [30]: " chapters; \
	chapters=$${chapters:-30}; \
	read -p "Output file [novel.md]: " output; \
	output=$${output:-novel.md}; \
	echo ""; \
	printf "Image model options:\n"; \
	printf "  1. flux.2-klein-4b (fast, cheaper) [default]\n"; \
	printf "  2. flux.2-max (highest quality)\n"; \
	read -p "Select model [1]: " model_choice; \
	if [ "$$model_choice" = "2" ]; then \
		flux_model="black-forest-labs/flux.2-max"; \
	else \
		flux_model="black-forest-labs/flux.2-klein-4b"; \
	fi; \
	echo ""; \
	printf "$(CYAN)Starting generation with images...$(RESET)\n"; \
	printf "  Title: $$title\n"; \
	printf "  Chapters: $$chapters\n"; \
	printf "  Output: $$output\n"; \
	printf "  Image model: $$flux_model\n"; \
	echo ""; \
	uv run python kimi_writer.py --title "$$title" --prompt "$$concept" --chapters "$$chapters" --out "$$output" --images --flux-model "$$flux_model"

resume:
	@if [ ! -f novel_state.json ]; then \
		printf "$(RED)No saved state found (novel_state.json)$(RESET)\n"; \
		printf "Start a new novel with 'make novel' or 'make novel-images'\n"; \
		exit 1; \
	fi; \
	printf "$(BOLD)$(CYAN)Resume Novel Generation$(RESET)\n"; \
	printf "$(YELLOW)───────────────────────$(RESET)\n"; \
	echo ""; \
	title=$$(python -c "import json; print(json.load(open('novel_state.json')).get('title', 'Unknown'))"); \
	current=$$(python -c "import json; print(json.load(open('novel_state.json')).get('current_idx', 0))"); \
	total=$$(python -c "import json; print(len(json.load(open('novel_state.json')).get('outline_items', [])))"); \
	images=$$(python -c "import json; print(json.load(open('novel_state.json')).get('images_enabled', False))"); \
	printf "  Title: $$title\n"; \
	printf "  Progress: $$current/$$total chapters\n"; \
	printf "  Images: $$images\n"; \
	echo ""; \
	read -p "Continue generation? [Y/n]: " cont; \
	if [ "$$cont" = "n" ] || [ "$$cont" = "N" ]; then \
		exit 0; \
	fi; \
	echo ""; \
	if [ "$$images" = "True" ]; then \
		uv run python kimi_writer.py --resume --images; \
	else \
		uv run python kimi_writer.py --resume --no-images; \
	fi

# Cleanup with confirmation
clean:
	@printf "$(BOLD)$(CYAN)Clean CLI Artifacts$(RESET)\n"
	@printf "$(YELLOW)───────────────────$(RESET)\n"
	@echo ""
	@printf "This will remove CLI-generated files in the current directory.\n"
	@echo ""
	@found=0; \
	if [ -f novel_state.json ]; then \
		printf "  $(RED)•$(RESET) novel_state.json (saved generation state)\n"; \
		found=1; \
	fi; \
	if [ -f novel.md ]; then \
		printf "  $(RED)•$(RESET) novel.md (generated novel)\n"; \
		found=1; \
	fi; \
	if [ -d images ]; then \
		count=$$(find images -type f 2>/dev/null | wc -l | tr -d ' '); \
		printf "  $(RED)•$(RESET) images/ directory ($$count files)\n"; \
		found=1; \
	fi; \
	if [ $$found -eq 0 ]; then \
		printf "$(GREEN)✓ Nothing to clean$(RESET)\n"; \
		exit 0; \
	fi; \
	echo ""; \
	read -p "Delete these files? [y/N]: " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		rm -f novel_state.json novel.md; \
		rm -rf images/; \
		echo ""; \
		printf "$(GREEN)✓ Cleaned$(RESET)\n"; \
	else \
		echo ""; \
		printf "$(YELLOW)Cancelled$(RESET)\n"; \
	fi

clean-preview:
	@printf "$(BOLD)$(CYAN)Clean Preview Directory$(RESET)\n"
	@printf "$(YELLOW)───────────────────────$(RESET)\n"
	@echo ""
	@printf "This will remove all draft novels in preview/\n"
	@printf "$(YELLOW)Note: Published novels in published/ will NOT be affected.$(RESET)\n"
	@echo ""
	@if [ ! -d preview ] || [ -z "$$(ls -A preview 2>/dev/null)" ]; then \
		printf "$(GREEN)✓ Preview directory is empty$(RESET)\n"; \
		exit 0; \
	fi; \
	printf "Files to be deleted:\n"; \
	echo ""; \
	for f in preview/*; do \
		if [ -f "$$f" ]; then \
			size=$$(ls -lh "$$f" | awk '{print $$5}'); \
			printf "  $(RED)•$(RESET) $$f ($$size)\n"; \
		elif [ -d "$$f" ]; then \
			count=$$(find "$$f" -type f | wc -l | tr -d ' '); \
			printf "  $(RED)•$(RESET) $$f/ ($$count files)\n"; \
		fi; \
	done; \
	echo ""; \
	read -p "Delete all preview files? [y/N]: " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		rm -rf preview/*; \
		echo ""; \
		printf "$(GREEN)✓ Preview directory cleaned$(RESET)\n"; \
	else \
		echo ""; \
		printf "$(YELLOW)Cancelled$(RESET)\n"; \
	fi
