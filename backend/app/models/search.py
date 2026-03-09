"""Pydantic models for search requests and responses."""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal


class SearchRequest(BaseModel):
    text_query: str | None = None
    strategy: Literal["vision", "openai", "compare"] = "vision"
    filters: dict[str, list[str]] | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class SearchResultItem(BaseModel):
    id: str
    file_name: str
    thumbnail_url: str
    original_url: str
    caption: str
    tags: list[str]
    objects: list[str]
    description: str | None = None
    relevance: float
    file_size: int
    width: int | None = None
    height: int | None = None
    upload_date: str | None = None
    content_type: str | None = None


class FacetValue(BaseModel):
    value: str
    count: int


class SearchResultSet(BaseModel):
    strategy: str
    total_count: int
    results: list[SearchResultItem]
    facets: dict[str, list[FacetValue]]


class SearchResponse(BaseModel):
    """Wraps one or two result sets (for compare mode)."""
    mode: Literal["single", "compare"]
    vision: SearchResultSet | None = None
    openai: SearchResultSet | None = None
