from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MemoryNoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=1, max_length=400)
    kind: Literal["intention", "preference", "decision"]
    source_date: date
    source_excerpt: str = Field(default="", max_length=1000)
    cues: list[str] = Field(default_factory=list, max_length=8)
    status: Literal["active", "completed", "abandoned"] = "active"

    @field_validator("cues")
    @classmethod
    def valid_cues(cls, values):
        if any(not v.strip() or len(v) > 50 for v in values):
            raise ValueError("Cues must contain 1–50 characters.")
        return sorted(set(v.strip().casefold() for v in values))
