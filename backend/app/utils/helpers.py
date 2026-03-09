"""Utility helpers — ID generation, text building."""

import uuid
import re


def generate_id() -> str:
    """Generate a URL-safe unique ID."""
    return uuid.uuid4().hex


def build_text_representation(
    caption: str,
    tags: list[str],
    objects: list[str] | None = None,
    details: str = "",
) -> str:
    """Build the text string that will be embedded by OpenAI.

    Combines caption, tags, objects, and the free-form details paragraph
    produced by GPT-4.1 Vision.  The richer this text is, the better the
    semantic search quality.
    """
    parts = []
    if caption:
        parts.append(caption)
    if details:
        parts.append(details)
    tag_str = ", ".join(tags) if tags else ""
    if tag_str:
        parts.append(f"Tags: {tag_str}")
    obj_str = ", ".join(objects) if objects else ""
    if obj_str:
        parts.append(f"Objects: {obj_str}")
    return ". ".join(parts) if parts else ""


def sanitize_filename(name: str) -> str:
    """Remove problematic characters from filenames."""
    return re.sub(r'[^\w\-.]', '_', name)
