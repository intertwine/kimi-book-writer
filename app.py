#!/usr/bin/env python
"""
Kimi Book Writer Web UI
-----------------------
A Streamlit-based web interface for generating, managing, and reading novels.
"""
import streamlit as st
import copy
import os
import json
import shutil
import subprocess
import re
import logging
import threading
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Literal
from dotenv import load_dotenv
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

# Load environment variables from .env file (must happen before importing kimi_writer)
load_dotenv()

# Import from existing modules (after load_dotenv so env vars are available)
from kimi_writer import (  # noqa: E402
    get_client,
    chat_complete_stream,
    build_book_markdown,
    SYSTEM_PRIMER,
    OUTLINE_PROMPT,
    CHAPTER_PROMPT,
    env
)
from utils import (  # noqa: E402
    extract_outline_items,
    get_novel_slug,
    validate_image_path,
    validate_flux_model,
    CONCEPT_EXCERPT_MAX_CHARS,
    CHAPTER_EXCERPT_MAX_CHARS,
)
from image_gen import (  # noqa: E402
    is_image_generation_enabled,
    generate_image,
    generate_cover_prompt,
    generate_chapter_prompt,
    save_image,
    get_flux_model,
)

# Configure logging for server-side error tracking
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Constants
PREVIEW_DIR = Path("preview")
PUBLISHED_DIR = Path("published")
PREVIEW_DIR.mkdir(exist_ok=True)
PUBLISHED_DIR.mkdir(exist_ok=True)

# Generation constants
THREAD_CLEANUP_TIMEOUT_SEC = 0.5  # Max time to wait for thread status update
SIDEBAR_REFRESH_INTERVAL_SEC = 1  # Auto-refresh interval for progress panel
CONTEXT_RECENT_CHAPTERS = 3  # Number of recent chapters for context
CONTEXT_CHAR_LIMIT = 2000  # Character limit per chapter in context
ERROR_MESSAGE_MAX_LENGTH = 250  # Max length for user-facing error messages

# Type alias for generation status
GenStatus = Literal["idle", "running", "paused", "completed", "error"]

# Lock for thread-safe session state updates from worker thread
_gen_state_lock = threading.Lock()


