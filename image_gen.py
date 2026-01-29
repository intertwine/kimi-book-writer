#!/usr/bin/env python
"""
Image Generation Module
-----------------------
Generate cover and chapter illustrations using FLUX.2 models via OpenRouter API.
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_FLUX_MODEL = "black-forest-labs/flux.2-klein-4b"


def is_image_generation_enabled() -> bool:
    """Check if OpenRouter API key is configured for image generation."""
    return bool(os.getenv("OPENROUTER_API_KEY"))


def get_flux_model() -> str:
    """Get configured FLUX model or default."""
    return os.getenv("FLUX_MODEL", DEFAULT_FLUX_MODEL)


def get_openrouter_client():
    """Create OpenAI client configured for OpenRouter."""
    from openai import OpenAI

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    return OpenAI(
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://github.com/intertwine/kimi-book-writer",
            "X-Title": "Kimi Book Writer"
        }
    )


@retry(wait=wait_exponential(multiplier=2, min=2, max=60), stop=stop_after_attempt(3))
def generate_image(prompt: str, model: Optional[str] = None) -> Tuple[bytes, str]:
    """
    Generate an image using FLUX.2 via OpenRouter.

    Args:
        prompt: Text description of the image to generate
        model: Optional model override (defaults to FLUX_MODEL env var)

    Returns:
        Tuple of (image_bytes, file_extension)

    Raises:
        ValueError: If OpenRouter API key not configured
        RuntimeError: If image generation fails
    """
    client = get_openrouter_client()
    model = model or get_flux_model()

    logger.info(f"Generating image with model {model}")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        extra_body={"modalities": ["image", "text"]}
    )

    # Extract image from response
    content = response.choices[0].message.content

    # Handle different response formats
    if hasattr(response.choices[0].message, 'images') and response.choices[0].message.images:
        # Response has images array
        images = response.choices[0].message.images
        if images:
            image_data = images[0]
            if isinstance(image_data, dict) and 'image_url' in image_data:
                data_url = image_data['image_url'].get('url', '')
            elif isinstance(image_data, str):
                data_url = image_data
            else:
                raise RuntimeError(f"Unexpected image format: {type(image_data)}")
        else:
            raise RuntimeError("No images in response")
    elif isinstance(content, list):
        # Content is array of parts
        data_url = None
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "image_url":
                    data_url = part.get("image_url", {}).get("url", "")
                    break
                elif part.get("type") == "image":
                    # Some APIs return type: "image" with base64 data
                    b64_data = part.get("data", part.get("image", ""))
                    mime_type = part.get("mime_type", "image/png")
                    ext = mime_type.split("/")[1] if "/" in mime_type else "png"
                    return base64.b64decode(b64_data), ext
        if not data_url:
            raise RuntimeError(f"No image found in response content: {content[:200] if content else 'empty'}")
    elif isinstance(content, str) and content.startswith("data:image"):
        # Content is a data URL
        data_url = content
    else:
        raise RuntimeError(f"Unexpected response format: {type(content)}")

    # Parse data URL: "data:image/png;base64,iVBORw0KGgo..."
    if not data_url or not data_url.startswith("data:image"):
        raise RuntimeError(f"Invalid data URL: {data_url[:100] if data_url else 'None'}")

    header, b64_data = data_url.split(",", 1)
    mime_type = header.split(";")[0].split(":")[1]  # "image/png"
    ext = mime_type.split("/")[1]  # "png"
    image_bytes = base64.b64decode(b64_data)

    logger.info(f"Generated image: {len(image_bytes)} bytes, format: {ext}")
    return image_bytes, ext


def generate_cover_prompt(title: str, concept: str) -> str:
    """Generate a prompt for the novel's cover image."""
    # Truncate concept if too long
    concept_excerpt = concept[:800] if len(concept) > 800 else concept

    return f"""Create a book cover illustration for a novel.

Title: "{title}"
Story concept: {concept_excerpt}

Requirements:
- Professional book cover art style
- Evocative and atmospheric composition
- NO text, titles, or words on the image
- High quality, detailed artwork
- Genre-appropriate aesthetic that captures the story's mood
- Suitable as a novel cover illustration"""


def generate_chapter_prompt(novel_title: str, chapter_title: str, chapter_excerpt: str) -> str:
    """Generate a prompt for a chapter illustration."""
    # Truncate excerpt if too long
    excerpt = chapter_excerpt[:600] if len(chapter_excerpt) > 600 else chapter_excerpt

    return f"""Create an illustration for a chapter of a novel.

Novel: "{novel_title}"
Chapter: "{chapter_title}"
Scene excerpt: {excerpt}

Requirements:
- Single scene illustration capturing the chapter's essence
- Atmospheric and evocative style
- NO text or words on the image
- Captures the mood and setting of the scene
- Suitable as a chapter header illustration"""


def save_image(image_bytes: bytes, path: Path) -> None:
    """Save image bytes to disk, creating parent directories if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image_bytes)
    logger.info(f"Saved image to {path}")
