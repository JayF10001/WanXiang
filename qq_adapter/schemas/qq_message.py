from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParsedMessage:
    command: str
    text: str
    raw_text: str