def init_gen_session_state() -> None:
    """Initialize generation-related session state keys if they don't exist."""
    defaults = {
        "gen_status": "idle",  # GenStatus
        "gen_progress_current": 0,
        "gen_progress_total": 0,
        "gen_progress_pct": 0.0,
        "gen_last_chapter": "",
        "gen_message": "",
        "gen_title": "",
        "gen_stop_event": threading.Event(),  # Thread-safe stop signal
        "gen_thread": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_generation_state() -> None:
    """Reset all generation state before starting new generation."""
    st.session_state.gen_status = "idle"
    st.session_state.gen_progress_current = 0
    st.session_state.gen_progress_total = 0
    st.session_state.gen_progress_pct = 0.0
    st.session_state.gen_last_chapter = ""
    st.session_state.gen_message = ""
    # Create fresh Event to avoid stale state from previous generation cycles
    st.session_state.gen_stop_event = threading.Event()


def is_generation_running() -> bool:
    """Check if generation thread is actively running."""
    gen_status = st.session_state.get("gen_status", "idle")
    gen_thread = st.session_state.get("gen_thread")
    return gen_status == "running" and gen_thread is not None and gen_thread.is_alive()


def cleanup_finished_thread() -> bool:
    """Clean up finished thread to allow garbage collection and handle race conditions."""
    gen_thread = st.session_state.get("gen_thread")

    if gen_thread is not None:
        # Use join() unconditionally with timeout to avoid TOCTOU race
        # (thread could complete between is_alive() check and join())
        gen_thread.join(timeout=THREAD_CLEANUP_TIMEOUT_SEC)

        # After join, check if thread is actually done
        if not gen_thread.is_alive():
            # If status is still "running" after join, worker didn't set final status
            if st.session_state.get("gen_status") == "running":
                with _gen_state_lock:
                    st.session_state.gen_status = "completed"

            # Allow garbage collection of finished thread
            st.session_state.gen_thread = None
            return True  # Thread was cleaned up
    return False  # No cleanup needed or thread still running


# Page config
st.set_page_config(
    page_title="Kimi Book Writer",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        margin-bottom: 2rem;
    }
    .novel-card {
        padding: 1rem;
        border-radius: 0.5rem;
        border: 1px solid #ddd;
        margin-bottom: 1rem;
    }
    .chapter-nav {
        position: sticky;
        top: 0;
        background: white;
        padding: 1rem 0;
        border-bottom: 1px solid #ddd;
        margin-bottom: 1rem;
        z-index: 100;
    }
</style>
""", unsafe_allow_html=True)

# Utility functions
def validate_path_within_directory(path: Path, allowed_dir: Path) -> Path:
    """
    Validate that a path resolves within an allowed directory.
    Raises ValueError if path traversal is detected.
    """
    resolved = path.resolve()
    allowed_resolved = allowed_dir.resolve()
    if not str(resolved).startswith(str(allowed_resolved) + os.sep) and resolved != allowed_resolved:
        raise ValueError(f"Path traversal detected: {path} resolves outside {allowed_dir}")
    return resolved

def strip_markdown_formatting(text: str) -> str:
    """Strip markdown bold (**text**) and italic (*text*) formatting from a string."""
    # First strip bold (double asterisks)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # Then strip italic (single asterisks)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    return text

def get_novel_state_path(title: str, preview: bool = True) -> Path:
    """Get the path to a novel's state file."""
    slug = get_novel_slug(title)
    base_dir = PREVIEW_DIR if preview else PUBLISHED_DIR
    return base_dir / f"{slug}_state.json"

def get_novel_md_path(title: str, preview: bool = True) -> Path:
    """Get the path to a novel's markdown file."""
    slug = get_novel_slug(title)
    base_dir = PREVIEW_DIR if preview else PUBLISHED_DIR
    return base_dir / f"{slug}.md"

def list_novels(preview: bool = True) -> List[Dict]:
    """List all novels in preview or published directory."""
    base_dir = PREVIEW_DIR if preview else PUBLISHED_DIR
    novels = []
    errors = []

    for state_file in base_dir.glob("*_state.json"):
        try:
            state = json.loads(state_file.read_text())
            slug = state_file.stem.replace("_state", "")
            md_file = base_dir / f"{slug}.md"

            novels.append({
                "title": state.get("title", "Untitled"),
                "slug": slug,
                "concept": state.get("concept", ""),
                "chapters_written": len(state.get("chapters", [])),
                "total_chapters": len(state.get("outline_items", [])),
                "state_path": state_file,
                "md_path": md_file,
                "state": state,
                "exists": md_file.exists()
            })
        except Exception as e:
            # Log error server-side and collect for contextual display
            logger.error(f"Error loading {state_file}: {e}", exc_info=True)
            errors.append(f"Failed to load {state_file.name}")

    # Return novels and errors separately for contextual display
    return sorted(novels, key=lambda x: x["title"]), errors

def get_novel_images_dir(title: str, preview: bool = True) -> Path:
    """Get the images directory for a novel."""
    slug = get_novel_slug(title)
    base_dir = PREVIEW_DIR if preview else PUBLISHED_DIR
    return base_dir / f"{slug}_images"


def init_novel_state(title: str, concept: str, max_chapters: int = 30, flux_model: str = None) -> Dict:
    """Initialize a new novel state."""
    return {
        "title": title,
        "concept": concept,
        "model": env("KIMI_MODEL", "kimi-k2.5"),
        "temperature": float(env("KIMI_TEMPERATURE", "1.0")),
        "top_p": float(env("KIMI_TOP_P", "0.95")),
        "max_output_tokens": int(env("KIMI_MAX_OUTPUT_TOKENS", "8192")),
        "max_chapters": max_chapters,
        "outline_text": None,
        "chapters": [],
        "outline_items": [],
        "current_idx": 0,
        "images_enabled": False,
        "flux_model": flux_model,  # Persist for resume
        "cover_image_path": None,
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat()
    }

def save_novel_state(title: str, state: Dict, preview: bool = True):
    """Save novel state to file."""
    state["updated_at"] = datetime.now().isoformat()
    state_path = get_novel_state_path(title, preview)
    state_path.write_text(json.dumps(state, indent=2))

def publish_novel(title: str):
    """Move a novel from preview to published and commit to git."""
    slug = get_novel_slug(title)

    # Copy files
    preview_state = PREVIEW_DIR / f"{slug}_state.json"
    preview_md = PREVIEW_DIR / f"{slug}.md"
    preview_images = PREVIEW_DIR / f"{slug}_images"
    published_state = PUBLISHED_DIR / f"{slug}_state.json"
    published_md = PUBLISHED_DIR / f"{slug}.md"
    published_images = PUBLISHED_DIR / f"{slug}_images"

    if not preview_state.exists() or not preview_md.exists():
        raise FileNotFoundError("Preview files not found")

    shutil.copy2(preview_state, published_state)
    shutil.copy2(preview_md, published_md)

    # Copy images directory if it exists
    if preview_images.exists():
        if published_images.exists():
            shutil.rmtree(published_images)
        shutil.copytree(preview_images, published_images)

    # Git commit
    try:
        # Add files to staging (including images if present)
        files_to_add = [str(published_md), str(published_state)]
        if published_images.exists():
            files_to_add.append(str(published_images))
        subprocess.run(
            ["git", "add"] + files_to_add,
            check=True,
            capture_output=True,
            text=True
        )

        # Check if there are changes to commit
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            capture_output=True
        )

        if result.returncode == 0:
            # No changes to commit (file already published with same content)
            logger.info(f"Novel '{title}' already published with same content, no commit needed")
        else:
            # Commit the changes
            subprocess.run(
                ["git", "commit", "-m", f"Publish novel: {title}"],
                check=True,
                capture_output=True,
                text=True
            )
            logger.info(f"Successfully published and committed novel: {title}")

        # Remove preview files after successful publish
        try:
            if preview_state.exists():
                preview_state.unlink()
            if preview_md.exists():
                preview_md.unlink()
            if preview_images.exists():
                shutil.rmtree(preview_images)
            logger.info(f"Cleaned up preview files for '{title}'")
        except OSError as e:
            logger.warning(f"Could not delete preview files for '{title}': {e}")
            # Non-critical - publish still succeeded

        return True

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        logger.error(f"Git operation failed for novel '{title}': {error_msg}", exc_info=True)
        st.error("Failed to commit to git. Please ensure git is configured properly.")
        return False
    except Exception as e:
        logger.error(f"Unexpected error publishing novel '{title}': {e}", exc_info=True)
        st.error(f"Unexpected error during publish: {str(e)}")
        return False

