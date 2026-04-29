from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

from .config import AppConfig


FILLER_PATTERNS = [
    r"\bum+\b",
    r"\buh+\b",
    r"\berm+\b",
    r"\bhm+\b",
    r"\bhmm+\b",
    r"\byou know\b",
    r"\bi mean\b",
]


def apply_spoken_corrections(text: str) -> str:
    corrected = text.strip()
    corrected = _apply_reset_commands(corrected)
    corrected = _apply_delete_last_sentence(corrected)
    corrected = _apply_delete_last_word(corrected)
    corrected = _apply_inline_replacements(corrected)
    return _collapse_spaces(corrected)


def deterministic_cleanup(text: str) -> str:
    corrected = apply_spoken_corrections(text)
    cleaned = f" {corrected.strip()} "
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = _collapse_spaces(cleaned)
    cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
    cleaned = cleaned.strip()
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def polished_cleanup(text: str, config: AppConfig) -> str:
    base = deterministic_cleanup(text)
    if config.cleanup_mode != "polished" or not config.ollama_enabled:
        return base
    try:
        polished = _ollama_cleanup(base, config)
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return base
    return polished or base


def _ollama_cleanup(text: str, config: AppConfig) -> str:
    prompt = (
        "Clean this dictated text for direct insertion into a text field.\n"
        "Apply spoken correction commands such as scratch that, start over, delete last word, delete last sentence, actually, sorry, no, not, rather, and I mean.\n"
        "Treat phrases like 'John sorry Sarah', 'John no Sarah', and 'John not Sarah' as replacing John with Sarah.\n"
        "Remove filler words, repeated words, and false starts.\n"
        "Add punctuation and capitalization.\n"
        "Preserve the intended meaning. Do not summarize, expand, or invent details.\n"
        "Return only the cleaned text.\n\n"
        f"Text: {text}"
    )
    payload = {
        "model": config.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 160,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        config.ollama_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=config.ollama_timeout_s) as response:
        raw = response.read().decode("utf-8")
    result = json.loads(raw)
    return str(result.get("response", "")).strip().strip('"')


def _apply_reset_commands(text: str) -> str:
    parts = re.split(r"\b(?:scratch that|start over)\b", text, flags=re.IGNORECASE)
    return parts[-1].strip() if len(parts) > 1 else text


def _apply_delete_last_sentence(text: str) -> str:
    pattern = re.compile(r"\bdelete last sentence\b", flags=re.IGNORECASE)
    while True:
        match = pattern.search(text)
        if not match:
            return text
        before = text[: match.start()].rstrip()
        after = text[match.end() :].lstrip()
        before = re.sub(r"[^.!?]*[.!?]?\s*$", "", before).rstrip()
        text = f"{before} {after}".strip()


def _apply_delete_last_word(text: str) -> str:
    pattern = re.compile(r"\bdelete last word\b", flags=re.IGNORECASE)
    while True:
        match = pattern.search(text)
        if not match:
            return text
        before = text[: match.start()].rstrip()
        after = text[match.end() :].lstrip()
        before = re.sub(r"\S+\s*$", "", before).rstrip()
        text = f"{before} {after}".strip()


def _apply_inline_replacements(text: str) -> str:
    text = re.sub(
        r"\b(?P<old>\w+)\s+(?:no not|i mean|actually|sorry|rather|no|not)\s+(?P<new>\w+)\b",
        lambda match: match.group("new"),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\b(?P<old>\w+(?:\s+\w+){0,2})\s+(?:no not|i mean|actually|sorry|rather|no|not)\s+(?P<new>\w+(?:\s+\w+){0,2})(?=$|[,.!?;:])",
        lambda match: match.group("new"),
        text,
        flags=re.IGNORECASE,
    )
    return text


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
