#!/usr/bin/env python
"""
Kimi Book Writer Web UI
-----------------------
A Streamlit-based web interface for generating, managing, and reading novels.
"""
import streamlit as st
import os
import json
import shutil
import subprocess
import re
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# Import from existing modules
from kimi_writer import (
    get_client,
    chat_complete_stream,
    build_book_markdown,
    SYSTEM_PRIMER,
    OUTLINE_PROMPT,
    CHAPTER_PROMPT,
    env
)
from utils import extract_outline_items

# Configure logging for server-side error tracking
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

# Constants
PREVIEW_DIR = Path("preview")
PUBLISHED_DIR = Path("published")
PREVIEW_DIR.mkdir(exist_ok=True)
PUBLISHED_DIR.mkdir(exist_ok=True)

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
def get_novel_slug(title: str) -> str:
    """Convert novel title to filesystem-safe slug."""
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')

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

def init_novel_state(title: str, concept: str) -> Dict:
    """Initialize a new novel state."""
    return {
        "title": title,
        "concept": concept,
        "model": env("KIMI_MODEL", "kimi-k2-thinking-turbo"),
        "temperature": float(env("KIMI_TEMPERATURE", "0.6")),
        "max_output_tokens": int(env("KIMI_MAX_OUTPUT_TOKENS", "4096")),
        "outline_text": None,
        "chapters": [],
        "outline_items": [],
        "current_idx": 0,
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
    published_state = PUBLISHED_DIR / f"{slug}_state.json"
    published_md = PUBLISHED_DIR / f"{slug}.md"

    if not preview_state.exists() or not preview_md.exists():
        raise FileNotFoundError("Preview files not found")

    shutil.copy2(preview_state, published_state)
    shutil.copy2(preview_md, published_md)

    # Git commit
    try:
        # Add files to staging
        subprocess.run(
            ["git", "add", str(published_md), str(published_state)],
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
            return True

        # Commit the changes
        subprocess.run(
            ["git", "commit", "-m", f"Publish novel: {title}"],
            check=True,
            capture_output=True,
            text=True
        )
        logger.info(f"Successfully published and committed novel: {title}")
        return True

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode() if e.stderr else str(e)
        logger.error(f"Git operation failed for novel '{title}': {error_msg}", exc_info=True)
        st.error(f"Failed to commit to git. Please ensure git is configured properly.")
        return False
    except Exception as e:
        logger.error(f"Unexpected error publishing novel '{title}': {e}", exc_info=True)
        st.error(f"Unexpected error during publish: {str(e)}")
        return False

def delete_novel(title: str, preview: bool = True):
    """Delete a novel's files."""
    state_path = get_novel_state_path(title, preview)
    md_path = get_novel_md_path(title, preview)

    if state_path.exists():
        state_path.unlink()
    if md_path.exists():
        md_path.unlink()

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
        # Mode selection
        mode = st.radio(
            "Mode",
            ["New Novel", "Continue Existing"],
            horizontal=True
        )

        if mode == "New Novel":
            with st.form("new_novel_form"):
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
                    temperature = st.slider("Temperature", min_value=0.0, max_value=1.0, value=0.6, step=0.1)

                submitted = st.form_submit_button("Start Generation", use_container_width=True)

                if submitted:
                    if not title or not concept:
                        st.error("Please provide both title and concept.")
                    else:
                        # Check if novel already exists
                        existing = get_novel_state_path(title, preview=True)
                        if existing.exists():
                            st.error(f"A novel with title '{title}' already exists in preview. Please choose a different title or continue the existing one.")
                        else:
                            generate_novel(title, concept, max_chapters, temperature)

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

                    if novel['chapters_written'] >= novel['total_chapters']:
                        st.success("✅ This novel is complete!")

                    if st.button("Continue Generation", use_container_width=True):
                        continue_novel(novel)

    with col2:
        st.markdown("### 💡 Tips")
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

def generate_novel(title: str, concept: str, max_chapters: int, temperature: float):
    """Generate a new novel from scratch."""
    try:
        # Initialize state
        state = init_novel_state(title, concept)
        state["temperature"] = temperature

        # Get client
        client = get_client()
        model = state["model"]
        max_tokens = state["max_output_tokens"]

        # Generate outline
        st.markdown("---")
        st.markdown("### 📋 Generating Outline...")

        with st.spinner("Creating outline..."):
            messages = [
                {"role": "system", "content": SYSTEM_PRIMER},
                {"role": "user", "content": f"{OUTLINE_PROMPT}\n\nConcept: {concept}"}
            ]
            stream = chat_complete_stream(client, model, messages, temperature, max_tokens)

            # Collect outline
            outline_chunks = []
            outline_placeholder = st.empty()
            for chunk in stream:
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    outline_chunks.append(delta.content)
                    outline_placeholder.markdown("".join(outline_chunks))

            outline = "".join(outline_chunks).strip()
            state["outline_text"] = outline
            state["outline_items"] = extract_outline_items(outline)[:max_chapters]

            save_novel_state(title, state, preview=True)

        st.success(f"✅ Outline created with {len(state['outline_items'])} chapters!")

        # Generate chapters
        st.markdown("### ✍️ Writing Chapters...")
        progress_bar = st.progress(0)
        status_text = st.empty()
        chapter_display = st.empty()

        total_chapters = len(state["outline_items"])

        for idx in range(total_chapters):
            chapter_title = state["outline_items"][idx]
            status_text.text(f"Writing Chapter {idx + 1}/{total_chapters}: {chapter_title}")

            # Build context (only include if there are previous chapters)
            user_content = f"Novel concept:\n{concept}\n\n"
            if state["chapters"]:
                context_snippets = "\n\n".join(
                    ch.get("content", "")[-2000:] for ch in state["chapters"][-3:]
                )
                user_content += f"Existing recent context (last chapters excerpts):\n{context_snippets}\n\n"
            user_content += CHAPTER_PROMPT.format(idx=idx+1, title=chapter_title)

            messages = [
                {"role": "system", "content": SYSTEM_PRIMER},
                {"role": "user", "content": user_content}
            ]

            stream = chat_complete_stream(client, model, messages, temperature, max_tokens)

            # Collect chapter
            chapter_chunks = []
            for chunk in stream:
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    chapter_chunks.append(delta.content)

            chapter_md = "".join(chapter_chunks).strip()
            if not chapter_md.lstrip().startswith("##"):
                chapter_md = f"## Chapter {idx+1}: {chapter_title}\n\n" + chapter_md

            state["chapters"].append({"title": chapter_title, "content": chapter_md})
            state["current_idx"] = idx + 1

            # Save state and markdown
            save_novel_state(title, state, preview=True)
            md_path = get_novel_md_path(title, preview=True)
            md_path.write_text(build_book_markdown(state), encoding="utf-8")

            # Update progress
            progress_bar.progress((idx + 1) / total_chapters)
            chapter_display.markdown(f"**Latest:** {chapter_title}")

        st.success(f"🎉 Novel complete! {total_chapters} chapters written.")
        st.balloons()

    except Exception as e:
        # Log full traceback server-side
        logger.error(f"Error during novel generation: {e}", exc_info=True)
        # Display user-friendly error message
        st.error(f"❌ Error during generation: {str(e)}")
        st.info("The error has been logged. Please check your API key and try again.")

def continue_novel(novel: Dict):
    """Continue generating an incomplete novel."""
    try:
        state = novel["state"]
        title = state["title"]

        if state["current_idx"] >= len(state["outline_items"]):
            st.info("This novel is already complete!")
            return

        client = get_client()
        model = state["model"]
        temperature = state["temperature"]
        max_tokens = state["max_output_tokens"]

        st.markdown("---")
        st.markdown("### ✍️ Continuing Novel...")

        progress_bar = st.progress(state["current_idx"] / len(state["outline_items"]))
        status_text = st.empty()
        chapter_display = st.empty()

        total_chapters = len(state["outline_items"])

        for idx in range(state["current_idx"], total_chapters):
            chapter_title = state["outline_items"][idx]
            status_text.text(f"Writing Chapter {idx + 1}/{total_chapters}: {chapter_title}")

            # Build context (only include if there are previous chapters)
            user_content = f"Novel concept:\n{state['concept']}\n\n"
            if state["chapters"]:
                context_snippets = "\n\n".join(
                    ch.get("content", "")[-2000:] for ch in state["chapters"][-3:]
                )
                user_content += f"Existing recent context (last chapters excerpts):\n{context_snippets}\n\n"
            user_content += CHAPTER_PROMPT.format(idx=idx+1, title=chapter_title)

            messages = [
                {"role": "system", "content": SYSTEM_PRIMER},
                {"role": "user", "content": user_content}
            ]

            stream = chat_complete_stream(client, model, messages, temperature, max_tokens)

            chapter_chunks = []
            for chunk in stream:
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    chapter_chunks.append(delta.content)

            chapter_md = "".join(chapter_chunks).strip()
            if not chapter_md.lstrip().startswith("##"):
                chapter_md = f"## Chapter {idx+1}: {chapter_title}\n\n" + chapter_md

            state["chapters"].append({"title": chapter_title, "content": chapter_md})
            state["current_idx"] = idx + 1

            save_novel_state(title, state, preview=True)
            md_path = get_novel_md_path(title, preview=True)
            md_path.write_text(build_book_markdown(state), encoding="utf-8")

            progress_bar.progress((idx + 1) / total_chapters)
            chapter_display.markdown(f"**Latest:** {chapter_title}")

        st.success(f"🎉 Novel complete! {total_chapters} chapters written.")
        st.balloons()

    except Exception as e:
        # Log full traceback server-side
        logger.error(f"Error continuing novel: {e}", exc_info=True)
        # Display user-friendly error message
        st.error(f"❌ Error continuing novel: {str(e)}")
        st.info("The error has been logged. Please check your API key and try again.")

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
                if st.button("📖 Read", key=f"read_{novel['slug']}_{preview}"):
                    st.session_state.reading_novel = novel
                    st.session_state.reading_preview = preview
                    st.rerun()

                if novel['exists']:
                    with open(novel['md_path'], 'r') as f:
                        st.download_button(
                            "⬇️ Download",
                            f.read(),
                            file_name=f"{novel['slug']}.md",
                            mime="text/markdown",
                            key=f"download_{novel['slug']}_{preview}"
                        )

            with col3:
                if preview:
                    if novel['chapters_written'] >= novel['total_chapters']:
                        if st.button("✅ Publish", key=f"publish_{novel['slug']}"):
                            with st.spinner("Publishing..."):
                                if publish_novel(novel['title']):
                                    st.success("Published successfully!")
                                    st.rerun()
                    else:
                        st.caption("⏳ Incomplete")

                if st.button("🗑️ Delete", key=f"delete_{novel['slug']}_{preview}"):
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
            st.rerun()

    # Load full content
    md_path = get_novel_md_path(novel['title'], preview)
    if not md_path.exists():
        st.error("Novel file not found!")
        return

    content = md_path.read_text()

    # Extract chapters
    state = novel['state']
    chapters = state.get('chapters', [])

    if not chapters:
        st.warning("No chapters available.")
        return

    # Chapter navigation
    st.markdown('<div class="chapter-nav">', unsafe_allow_html=True)
    chapter_titles = [f"Ch {i+1}: {ch['title']}" for i, ch in enumerate(chapters)]

    # Initialize or get selected chapter from session state
    if 'selected_chapter' not in st.session_state:
        st.session_state.selected_chapter = 0

    selected_chapter = st.selectbox(
        "Jump to chapter:",
        range(len(chapters)),
        index=st.session_state.selected_chapter,
        format_func=lambda x: chapter_titles[x],
        key="chapter_selector"
    )

    # Update session state when selectbox changes
    if selected_chapter != st.session_state.selected_chapter:
        st.session_state.selected_chapter = selected_chapter

    st.markdown('</div>', unsafe_allow_html=True)

    # Display selected chapter
    chapter = chapters[selected_chapter]
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

# Main app
def main():
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
        st.markdown("### Stats")
        preview_novels, _ = list_novels(preview=True)
        published_novels, _ = list_novels(preview=False)
        st.metric("Preview Novels", len(preview_novels))
        st.metric("Published Novels", len(published_novels))

        st.markdown("---")
        st.markdown("### About")
        st.markdown("Powered by Moonshot AI's Kimi K2 models")
        st.markdown("[Documentation](https://github.com/yourusername/kimi-book-writer)")

    # Main content
    if 'reading_novel' in st.session_state:
        render_reader()
    else:
        tab1, tab2 = st.tabs(["📝 Generate", "📚 Library"])

        with tab1:
            render_generate_tab()

        with tab2:
            render_library_tab()

if __name__ == "__main__":
    main()