def delete_novel(title: str, preview: bool = True):
    """Delete a novel's files with path traversal protection."""
    base_dir = PREVIEW_DIR if preview else PUBLISHED_DIR
    state_path = get_novel_state_path(title, preview)
    md_path = get_novel_md_path(title, preview)
    images_dir = get_novel_images_dir(title, preview)

    # Validate all paths are within expected directory (defense in depth)
    try:
        validate_path_within_directory(state_path, base_dir)
        validate_path_within_directory(md_path, base_dir)
        validate_path_within_directory(images_dir, base_dir)
    except ValueError as e:
        logger.error(f"Path validation failed in delete_novel: {e}")
        raise

    if state_path.exists():
        state_path.unlink()
    if md_path.exists():
        md_path.unlink()
    if images_dir.exists():
        shutil.rmtree(images_dir)

# UI Components
def render_generate_tab():
    """Render the novel generation tab."""
    st.markdown('<div class="main-header">📝 Generate Novel</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Create a new novel or continue an existing one</div>', unsafe_allow_html=True)

    # List existing preview novels
    preview_novels, load_errors = list_novels(preview=True)

    # Display any loading errors
    if load_errors:
        st.warning("⚠️ Some novels failed to load:")
        for error in load_errors:
            st.caption(f"- {error}")

    col1, col2 = st.columns([2, 1])

    with col1:
        # Clean up finished thread and handle race conditions.
        # If thread just finished, trigger rerun to refresh UI with new status.
        # Note: st.rerun() exits the function immediately, so code below won't execute.
        if cleanup_finished_thread():
            st.rerun()

        # Get current generation status (thread is either still running or already cleaned up)
        gen_status = st.session_state.get("gen_status", "idle")
        is_running = is_generation_running()

        if not is_running:
            # Mode selection - disabled if generation just completed/errored
            mode = st.radio(
                "Mode",
                ["New Novel", "Continue Existing"],
                horizontal=True
            )

            if mode == "New Novel":
                title = st.text_input("Novel Title *", placeholder="Enter a compelling title...")
                concept = st.text_area(
                    "Novel Concept *",
                    placeholder="Describe your novel idea, themes, characters, setting...",
                    height=150
                )

                col_a, col_b = st.columns(2)
                with col_a:
                    max_chapters = st.number_input("Max Chapters", min_value=5, max_value=100, value=30)
                with col_b:
                    temperature = st.slider(
                        "Temperature",
                        min_value=0.0,
                        max_value=1.5,
                        value=1.0,
                        step=0.1,
                        help="Lower = more focused. Higher = more creative. 1.0 recommended for K2.5."
                    )

                col_c, col_d = st.columns(2)
                with col_c:
                    top_p = st.slider(
                        "Top P",
                        min_value=0.0,
                        max_value=1.0,
                        value=0.95,
                        step=0.05,
                        help="Nucleus sampling. 0.95 recommended for K2.5."
                    )
                with col_d:
                    # Image generation settings
                    if is_image_generation_enabled():
                        enable_images = st.checkbox(
                            "Generate illustrations",
                            value=True,
                            help="Generate cover and chapter images using FLUX"
                        )
                    else:
                        st.caption("Add OPENROUTER_API_KEY for illustrations")
                        enable_images = False

                # FLUX model selection (only if images enabled)
                flux_model = None
                if enable_images:
                    flux_model = st.selectbox(
                        "Image model",
                        options=[
                            "black-forest-labs/flux.2-klein-4b",
                            "black-forest-labs/flux.2-max"
                        ],
                        format_func=lambda x: "FLUX.2 Klein (Fast)" if "klein" in x else "FLUX.2 Max (Quality)",
                        help="Klein is faster and cheaper, Max produces higher quality"
                    )

                if st.button("Start Generation", use_container_width=True):
                    if not title or not concept:
                        st.error("Please provide both title and concept.")
                    else:
                        # Check if novel already exists
                        existing = get_novel_state_path(title, preview=True)
                        if existing.exists():
                            st.error(f"A novel with title '{title}' already exists in preview. Please choose a different title or continue the existing one.")
                        else:
                            # Start generation (reset_generation_state() called internally)
                            generate_novel(title, concept, max_chapters, temperature, top_p, enable_images, flux_model)
                            st.rerun()

            else:  # Continue Existing
                if not preview_novels:
                    st.info("No novels in preview. Create a new novel to get started!")
                else:
                    novel_options = {n["title"]: n for n in preview_novels}
                    selected_title = st.selectbox(
                        "Select Novel to Continue",
                        options=list(novel_options.keys())
                    )

                    if selected_title:
                        novel = novel_options[selected_title]
                        st.info(f"**Concept:** {novel['concept']}")
                        st.info(f"**Progress:** {novel['chapters_written']}/{novel['total_chapters']} chapters")

                        is_complete = novel['chapters_written'] >= novel['total_chapters'] and novel['total_chapters'] > 0

                        if is_complete:
                            st.success("✅ This novel is complete!")
                            if st.button("✅ Publish", use_container_width=True, type="primary"):
                                with st.spinner("Publishing and committing to git..."):
                                    if publish_novel(novel['title']):
                                        st.balloons()
                                        st.success(f"🎉 '{novel['title']}' published successfully! Moved to Published library.")
                                        time.sleep(1.5)  # Brief pause to show success message
                                        st.rerun()
                                    else:
                                        st.error("Failed to publish. Check the logs for details.")
                        else:
                            if st.button("Continue Generation", use_container_width=True):
                                # Start generation (reset_generation_state() called internally)
                                continue_novel(novel)
                                st.rerun()

            # Show status message for completed/paused/error states
            if gen_status == "completed":
                st.success(f"🎉 {st.session_state.get('gen_message', 'Generation completed!')}")
                if st.button("✅ Generation Completed", disabled=True, use_container_width=True):
                    pass
            elif gen_status == "paused":
                st.warning(f"⏸️ {st.session_state.get('gen_message', 'Generation paused.')}")
            elif gen_status == "error":
                st.error(f"❌ {st.session_state.get('gen_message', 'An error occurred.')}")
                if st.button("⚠️ Generation Error", disabled=True, use_container_width=True):
                    pass

        else:
            # Generation in progress - show pause button
            st.caption("Progress is saved after each chapter. You can pause and continue later from the Library.")
            st.info(f"**Generating:** {st.session_state.get('gen_title', 'Novel')}")

            # Show current progress in the main area too
            progress_pct = st.session_state.get("gen_progress_pct", 0)
            st.progress(progress_pct)
            st.caption(st.session_state.get("gen_message", "Starting..."))

            if st.button("⏸️ Pause Generation", use_container_width=True, type="primary"):
                st.session_state.gen_stop_event.set()  # Thread-safe stop signal
                st.rerun()

    with col2:
        with st.expander("💡 Tips", expanded=True):
            st.markdown("""
**Good Concepts Include:**
- Genre and tone
- Main characters
- Setting/world
- Central conflict
- Themes to explore

**Example:**
*"A cyberpunk thriller set in 2150 Tokyo. A rogue AI detective must solve a series of murders in the virtual realm while questioning their own consciousness. Themes: identity, reality vs simulation, corporate dystopia."*
            """)

