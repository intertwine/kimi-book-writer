from __future__ import annotations
import os
import re
from pathlib import Path
from typing import List

# Constants for prompt truncation limits
CONCEPT_EXCERPT_MAX_CHARS = 800
CHAPTER_EXCERPT_MAX_CHARS = 600

# Valid FLUX model identifiers
VALID_FLUX_MODELS = {
    "black-forest-labs/flux.2-klein-4b",
    "black-forest-labs/flux.2-max",
    "black-forest-labs/flux.2-pro",
    "black-forest-labs/flux.2-flex",
}


def get_novel_slug(title: str) -> str:
    """Convert novel title to filesystem-safe slug."""
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug.strip('-')


def validate_image_path(path_str: str, allowed_dir: Path) -> bool:
    """
    Validate that an image path is safe to use.
    Returns True if path is valid and within allowed directory.
    """
    if not path_str:
        return False
    try:
        path = Path(path_str)
        resolved = path.resolve()
        allowed_resolved = allowed_dir.resolve()
        # Check path is within allowed directory (or is the directory itself)
        if not (resolved == allowed_resolved or str(resolved).startswith(str(allowed_resolved) + os.sep)):
            return False
        # Check extension is valid image type
        valid_extensions = {'.png', '.jpg', '.jpeg', '.webp', '.gif'}
        if path.suffix.lower() not in valid_extensions:
            return False
        return True
    except (ValueError, OSError):
        return False


def validate_flux_model(model: str) -> str:
    """
    Validate and normalize a FLUX model identifier.
    Returns the model if valid, raises ValueError if invalid.
    """
    if not model:
        return None
    if model in VALID_FLUX_MODELS:
        return model
    # Check if it's a partial match (user might omit prefix)
    for valid_model in VALID_FLUX_MODELS:
        if valid_model.endswith(model):
            return valid_model
    raise ValueError(
        f"Invalid FLUX model '{model}'. Valid models: {', '.join(sorted(VALID_FLUX_MODELS))}"
    )


def extract_outline_items(text: str) -> List[str]:
    """
    Extract chapter titles from a model-generated outline.
    Accepts numbered lists, markdown headings, or bullet lists.
    """
    items = []
    for line in text.splitlines():
        line=line.strip()
        if not line:
            continue
        if re.match(r'^(\d+\.\s+|\-\s+|\*\s+|#{1,6}\s+|Chapter\s*\d+)', line, flags=re.I):
            core = re.sub(r'^(\d+\.\s+|\-\s+|\*\s+|#{1,6}\s+|Chapter\s*\d+\s*)', '', line, flags=re.I).strip()
            core = re.sub(r'^(?:Chapter\s*\d+\s*[:\-–]\s*)', '', core, flags=re.I).strip()
            # Remove any leftover leading punctuation (colon, dash, etc.) after removing Chapter prefix
            core = re.sub(r'^[:\-–]\s*', '', core).strip()
            # Remove long dashes and summaries after an em dash
            core = core.split('—')[0].split('--')[0].strip()
            if core:
                items.append(core)
    if not items:
        paras = [p.strip() for p in text.split("\n\n") if p.strip()]
        items = paras
    seen=set()
    uniq=[]
    for it in items:
        key=it.lower()
        if key not in seen:
            uniq.append(it)
            seen.add(key)
    return uniq[:100]
