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


def deterministic_cleanup(text: str) -> str:
    cleaned = f" {text.strip()} "
    for pattern in FILLER_PATTERNS:
        cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned)
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
        "Remove filler words, repeated words, and false starts.\n"
        "Add punctuation and capitalization.\n"
        "Preserve the original meaning. Do not summarize.\n"
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