def _update_gen_state(**kwargs) -> None:
    """Thread-safe helper to update generation state atomically."""
    with _gen_state_lock:
        # Use update() to apply all changes atomically, minimizing the window
        # where partially-updated state could be observed by the UI thread
        st.session_state.update(kwargs)


def _generation_worker(title: str, concept: str, max_chapters: int, temperature: float, top_p: float, images_enabled: bool, flux_model: str, is_new: bool, state: Dict) -> None:
    """
    Background worker for novel generation.
    Updates session state with progress; does NOT call Streamlit UI methods.
    Uses _gen_state_lock for thread-safe state updates.
    """
    try:
        client = get_client()
        model = state["model"]
        max_tokens = state["max_output_tokens"]

        # Set up images directory if enabled (with race condition handling)
        images_dir = None
        if images_enabled:
            images_dir = get_novel_images_dir(title, preview=True)
            try:
                images_dir.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                logger.warning(f"Failed to create images directory {images_dir}: {e}")
                images_dir = None
                images_enabled = False

        # Phase 1: Generate outline (for new novels OR novels paused during outline generation)
        if is_new or not state.get("outline_items"):
            _update_gen_state(gen_message="Generating outline...")
            messages = [
                {"role": "system", "content": SYSTEM_PRIMER},
                {"role": "user", "content": f"{OUTLINE_PROMPT}\n\nConcept: {concept}"}
            ]
            stream = chat_complete_stream(client, model, messages, temperature, max_tokens, top_p)

            outline_chunks = []
            chunk_count = 0
            for chunk in stream:
                # Check for pause request with lock to prevent race conditions
                with _gen_state_lock:
                    if st.session_state.gen_stop_event.is_set():
                        st.session_state.update({"gen_status": "paused", "gen_message": "Paused during outline generation"})
                        st.session_state.gen_stop_event.clear()  # Clear after state transition
                        return

                chunk_count += 1
                delta = chunk.choices[0].delta

                # Kimi K2 thinking models may return content in delta.thinking or delta.content
                # Prefer content, but fall back to thinking if content is empty
                content = getattr(delta, "content", None)
                thinking = getattr(delta, "thinking", None)

                if content:
                    outline_chunks.append(content)
                elif thinking:
                    # Log first occurrence of thinking-only response for debugging
                    if not outline_chunks and chunk_count == 1:
                        logger.info("Outline stream: receiving thinking tokens (Kimi K2 thinking model)")
                    outline_chunks.append(thinking)

            logger.info(f"Outline stream completed: {chunk_count} chunks, {len(outline_chunks)} content chunks")

            outline = "".join(outline_chunks).strip()
            state["outline_text"] = outline
            state["outline_items"] = extract_outline_items(outline)[:max_chapters]
            save_novel_state(title, state, preview=True)

            # Validate outline was generated successfully
            if not state["outline_items"]:
                logger.error(f"Outline generation failed: no chapters extracted. Outline text length: {len(outline)}")
                if not outline:
                    _update_gen_state(
                        gen_status="error",
                        gen_message="Outline generation failed: no content received from API. Please try again."
                    )
                else:
                    _update_gen_state(
                        gen_status="error",
                        gen_message=f"Outline generation failed: could not parse chapter titles from outline ({len(outline)} chars received)."
                    )
                return

            _update_gen_state(gen_message=f"Outline created with {len(state['outline_items'])} chapters")

        # Generate cover image (if enabled and not already generated)
        if images_enabled and not state.get("cover_image_path"):
            _update_gen_state(gen_message="Generating cover image...")
            try:
                cover_prompt = generate_cover_prompt(state["title"], concept)
                image_bytes, ext = generate_image(cover_prompt, flux_model)
                cover_path = images_dir / f"cover.{ext}"
                save_image(image_bytes, cover_path)
                state["cover_image_path"] = str(cover_path)
                save_novel_state(title, state, preview=True)
                logger.info(f"Cover image saved to {cover_path}")
            except Exception as e:
                logger.warning(f"Failed to generate cover image: {e}")
                # Track failure in state for debugging
                if "failed_images" not in state:
                    state["failed_images"] = []
                state["failed_images"].append({"type": "cover", "error": str(e)})
                save_novel_state(title, state, preview=True)

        # Phase 2: Generate chapters
        total_chapters = len(state["outline_items"])
        _update_gen_state(gen_progress_total=total_chapters)
        start_idx = state.get("current_idx", 0) if not is_new else 0

        for idx in range(start_idx, total_chapters):
            # Check for pause request with lock to prevent race conditions
            with _gen_state_lock:
                if st.session_state.gen_stop_event.is_set():
                    st.session_state.update({"gen_status": "paused", "gen_message": f"Paused at chapter {idx}/{total_chapters}"})
                    st.session_state.gen_stop_event.clear()  # Clear after state transition
                    return

            chapter_title = state["outline_items"][idx]
            _update_gen_state(
                gen_progress_current=idx + 1,
                gen_progress_pct=(idx + 1) / total_chapters,
                gen_last_chapter=strip_markdown_formatting(chapter_title),
                gen_message=f"Writing Chapter {idx + 1}/{total_chapters}: {strip_markdown_formatting(chapter_title)}"
            )

            # Build context using constants
            user_content = f"Novel concept:\n{concept}\n\n"
            if state["chapters"]:
                context_snippets = "\n\n".join(
                    ch.get("content", "")[-CONTEXT_CHAR_LIMIT:] for ch in state["chapters"][-CONTEXT_RECENT_CHAPTERS:]
                )
                user_content += f"Existing recent context (last chapters excerpts):\n{context_snippets}\n\n"
            user_content += CHAPTER_PROMPT.format(idx=idx+1, title=chapter_title)

            messages = [
                {"role": "system", "content": SYSTEM_PRIMER},
                {"role": "user", "content": user_content}
            ]

            stream = chat_complete_stream(client, model, messages, temperature, max_tokens, top_p)

            chapter_chunks = []
            for chunk in stream:
                # Check for pause request with lock to prevent race conditions
                with _gen_state_lock:
                    if st.session_state.gen_stop_event.is_set():
                        st.session_state.update({"gen_status": "paused", "gen_message": f"Paused during chapter {idx + 1}"})
                        st.session_state.gen_stop_event.clear()  # Clear after state transition
                        return

                delta = chunk.choices[0].delta

                # Kimi K2 thinking models may return content in delta.thinking or delta.content
                content = getattr(delta, "content", None)
                thinking = getattr(delta, "thinking", None)

                if content:
                    chapter_chunks.append(content)
                elif thinking:
                    chapter_chunks.append(thinking)

            chapter_md = "".join(chapter_chunks).strip()
            if not chapter_md.lstrip().startswith("##"):
                chapter_md = f"## Chapter {idx+1}: {chapter_title}\n\n" + chapter_md

            chapter_data = {"title": chapter_title, "content": chapter_md}

            # Generate chapter image
            if images_enabled and images_dir:
                _update_gen_state(gen_message=f"Generating image for Chapter {idx + 1}...")
                try:
                    chapter_prompt = generate_chapter_prompt(
                        state["title"],
                        chapter_title,
                        chapter_md[:600]  # Use beginning of chapter as context
                    )
                    image_bytes, ext = generate_image(chapter_prompt, flux_model)
                    chapter_image_path = images_dir / f"chapter_{idx+1:02d}.{ext}"
                    save_image(image_bytes, chapter_image_path)
                    chapter_data["image_path"] = str(chapter_image_path)
                    logger.info(f"Chapter {idx+1} image saved")
                except Exception as e:
                    logger.warning(f"Failed to generate chapter {idx+1} image: {e}")
                    # Track failure in state for debugging
                    if "failed_images" not in state:
                        state["failed_images"] = []
                    state["failed_images"].append({"type": f"chapter_{idx+1}", "error": str(e)})

            state["chapters"].append(chapter_data)
            state["current_idx"] = idx + 1

            # Save state and markdown
            save_novel_state(title, state, preview=True)
            md_path = get_novel_md_path(title, preview=True)
            md_path.write_text(build_book_markdown(state), encoding="utf-8")

        # Completed successfully
        _update_gen_state(
            gen_status="completed",
            gen_progress_pct=1.0,
            gen_progress_current=total_chapters,
            gen_message=f"Novel complete! {total_chapters} chapters written."
        )

    except Exception as e:
        logger.error(f"Error during novel generation: {e}", exc_info=True)

        # User-friendly error messages
        error_msg = str(e).lower()
        if "api.moonshot.ai" in error_msg or "connection" in error_msg or "timeout" in error_msg:
            user_msg = "API connection failed. Check your internet connection and API key."
        elif "rate limit" in error_msg or "429" in error_msg:
            user_msg = "API rate limit exceeded. Please wait a few minutes and try again."
        elif "401" in error_msg or "unauthorized" in error_msg or "api key" in error_msg:
            user_msg = "Invalid API key. Please check your MOONSHOT_API_KEY in .env file."
        elif "insufficient" in error_msg or "quota" in error_msg or "balance" in error_msg:
            user_msg = "API quota exceeded. Please check your account balance."
        else:
            # Truncate long error messages, preserving useful context
            error_str = str(e)
            if len(error_str) > ERROR_MESSAGE_MAX_LENGTH:
                user_msg = f"Generation failed: {error_str[:ERROR_MESSAGE_MAX_LENGTH]}..."
            else:
                user_msg = f"Generation failed: {error_str}"

        _update_gen_state(gen_status="error", gen_message=user_msg)


