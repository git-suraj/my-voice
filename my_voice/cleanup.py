from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
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


@dataclass(frozen=True)
class CleanupResult:
    text: str
    deterministic_ms: float
    llm_ms: float
    total_ms: float
    used_llm: bool
    llm_error: str = ""


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
    return cleanup_with_metrics(text, config).text


def cleanup_with_metrics(text: str, config: AppConfig) -> CleanupResult:
    total_started = time.perf_counter()
    deterministic_started = time.perf_counter()
    base = deterministic_cleanup(text)
    deterministic_ms = (time.perf_counter() - deterministic_started) * 1000
    if config.cleanup_mode != "polished" or not config.ollama_enabled:
        total_ms = (time.perf_counter() - total_started) * 1000
        return CleanupResult(base, deterministic_ms, 0.0, total_ms, False)

    llm_started = time.perf_counter()
    try:
        polished = _ollama_cleanup(raw_text=text, draft_text=base, config=config)
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
        llm_ms = (time.perf_counter() - llm_started) * 1000
        total_ms = (time.perf_counter() - total_started) * 1000
        return CleanupResult(base, deterministic_ms, llm_ms, total_ms, False, repr(exc))

    llm_ms = (time.perf_counter() - llm_started) * 1000
    total_ms = (time.perf_counter() - total_started) * 1000
    final_text = polished or base
    return CleanupResult(final_text, deterministic_ms, llm_ms, total_ms, bool(polished))


def _ollama_cleanup(raw_text: str, draft_text: str, config: AppConfig) -> str:
    prompt = (
        "You are a conservative dictation cleanup engine.\n"
        "Return text for direct insertion into a text field.\n\n"
        "Resolve natural spoken self-corrections anywhere in the sentence, including corrections phrased as:\n"
        "- actually ...\n"
        "- sorry ...\n"
        "- no ...\n"
        "- no not ...\n"
        "- rather ...\n"
        "- I mean ...\n"
        "- that's not what I meant ...\n"
        "- what I meant was ...\n"
        "- make that ...\n"
        "- instead ...\n"
        "- scratch that\n"
        "- start over\n"
        "- delete last word\n"
        "- delete last sentence\n\n"
        "When the speaker corrects a word, phrase, person, date, time, or object, keep the corrected version and remove the mistaken version.\n"
        "Remove filler words, repeated words, hesitation fragments, and false starts.\n"
        "Add punctuation and capitalization.\n"
        "Preserve the intended meaning. Do not summarize, expand, invent details, or change the user's style.\n"
        "Return only the final cleaned text. Do not explain your changes.\n\n"
        "Examples:\n"
        "Raw: schedule a meeting with John sorry Sarah\n"
        "Final: Schedule a meeting with Sarah.\n"
        "Raw: send it tomorrow no Friday\n"
        "Final: Send it Friday.\n"
        "Raw: I need the report by Tuesday that's not what I meant by Thursday\n"
        "Final: I need the report by Thursday.\n"
        "Raw: book a flight to London make that Paris next week\n"
        "Final: Book a flight to Paris next week.\n\n"
        f"Raw transcript: {raw_text}\n"
        f"Rule-cleaned draft: {draft_text}\n"
        "Final:"
    )
    payload = {
        "model": config.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 240,
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
    marker = r"(?:no not|i mean|actually|sorry|rather|no|not)"
    separator = r"(?:\s+|\s*[,;:]\s*)"
    optional_filler = r"(?:(?:oh|um|uh|erm)\b\s*[,;:]?\s*)?"
    text = re.sub(
        rf"\b(?P<old>\w+){separator}{marker}{separator}{optional_filler}(?P<new>\w+)\b",
        lambda match: match.group("new"),
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        rf"\b(?P<old>\w+(?:\s+\w+){{0,2}}){separator}{marker}{separator}{optional_filler}(?P<new>\w+(?:\s+\w+){{0,2}})(?=$|[,.!?;:])",
        lambda match: match.group("new"),
        text,
        flags=re.IGNORECASE,
    )
    return text


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
