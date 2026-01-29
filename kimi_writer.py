#!/usr/bin/env python
"""
Kimi K2.5 Novelist
------------------
Generate a novel-length Markdown book using Moonshot AI's Kimi K2.5 reasoning models.

• Uses OpenAI SDK (v1) compatibility with base_url set to Moonshot.
• Streams content and saves a resumable state file.
• Optional image generation via FLUX.2 models on OpenRouter.
• Reads secrets from .env (MOONSHOT_API_KEY, optional model overrides).
• Designed to be run via `uv run kimi_writer.py`.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import List, Dict

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TimeElapsedColumn, BarColumn, TextColumn

from openai import OpenAI

from utils import extract_outline_items
from image_gen import (
    is_image_generation_enabled,
    generate_image,
    generate_cover_prompt,
    generate_chapter_prompt,
    save_image,
)

console = Console()

SYSTEM_PRIMER = """You are Kimi, an AI novelist provided by Moonshot AI. 
You write long-form, novel-length fiction in clear, publishable English (or the user's requested language).
You produce valid Markdown with semantic structure (# for title, ## for chapters, ### for sections).
When writing chapters, include: a short epigraph (optional), vivid scene-setting, character arcs, and continuity.
Avoid explicit sexual content, racism, terrorism, or graphic violence.
The string 'Moonshot AI' must remain in English if mentioned.
"""

OUTLINE_PROMPT = """You will design a compelling, novel-length outline based on the user's concept.

Return a detailed outline with 20–40 chapters (or reasonable for the genre), each a single line:
- A short, punchy chapter title
- A 1–2 sentence summary of the chapter's events or purpose
Return the outline as a numbered Markdown list (e.g., "1. Chapter Title — one sentence...").
If the concept suggests multiple parts/acts, group with Markdown headings.
"""

CHAPTER_PROMPT = """Write Chapter {idx}: "{title}" of this novel.
Follow the established outline and ensure strong continuity from earlier chapters.

Requirements:
- Length: ~1,500–2,500 words (aim for substance; do not pad with filler)
- Markdown only. Start with `## Chapter {idx}: {title}` as the heading.
- Include a concise italic epigraph (optional) below the heading.
- Maintain tone, themes, and details across chapters.
- Conclude the chapter with a natural beat, not a summary of the entire book.

Before you write, think briefly about plot beats. Then write the chapter in full.
"""

RESUME_FILE = "novel_state.json"

def get_client() -> OpenAI:
    load_dotenv()
    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        console.print("[red]Missing MOONSHOT_API_KEY in environment (.env).[/red]")
        sys.exit(1)
    base_url = "https://api.moonshot.ai/v1"
    return OpenAI(api_key=api_key, base_url=base_url)

def env(name: str, default: str) -> str:
    val = os.getenv(name)
    return val if val is not None else default

def create_fresh_state(title: str = None, concept: str = None) -> Dict:
    """Create a new, empty novel state with default values."""
    return {
        "title": title,
        "concept": concept,
        "model": env("KIMI_MODEL", "kimi-k2.5"),
        "temperature": float(env("KIMI_TEMPERATURE", "1.0")),
        "top_p": float(env("KIMI_TOP_P", "0.95")),
        "max_output_tokens": int(env("KIMI_MAX_OUTPUT_TOKENS", "8192")),
        "outline_text": None,
        "chapters": [],
        "outline_items": [],
        "current_idx": 0,
        "images_enabled": False,
        "cover_image_path": None
    }


def load_or_init_state(path: Path) -> Dict:
    if path.exists():
        return json.loads(path.read_text())
    return create_fresh_state()

def save_state(path: Path, state: Dict):
    path.write_text(json.dumps(state, indent=2))

@retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(5))
def chat_complete_stream(client: OpenAI, model: str, messages: List[Dict], temperature: float, max_tokens: int, top_p: float = 0.95):
    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        stream=True
    )

def stream_to_text(stream) -> str:
    chunks = []
    for chunk in stream:
        delta = chunk.choices[0].delta

        # Kimi K2 thinking models may return content in delta.thinking or delta.content
        content = getattr(delta, "content", None)
        thinking = getattr(delta, "thinking", None)

        if content:
            chunks.append(content)
        elif thinking:
            chunks.append(thinking)

        if len(chunks) % 50 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()
    sys.stdout.write("\n")
    return "".join(chunks)

def build_book_markdown(state: Dict, include_images: bool = True) -> str:
    """Build the complete novel markdown with optional image references."""
    title = state["title"] or "Untitled Novel"
    parts = [f"# {title}\n"]

    # Include cover image if available
    if include_images and state.get("cover_image_path"):
        cover_filename = Path(state["cover_image_path"]).name
        parts.append(f"![Cover](images/{cover_filename})\n")

    if state.get("concept"):
        parts.append(f"*Generated from concept:* {state['concept']}\n")
    if state["outline_text"]:
        parts.append("## Outline\n\n" + state["outline_text"].strip() + "\n")

    for i, ch in enumerate(state["chapters"]):
        # Add chapter image before content if available
        if include_images and ch.get("image_path"):
            img_filename = Path(ch["image_path"]).name
            parts.append(f"![Chapter {i+1}](images/{img_filename})\n")
        parts.append(ch["content"].strip() + "\n")

    return "\n".join(parts)

def main():
    parser = argparse.ArgumentParser(description="Generate a novel-length Markdown book with Kimi K2.5.")
    parser.add_argument("--prompt", "-p", help="Concept prompt for the novel (if omitted, you will be asked)")
    parser.add_argument("--title", "-t", help="Optional working title")
    parser.add_argument("--out", "-o", default="novel.md", help="Output Markdown path")
    parser.add_argument("--resume", action="store_true", help="Resume from saved state if available")
    parser.add_argument("--chapters", type=int, default=None, help="Limit number of chapters to write (for testing)")
    parser.add_argument("--images", action="store_true", help="Generate cover and chapter images (requires OPENROUTER_API_KEY)")
    parser.add_argument("--no-images", action="store_true", dest="no_images", help="Disable image generation even if API key is set")
    parser.add_argument("--flux-model", default=None, help="FLUX model to use (default: flux.2-klein-4b)")
    args = parser.parse_args()

    state_path = Path(RESUME_FILE)

    if args.resume:
        # Resume mode: load existing state
        state = load_or_init_state(state_path)
        if not state.get("concept"):
            prompt = args.prompt or input("Enter your novel concept/prompt: ").strip()
            state["concept"] = prompt
            if args.title:
                state["title"] = args.title
    else:
        # Fresh start: initialize new state, discard any existing state file
        prompt = args.prompt or input("Enter your novel concept/prompt: ").strip()
        state = create_fresh_state(title=args.title, concept=prompt)

    client = get_client()
    model = state["model"]
    temperature = state["temperature"]
    top_p = state.get("top_p", 0.95)
    max_tokens = state["max_output_tokens"]

    # Determine if images are enabled
    images_enabled = False
    images_dir = None
    flux_model = args.flux_model

    if args.no_images:
        images_enabled = False
    elif args.images:
        if not is_image_generation_enabled():
            console.print("[yellow]Warning: --images specified but OPENROUTER_API_KEY not set. Images disabled.[/yellow]")
        else:
            images_enabled = True
    elif is_image_generation_enabled():
        # Auto-enable if key is present
        images_enabled = True

    state["images_enabled"] = images_enabled

    if images_enabled:
        # Set up images directory next to output file
        out_path = Path(args.out)
        images_dir = out_path.parent / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        console.print(f"[cyan]Image generation enabled. Images will be saved to {images_dir}[/cyan]")

    # Outline phase
    if not state["outline_text"]:
        console.rule("[bold]Generating outline[/bold]")
        messages = [
            {"role": "system", "content": SYSTEM_PRIMER},
            {"role": "user", "content": f"{OUTLINE_PROMPT}\n\nConcept: {state['concept']}"}]
        stream = chat_complete_stream(client, model, messages, temperature, max_tokens, top_p)
        outline = stream_to_text(stream).strip()
        state["outline_text"] = outline
        state["outline_items"] = extract_outline_items(outline)
        state["current_idx"] = 0
        save_state(state_path, state)
        console.print(f"[green]Outline created with {len(state['outline_items'])} chapters.[/green]")
    else:
        console.print("[yellow]Using existing outline from state.[/yellow]")

    if not state["title"]:
        state["title"] = "A Novel Generated with Kimi K2.5"
        save_state(state_path, state)

    # Generate cover image (if enabled and not already generated)
    if images_enabled and not state.get("cover_image_path"):
        console.rule("[bold]Generating cover image[/bold]")
        try:
            cover_prompt = generate_cover_prompt(state["title"], state["concept"])
            image_bytes, ext = generate_image(cover_prompt, flux_model)
            cover_path = images_dir / f"cover.{ext}"
            save_image(image_bytes, cover_path)
            state["cover_image_path"] = str(cover_path)
            save_state(state_path, state)
            console.print(f"[green]Cover image saved to {cover_path}[/green]")
        except Exception as e:
            console.print(f"[yellow]Failed to generate cover image: {e}[/yellow]")

    # Chapter phase
    console.rule("[bold]Writing chapters[/bold]")
    total = len(state["outline_items"])
    if args.chapters:
        if args.resume and state["current_idx"] > 0:
            # When resuming, --chapters means "write N more chapters from current position"
            total = min(total, state["current_idx"] + args.chapters)
        else:
            # When starting fresh, --chapters means "write up to N chapters total"
            total = min(total, args.chapters)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Generating", total=total)
        start_idx = state["current_idx"]
        for idx in range(start_idx, total):
            title = state["outline_items"][idx]
            progress.update(task, description=f"Chapter {idx+1}: {title}")
            context_snippets = "\n\n".join(ch.get("content","")[-2000:] for ch in state["chapters"][-3:])

            messages = [
                {"role": "system", "content": SYSTEM_PRIMER},
                {"role": "user", "content": f"Novel concept:\n{state['concept']}\n\nExisting recent context (last chapters excerpts):\n{context_snippets}\n\n{CHAPTER_PROMPT.format(idx=idx+1, title=title)}"}
            ]
            stream = chat_complete_stream(client, model, messages, temperature, max_tokens, top_p)
            chapter_md = stream_to_text(stream).strip()
            if not chapter_md.lstrip().startswith("##"):
                chapter_md = f"## Chapter {idx+1}: {title}\n\n" + chapter_md

            chapter_data = {"title": title, "content": chapter_md}

            # Generate chapter image
            if images_enabled:
                try:
                    chapter_prompt = generate_chapter_prompt(
                        state["title"],
                        title,
                        chapter_md[:600]  # Use beginning of chapter as context
                    )
                    image_bytes, ext = generate_image(chapter_prompt, flux_model)
                    chapter_image_path = images_dir / f"chapter_{idx+1:02d}.{ext}"
                    save_image(image_bytes, chapter_image_path)
                    chapter_data["image_path"] = str(chapter_image_path)
                    console.print(f"[green]Chapter {idx+1} image saved[/green]")
                except Exception as e:
                    console.print(f"[yellow]Failed to generate chapter {idx+1} image: {e}[/yellow]")

            state["chapters"].append(chapter_data)
            state["current_idx"] = idx + 1
            save_state(state_path, state)
            progress.advance(task)

    out_path = Path(args.out)
    out_path.write_text(build_book_markdown(state), encoding="utf-8")
    console.rule("[bold green]Done[/bold green]")
    console.print(f"Wrote [bold]{out_path}[/bold] with {len(state['chapters'])} chapters.")
    console.print(f"State saved to {state_path}. Use --resume to continue.")

if __name__ == "__main__":
    main()