def start_generation_thread(title: str, concept: str, max_chapters: int, temperature: float, top_p: float, images_enabled: bool, flux_model: str, is_new: bool, state: Dict) -> None:
    """Start the generation worker in a background thread with Streamlit context."""
    # Reset all progress state before starting
    reset_generation_state()
    st.session_state.gen_status = "running"
    st.session_state.gen_title = title
    st.session_state.gen_message = "Starting generation..."

    # Deep copy state to prevent race conditions with shared dict mutation
    state_copy = copy.deepcopy(state)

    # Create thread with Streamlit context
    # Note: daemon=True ensures thread won't block app shutdown, but may leave
    # novels in incomplete state. This is acceptable since state is saved after each chapter.
    ctx = get_script_run_ctx()
    thread = threading.Thread(
        target=_generation_worker,
        args=(title, concept, max_chapters, temperature, top_p, images_enabled, flux_model, is_new, state_copy),
        daemon=True
    )
    add_script_run_ctx(thread, ctx)

    # Start thread with error handling
    try:
        thread.start()
        st.session_state.gen_thread = thread
    except Exception as e:
        logger.error(f"Failed to start generation thread: {e}", exc_info=True)
        st.session_state.gen_status = "error"
        st.session_state.gen_message = "Failed to start generation. Please try again."
        st.session_state.gen_thread = None


