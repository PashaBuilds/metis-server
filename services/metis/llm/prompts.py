"""Versiyonlu prompt dosyaları (llm/prompts/<id>.md). Prompt kimliği = dosya adı; hash yeterlilik fingerprint'ine girer."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


@dataclass(frozen=True)
class Prompt:
    id: str
    text: str
    sha256: str

    @property
    def version(self) -> str:
        return self.id


@lru_cache(maxsize=32)
def load(prompt_id: str) -> Prompt:
    path = PROMPT_DIR / f"{prompt_id}.md"
    if not path.is_file() or path.parent != PROMPT_DIR:
        raise KeyError(prompt_id)
    text = path.read_text(encoding="utf-8").strip()
    return Prompt(id=prompt_id, text=text, sha256=hashlib.sha256(text.encode()).hexdigest())


EVIDENCE = "evidence-explain-v1"
SOURCE_SELECTION = "mentor-source-selection-v1"
EXTRACT = "extract-claims-v2"
PAGE_DIFF = "page-diff-v5"
CLAIM_CONFLICT = "claim-conflict-v3"
RELATION = "relation-v3"
REFINE = "draft-refinement-v2"
CONFLICT_RESOLUTION = "conflict-resolution-v1"
