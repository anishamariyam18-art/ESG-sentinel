"""Shared provenance primitives used across module contracts.

Kept separate from any single module's contract file (analyzer, claims, ...)
so multiple modules can reference the same shape without importing from
each other's "leaf" model files.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class SourceReference(BaseModel):
    chunk_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    section: str | None = None