def generate_novel(title: str, concept: str, max_chapters: int, temperature: float, top_p: float = 0.95, images_enabled: bool = False, flux_model: str = None) -> None:
    """Generate a new novel from scratch (starts background thread)."""
    state = init_novel_state(title, concept, max_chapters, flux_model=flux_model)
    state["temperature"] = temperature
    state["top_p"] = top_p
    state["images_enabled"] = images_enabled
    start_generation_thread(title, concept, max_chapters, temperature, top_p, images_enabled, flux_model, is_new=True, state=state)

def continue_novel(novel: Dict) -> None:
    """Continue generating an incomplete novel (starts background thread)."""
    state = novel["state"]
    title = state["title"]
    concept = state["concept"]
    temperature = state["temperature"]
    top_p = state.get("top_p", 0.95)
    images_enabled = state.get("images_enabled", False)
    # Load flux_model from state if available, fallback to env default
    flux_model = state.get("flux_model") or (get_flux_model() if images_enabled else None)

    # Use existing outline length, or stored max_chapters if outline was never generated
    # (e.g., paused during outline generation). Fall back to 30 for legacy state files.
    max_chapters = len(state["outline_items"]) if state.get("outline_items") else state.get("max_chapters", 30)

    # Only mark as complete if we have an outline AND all chapters are written
    if state.get("outline_items") and state["current_idx"] >= len(state["outline_items"]):
        st.session_state.gen_status = "completed"
        st.session_state.gen_message = "This novel is already complete!"
        return

    start_generation_thread(title, concept, max_chapters, temperature, top_p, images_enabled, flux_model, is_new=False, state=state)

def render_library_tab():
    """Render the library management tab."""
    st.markdown('<div class="main-header">📚 Library</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Manage and read your novels</div>', unsafe_allow_html=True)

    # Tabs for preview and published
    tab1, tab2 = st.tabs(["📝 Preview", "✅ Published"])

    with tab1:
        render_novel_list(preview=True)

    with tab2:
        render_novel_list(preview=False)

