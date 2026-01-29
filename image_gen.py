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

import httpx
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from utils import CONCEPT_EXCERPT_MAX_CHARS, CHAPTER_EXCERPT_MAX_CHARS

logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_FLUX_MODEL = "black-forest-labs/flux.2-klein-4b"
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpeg", "jpg", "webp", "gif"}
# Timeout is configurable for slower models like FLUX.2-max (default 180s)
DEFAULT_IMAGE_TIMEOUT = int(os.getenv("IMAGE_GENERATION_TIMEOUT", "180"))


def is_image_generation_enabled() -> bool:
    """Check if OpenRouter API key is configured for image generation."""
    return bool(os.getenv("OPENROUTER_API_KEY"))


def get_flux_model() -> str:
    """Get configured FLUX model or default."""
    return os.getenv("FLUX_MODEL", DEFAULT_FLUX_MODEL)


@retry(wait=wait_exponential(multiplier=2, min=2, max=60), stop=stop_after_attempt(3))
def generate_image(prompt: str, model: Optional[str] = None) -> Tuple[bytes, str]:
    """
    Generate an image using FLUX via OpenRouter.

    Args:
        prompt: Text description of the image to generate
        model: Optional model override (defaults to FLUX_MODEL env var)

    Returns:
        Tuple of (image_bytes, file_extension)

    Raises:
        ValueError: If OpenRouter API key not configured
        RuntimeError: If image generation fails
    """
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not configured")

    model = model or get_flux_model()
    logger.info(f"Generating image with model {model}")

    # Use httpx directly to have full control over the request format
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/intertwine/kimi-book-writer",
        "X-Title": "Kimi Book Writer"
    }

    # FLUX.2 models output image only, not image+text
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "modalities": ["image"]
    }

    with httpx.Client(timeout=float(DEFAULT_IMAGE_TIMEOUT)) as client:
        response = client.post(
            f"{OPENROUTER_BASE_URL}/chat/completions",
            headers=headers,
            json=payload
        )

        if response.status_code != 200:
            error_text = response.text[:500] if response.text else "No error message"
            # Provide helpful guidance for common errors
            if response.status_code == 401:
                raise ValueError(
                    "Invalid OPENROUTER_API_KEY. Check your API key at https://openrouter.ai/keys"
                )
            elif response.status_code == 429:
                raise RuntimeError(
                    "Rate limited by OpenRouter. Please wait and try again."
                )
            elif response.status_code == 402:
                raise RuntimeError(
                    "Insufficient credits on OpenRouter. Add credits at https://openrouter.ai/credits"
                )
            raise RuntimeError(f"OpenRouter API error {response.status_code}: {error_text}")

        data = response.json()

    # Extract image from response
    choices = data.get("choices", [])
    if not choices:
        raise RuntimeError("No choices in response")

    message = choices[0].get("message", {})
    content = message.get("content")

    # Handle different response formats
    # Format 1: images array in message
    if "images" in message and message["images"]:
        images = message["images"]
        image_data = images[0]
        if isinstance(image_data, dict) and "image_url" in image_data:
            data_url = image_data["image_url"].get("url", "")
        elif isinstance(image_data, str):
            data_url = image_data
        else:
            raise RuntimeError(f"Unexpected image format: {type(image_data)}")
    # Format 2: content is array of parts
    elif isinstance(content, list):
        data_url = None
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "image_url":
                    data_url = part.get("image_url", {}).get("url", "")
                    break
                elif part.get("type") == "image":
                    b64_data = part.get("data", part.get("image", ""))
                    mime_type = part.get("mime_type", "image/png")
                    ext = mime_type.split("/")[1] if "/" in mime_type else "png"
                    return base64.b64decode(b64_data), ext
        if not data_url:
            raise RuntimeError(f"No image found in response content: {str(content)[:200]}")
    # Format 3: content is a data URL string
    elif isinstance(content, str) and content.startswith("data:image"):
        data_url = content
    else:
        raise RuntimeError(f"Unexpected response format. Content type: {type(content)}, keys: {list(message.keys())}")

    # Parse data URL: "data:image/png;base64,iVBORw0KGgo..."
    if not data_url or not data_url.startswith("data:image"):
        raise RuntimeError(f"Invalid data URL: {data_url[:100] if data_url else 'None'}")

    # Defensive parsing with validation
    if "," not in data_url:
        raise RuntimeError("Malformed data URL: missing comma separator")

    header, b64_data = data_url.split(",", 1)

    # Extract MIME type with validation
    if ":" not in header or "/" not in header:
        raise RuntimeError(f"Malformed data URL header: {header[:50]}")

    mime_part = header.split(";")[0]  # "data:image/png"
    mime_type = mime_part.split(":")[1] if ":" in mime_part else "image/png"
    ext = mime_type.split("/")[1] if "/" in mime_type else "png"

    # Validate extension against allowlist
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        logger.warning(f"Unexpected image extension '{ext}', defaulting to 'png'")
        ext = "png"

    # Decode base64 with error handling
    try:
        image_bytes = base64.b64decode(b64_data)
    except Exception as e:
        raise RuntimeError(f"Failed to decode base64 image data: {e}")

    logger.info(f"Generated image: {len(image_bytes)} bytes, format: {ext}")
    return image_bytes, ext


def generate_cover_prompt(title: str, concept: str) -> str:
    """Generate a prompt for the novel's cover image."""
    # Truncate concept if too long
    concept_excerpt = concept[:CONCEPT_EXCERPT_MAX_CHARS] if len(concept) > CONCEPT_EXCERPT_MAX_CHARS else concept

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
    excerpt = chapter_excerpt[:CHAPTER_EXCERPT_MAX_CHARS] if len(chapter_excerpt) > CHAPTER_EXCERPT_MAX_CHARS else chapter_excerpt

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
