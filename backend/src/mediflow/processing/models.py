"""Inspectable evidence, conservative outcomes, and hard upper resource limits."""

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


def normalize_quote(text: str) -> str:
    """Only trim/collapse Unicode whitespace; preserve all printed characters."""
    return " ".join(text.split())


class Limits(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    max_bytes: int = Field(default=10_000_000, gt=0, le=10_000_000)
    max_pages: int = Field(default=10, gt=0, le=10)
    dpi: int = Field(default=150, ge=72, le=150)
    max_pixels: int = Field(default=4_000_000, ge=1000, le=4_000_000)
    deadline_seconds: float = Field(default=240, gt=0, le=240)
    ocr_seconds: float = Field(default=30, gt=0, le=30)
    max_page_characters: int = Field(default=100_000, gt=0, le=100_000)
    memory_bytes: int = Field(default=805_306_368, ge=134_217_728, le=805_306_368)


class PageText(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    page_number: int
    origin: Literal["native", "ocr"]
    original_text: str
    native_text: str
    native_adequate: bool
    alphabetic_characters: int
    printable_ratio: float
    flags: tuple[str, ...] = ()
    trust: Literal["untrusted_document_data"] = "untrusted_document_data"

    @property
    def normalized_text(self) -> str:
        return normalize_quote(self.original_text)

    def supports_quote(self, quote: str) -> bool:
        normalized = normalize_quote(quote)
        return bool(normalized) and normalized in self.normalized_text


class ProcessingResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    outcome: Literal["succeeded", "rejected", "failed"]
    reason: str | None = None
    category: Literal["laboratory", "unsupported", "uncertain"] = "uncertain"
    pages: tuple[PageText, ...] = ()
    source_sha256: str
    elapsed_seconds: float = 0
    peak_rss_bytes: int | None = None
    cpu_seconds: float | None = None
    normalization: Literal["unicode_whitespace_only_v1"] = "unicode_whitespace_only_v1"
    classification_method: Literal["conservative_english_rules_v1"] = (
        "conservative_english_rules_v1"
    )


def rejected(source: bytes, reason: str, *, failed: bool = False) -> ProcessingResult:
    return ProcessingResult(
        outcome="failed" if failed else "rejected",
        reason=reason,
        source_sha256=hashlib.sha256(source).hexdigest(),
    )