def render_novel_list(preview: bool):
    """Render a list of novels."""
    novels, load_errors = list_novels(preview=preview)

    # Display any loading errors
    if load_errors:
        st.warning("⚠️ Some novels failed to load:")
        for error in load_errors:
            st.caption(f"- {error}")

    if not novels:
        st.info(f"No novels in {'preview' if preview else 'published'} yet.")
        return

    for novel in novels:
        with st.container():
            col1, col2, col3 = st.columns([3, 1, 1])

            with col1:
                st.markdown(f"### {novel['title']}")
                st.caption(novel['concept'][:150] + "..." if len(novel['concept']) > 150 else novel['concept'])

                # Progress indicator
                progress = novel['chapters_written'] / novel['total_chapters'] if novel['total_chapters'] > 0 else 0
                st.progress(progress)
                st.caption(f"{novel['chapters_written']}/{novel['total_chapters']} chapters")

            with col2:
                # Only show Read button if novel has chapters
                if novel['chapters_written'] > 0:
                    if st.button("📖 Read", key=f"read_{novel['slug']}_{preview}"):
                        st.session_state.reading_novel = novel
                        st.session_state.reading_preview = preview
                        st.rerun()

                if novel['exists'] and novel['chapters_written'] > 0:
                    with open(novel['md_path'], 'r') as f:
                        st.download_button(
                            "⬇️ Download",
                            f.read(),
                            file_name=f"{novel['slug']}.md",
                            mime="text/markdown",
                            key=f"download_{novel['slug']}_{preview}"
                        )
                elif novel['chapters_written'] == 0:
                    st.button("⬇️ Download", disabled=True, key=f"download_disabled_{novel['slug']}_{preview}", help="No content yet")

            with col3:
                if preview:
                    # Check if generation is currently running
                    is_running = is_generation_running()

                    if novel['chapters_written'] >= novel['total_chapters']:
                        if st.button("✅ Publish", key=f"publish_{novel['slug']}"):
                            with st.spinner("Publishing..."):
                                if publish_novel(novel['title']):
                                    st.success("Published successfully!")
                                    st.rerun()
                    else:
                        # Show Continue button for incomplete novels (disabled if generation is running)
                        if st.button("▶️ Continue", key=f"continue_{novel['slug']}", disabled=is_running):
                            # Start generation (reset_generation_state() called internally)
                            continue_novel(novel)
                            st.rerun()

                with st.popover("🗑️ Delete", use_container_width=True):
                    st.warning(f"Delete **{novel['title']}**?")
                    st.caption("This action cannot be undone.")
                    if st.button("Yes, delete", key=f"confirm_delete_{novel['slug']}_{preview}", type="primary"):
                        # Clear reading state if deleting the currently open novel
                        if 'reading_novel' in st.session_state:
                            if st.session_state.reading_novel['title'] == novel['title']:
                                del st.session_state.reading_novel
                                if 'reading_preview' in st.session_state:
                                    del st.session_state.reading_preview
                                if 'selected_chapter' in st.session_state:
                                    del st.session_state.selected_chapter

                        delete_novel(novel['title'], preview=preview)
                        st.success("Deleted!")
                        st.rerun()

            st.markdown("---")

def render_reader():
    """Render the novel reader."""
    if 'reading_novel' not in st.session_state:
        st.info("Select a novel from the Library to read.")
        return

    novel = st.session_state.reading_novel
    preview = st.session_state.reading_preview

    # Header
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(f'<div class="main-header">📖 {novel["title"]}</div>', unsafe_allow_html=True)
    with col2:
        if st.button("← Back to Library"):
            # Clear all reading-related session state
            if 'reading_novel' in st.session_state:
                del st.session_state.reading_novel
            if 'reading_preview' in st.session_state:
                del st.session_state.reading_preview
            if 'selected_chapter' in st.session_state:
                del st.session_state.selected_chapter
            # Set flag to show Library tab when returning
            st.session_state.show_library_tab = True
            st.rerun()

    # Verify novel file exists
    md_path = get_novel_md_path(novel['title'], preview)
    if not md_path.exists():
        st.error("Novel file not found!")
        return

    # Extract chapters
    state = novel['state']
    chapters = state.get('chapters', [])

    # Display cover image if available (with path validation)
    cover_path = state.get("cover_image_path")
    if cover_path and validate_image_path(cover_path, PREVIEW_DIR):
        cover_file = Path(cover_path)
        if cover_file.exists():
            st.image(str(cover_file), caption="Cover", use_container_width=True)

    if not chapters:
        st.warning("No chapters available.")
        return

    # Chapter navigation
    st.markdown('<div class="chapter-nav">', unsafe_allow_html=True)
    chapter_titles = [f"Ch {i+1}: {strip_markdown_formatting(ch['title'])}" for i, ch in enumerate(chapters)]

    # Initialize selected chapter in session state
    if 'selected_chapter' not in st.session_state:
        st.session_state.selected_chapter = 0

    # Callback to update session state when selectbox changes
    def on_chapter_select():
        st.session_state.selected_chapter = st.session_state.chapter_selector

    # Sync the selectbox key with session state before rendering
    st.session_state.chapter_selector = st.session_state.selected_chapter

    st.selectbox(
        "Jump to chapter:",
        range(len(chapters)),
        format_func=lambda x: chapter_titles[x],
        key="chapter_selector",
        on_change=on_chapter_select
    )

    st.markdown('</div>', unsafe_allow_html=True)

    # Display selected chapter
    selected_chapter = st.session_state.selected_chapter
    chapter = chapters[selected_chapter]

    # Display chapter image if available (with path validation)
    chapter_image_path = chapter.get("image_path")
    if chapter_image_path and validate_image_path(chapter_image_path, PREVIEW_DIR):
        chapter_image_file = Path(chapter_image_path)
        if chapter_image_file.exists():
            st.image(str(chapter_image_file), caption=f"Chapter {selected_chapter + 1}", use_container_width=True)

    st.markdown(chapter['content'])

    # Navigation buttons
    col1, col2, col3 = st.columns([1, 2, 1])
    with col1:
        if selected_chapter > 0:
            if st.button("← Previous Chapter"):
                st.session_state.selected_chapter = selected_chapter - 1
                st.rerun()
    with col3:
        if selected_chapter < len(chapters) - 1:
            if st.button("Next Chapter →"):
                st.session_state.selected_chapter = selected_chapter + 1
                st.rerun()

