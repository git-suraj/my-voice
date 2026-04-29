from __future__ import annotations

import re

from .transcriber import TranscriptChunk


def assemble_chunks(chunks: list[TranscriptChunk]) -> str:
    ordered = sorted(chunks, key=lambda item: item.id)
    output: list[str] = []
    for chunk in ordered:
        words = chunk.text.strip().split()
        if not words:
            continue
        if not output:
            output.extend(words)
            continue
        overlap = _overlap_len(output, words, max_words=8)
        output.extend(words[overlap:])
    return " ".join(output)


def reconcile_text(text: str) -> str:
    text = _collapse_whitespace(text)
    text = _apply_self_corrections(text)
    return text.strip()


def _overlap_len(left: list[str], right: list[str], max_words: int) -> int:
    limit = min(len(left), len(right), max_words)
    left_norm = [_normalize_word(word) for word in left]
    right_norm = [_normalize_word(word) for word in right]
    for size in range(limit, 0, -1):
        if left_norm[-size:] == right_norm[:size]:
            return size
    return 0


def _normalize_word(word: str) -> str:
    return re.sub(r"[^a-z0-9']", "", word.lower())


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _apply_self_corrections(text: str) -> str:
    patterns = [
        r"\b(?P<old>[A-Z][a-z]+)\s+(?:no|actually|rather)\s+(?P<new>[A-Z][a-z]+)\b",
        r"\b(?P<old>\w+)\s+(?:no actually|actually|rather)\s+(?P<new>\w+)\b",
    ]
    for pattern in patterns:
        text = re.sub(pattern, lambda match: match.group("new"), text, flags=re.IGNORECASE)
    text = re.sub(r"\bno,\s*", "", text, flags=re.IGNORECASE)
    return text

