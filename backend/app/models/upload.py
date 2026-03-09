"""Pydantic models for upload requests and responses."""

from pydantic import BaseModel


class UploadResult(BaseModel):
    id: str
    file_name: str
    thumbnail_url: str
    original_url: str
    caption: str
    tags: list[str]
    objects: list[str]


class UploadResponse(BaseModel):
    status: str
    count: int
    results: list[UploadResult]
