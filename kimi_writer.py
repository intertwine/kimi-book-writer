#!/usr/bin/env python
"""
Kimi K2 Novelist
----------------
Generate a novel-length Markdown book using Moonshot AI's Kimi K2 reasoning models.

• Uses OpenAI SDK (v1) compatibility with base_url set to Moonshot.
• Streams content and saves a resumable state file.
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

def load_or_init_state(path: Path) -> Dict:
    if path.exists():
        return json.loads(path.read_text())
    return {
        "title": None,
        "concept": None,
        "model": env("KIMI_MODEL", "kimi-k2-thinking-turbo"),
        "temperature": float(env("KIMI_TEMPERATURE", "0.6")),
        "max_output_tokens": int(env("KIMI_MAX_OUTPUT_TOKENS", "4096")),
        "outline_text": None,
        "chapters": [],
        "outline_items": [],
        "current_idx": 0
    }

def save_state(path: Path, state: Dict):
    path.write_text(json.dumps(state, indent=2))

@retry(wait=wait_exponential(multiplier=1, min=1, max=20), stop=stop_after_attempt(5))
def chat_complete_stream(client: OpenAI, model: str, messages: List[Dict], temperature: float, max_tokens: int):
    return client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
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

def build_book_markdown(state: Dict) -> str:
    title = state["title"] or "Untitled Novel"
    parts = [f"# {title}\n"]
    if state.get("concept"):
        parts.append(f"*Generated from concept:* {state['concept']}\n")
    if state["outline_text"]:
        parts.append("## Outline\n\n" + state["outline_text"].strip() + "\n")
    for ch in state["chapters"]:
        parts.append(ch["content"].strip() + "\n")
    return "\n".join(parts)

def main():
    parser = argparse.ArgumentParser(description="Generate a novel-length Markdown book with Kimi K2.")
    parser.add_argument("--prompt", "-p", help="Concept prompt for the novel (if omitted, you will be asked)")
    parser.add_argument("--title", "-t", help="Optional working title")
    parser.add_argument("--out", "-o", default="novel.md", help="Output Markdown path")
    parser.add_argument("--resume", action="store_true", help="Resume from saved state if available")
    parser.add_argument("--chapters", type=int, default=None, help="Limit number of chapters to write (for testing)")
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
        state = {
            "title": args.title if args.title else None,
            "concept": prompt,
            "model": env("KIMI_MODEL", "kimi-k2-thinking-turbo"),
            "temperature": float(env("KIMI_TEMPERATURE", "0.6")),
            "max_output_tokens": int(env("KIMI_MAX_OUTPUT_TOKENS", "4096")),
            "outline_text": None,
            "chapters": [],
            "outline_items": [],
            "current_idx": 0
        }

    client = get_client()
    model = state["model"]
    temperature = state["temperature"]
    max_tokens = state["max_output_tokens"]

    # Outline phase
    if not state["outline_text"]:
        console.rule("[bold]Generating outline[/bold]")
        messages = [
            {"role": "system", "content": SYSTEM_PRIMER},
            {"role": "user", "content": f"{OUTLINE_PROMPT}\n\nConcept: {state['concept']}"}]
        stream = chat_complete_stream(client, model, messages, temperature, max_tokens)
        outline = stream_to_text(stream).strip()
        state["outline_text"] = outline
        state["outline_items"] = extract_outline_items(outline)
        state["current_idx"] = 0
        save_state(state_path, state)
        console.print(f"[green]Outline created with {len(state['outline_items'])} chapters.[/green]")
    else:
        console.print("[yellow]Using existing outline from state.[/yellow]")

    if not state["title"]:
        state["title"] = "A Novel Generated with Kimi K2"
        save_state(state_path, state)

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
            stream = chat_complete_stream(client, model, messages, temperature, max_tokens)
            chapter_md = stream_to_text(stream).strip()
            if not chapter_md.lstrip().startswith("##"):
                chapter_md = f"## Chapter {idx+1}: {title}\n\n" + chapter_md

            state["chapters"].append({"title": title, "content": chapter_md})
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