# Sidebar progress panel using fragment for auto-refresh
@st.fragment(run_every=SIDEBAR_REFRESH_INTERVAL_SEC)
def render_sidebar_progress() -> None:
    """Auto-refreshing sidebar progress panel for generation status."""
    gen_status = st.session_state.get("gen_status", "idle")

    # Only show progress panel if there's active or recent generation
    if gen_status == "idle":
        return

    st.markdown("### Generation Progress")

    if is_generation_running():
        # Active generation
        title = st.session_state.get("gen_title", "Novel")
        progress_pct = st.session_state.get("gen_progress_pct", 0)
        current = st.session_state.get("gen_progress_current", 0)
        total = st.session_state.get("gen_progress_total", 0)
        message = st.session_state.get("gen_message", "Starting...")
        last_chapter = st.session_state.get("gen_last_chapter", "")

        st.markdown(f"**{title}**")
        st.progress(progress_pct)
        if total > 0:
            st.caption(f"Chapter {current}/{total}")
        if last_chapter:
            st.caption(f"Latest: {last_chapter}")
        st.info(message)
        st.caption("New generation disabled while running.")

    elif gen_status == "completed":
        title = st.session_state.get("gen_title", "Novel")
        message = st.session_state.get("gen_message", "Completed!")
        st.markdown(f"**{title}**")
        st.progress(1.0)
        st.success(message)
        if st.button("Clear Status", key="clear_gen_status_sidebar"):
            st.session_state.gen_status = "idle"
            st.rerun()

    elif gen_status == "paused":
        title = st.session_state.get("gen_title", "Novel")
        message = st.session_state.get("gen_message", "Paused")
        st.markdown(f"**{title}**")
        progress_pct = st.session_state.get("gen_progress_pct", 0)
        st.progress(progress_pct)
        st.warning(message)
        if st.button("Clear Status", key="clear_gen_status_sidebar_paused"):
            st.session_state.gen_status = "idle"
            st.rerun()

    elif gen_status == "error":
        title = st.session_state.get("gen_title", "Novel")
        message = st.session_state.get("gen_message", "Error occurred")
        st.markdown(f"**{title}**")
        st.error(message)
        if st.button("Clear Status", key="clear_gen_status_sidebar_error"):
            st.session_state.gen_status = "idle"
            st.rerun()

    st.markdown("---")


# Main app
def main():
    # Initialize generation session state
    init_gen_session_state()

    # Sidebar
    with st.sidebar:
        st.markdown("# 📚 Kimi Book Writer")
        st.markdown("Generate complete novels with AI")
        st.markdown("---")

        # Check for API key
        if not os.getenv("MOONSHOT_API_KEY"):
            st.error("⚠️ MOONSHOT_API_KEY not set!")
            st.info("Create a `.env` file with your API key.")
        else:
            st.success("✅ API key loaded")

        st.markdown("---")

        # Render progress panel (auto-refreshes every 1s when running)
        render_sidebar_progress()

        st.markdown("### Stats")
        preview_novels, _ = list_novels(preview=True)
        published_novels, _ = list_novels(preview=False)

        # Calculate complete vs incomplete for preview
        complete_previews = sum(1 for n in preview_novels if n['chapters_written'] >= n['total_chapters'] and n['total_chapters'] > 0)
        incomplete_previews = len(preview_novels) - complete_previews

        st.metric("Preview Novels", len(preview_novels))
        if preview_novels:
            st.caption(f"  {complete_previews} complete, {incomplete_previews} in progress")
        st.metric("Published Novels", len(published_novels))

        st.markdown("---")
        st.markdown("### About")
        st.markdown("Powered by Moonshot AI's Kimi K2.5 models")
        if is_image_generation_enabled():
            st.markdown("Images: FLUX via OpenRouter")
        st.markdown("[Documentation](https://github.com/intertwine/kimi-book-writer)")

    # Main content
    if 'reading_novel' in st.session_state:
        render_reader()
    else:
        # Check if we should show Library tab (e.g., returning from reader)
        default_tab = 1 if st.session_state.pop('show_library_tab', False) else 0

        # Create tabs - Streamlit doesn't support default_index, so we use a workaround
        if default_tab == 1:
            # Show Library first by reordering, then swap back visually
            tab2, tab1 = st.tabs(["📚 Library", "📝 Generate"])
            with tab1:
                render_generate_tab()
            with tab2:
                render_library_tab()
        else:
            tab1, tab2 = st.tabs(["📝 Generate", "📚 Library"])
            with tab1:
                render_generate_tab()
            with tab2:
                render_library_tab()

if __name__ == "__main__":
    main()
