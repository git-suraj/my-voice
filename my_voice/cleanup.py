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

CORRECTION_CUE_PATTERN = (
    r"\b(?:scratch that|start over|delete last word|delete last sentence|"
    r"that's not what i meant|what i meant was|make that|no not|i mean|i meant|"
    r"what was that|never mind|i forgot|i think that's it|i think that is it|"
    r"that's it|that is it|actually|sorry|rather|instead|no)\b"
)
TRAILING_META_CUE_PATTERN = (
    r"\b(?:what was that|never mind|i forgot|i think that's it|i think that is it|"
    r"there was another thing|that's it|that is it)\b"
)
LOCAL_REPLACEMENT_MARKER = r"(?:actually|sorry|rather|no)"


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
    corrected = _apply_explicit_mean_replacements(corrected)
    corrected = _apply_safe_local_replacements(corrected)
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
    deterministic_changed = _normalized_for_compare(apply_spoken_corrections(text)) != _normalized_for_compare(text)
    if config.cleanup_mode != "polished" or not config.ollama_enabled or deterministic_changed:
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
        "You are a dictation correction engine.\n"
        "Convert a raw speech transcript into the exact text the speaker intended to insert.\n\n"
        "Rules:\n"
        "- Preserve the speaker's meaning.\n"
        "- Do not summarize.\n"
        "- Do not add new information.\n"
        "- Do not make the text more formal unless needed for grammar.\n"
        "- Apply spoken self-corrections semantically.\n"
        "- Remove correction phrases after applying them.\n"
        "- Remove filler words and false starts.\n"
        "- Remove trailing meta-speech where the speaker is thinking aloud, searching for what to say, or abandoning an unfinished thought.\n"
        "- Examples of trailing meta-speech include 'there was another thing...', 'what was that?', 'I forgot', 'never mind', and 'yeah, I think that's it' when they are not part of the intended message.\n"
        "- If the speaker dictates a numbered sequence such as 'number one ... number two ...', format it as a numbered list.\n"
        "- For numbered lists, use plain lines like '1. ...' and '2. ...'. Do not use bullets unless the speaker asked for bullets.\n"
        "- If the speaker states an intro phrase like 'I want to', 'I need to', 'I have to', 'Let's', or 'We should' followed by multiple actions joined by 'then', 'and then', 'also', 'plus', or 'after that', format it as the intro line plus Markdown bullets.\n"
        "- Keep names, dates, times, numbers, products, and technical terms exactly unless the speaker corrected them.\n"
        "- Treat the rule-cleaned draft as a conservative baseline, not as authoritative when the raw transcript contains a broader correction.\n\n"
        "Correction guidance:\n"
        "- 'John sorry Sarah' means replace John with Sarah.\n"
        "- 'tomorrow no Friday' means replace tomorrow with Friday.\n"
        "- 'I mean ...' often replaces the immediately previous word, phrase, or clause.\n"
        "- 'sorry, I mean ...' often replaces the immediately previous word, phrase, or clause.\n"
        "- If the correction starts with the same word as a recent clause, replace that recent clause from that word onward.\n"
        "- Example: 'checking if this is working. Sorry, I mean if this is not working' keeps 'checking' and replaces 'if this is working' with 'if this is not working'.\n"
        "- 'actually ...' often replaces the immediately previous word, phrase, or clause.\n"
        "- 'that's not what I meant ...' means use the corrected statement that follows.\n"
        "- 'scratch that' means discard the previous thought and use what follows.\n"
        "- 'start over' means discard everything before it.\n\n"
        "Return JSON only in this exact shape:\n"
        "{\"final_text\":\"...\",\"corrections_applied\":true,\"confidence\":\"high\"}\n"
        "confidence must be one of: high, medium, low.\n\n"
        "Examples:\n"
        "Raw: Okay, so I'm just checking if this is working. Sorry, I mean if this is not working.\n"
        "JSON: {\"final_text\":\"Okay, so I'm just checking if this is not working.\",\"corrections_applied\":true,\"confidence\":\"high\"}\n"
        "Raw: Can you please schedule a meeting with Roger? Sorry, Sarah.\n"
        "JSON: {\"final_text\":\"Can you please schedule a meeting with Sarah.\",\"corrections_applied\":true,\"confidence\":\"high\"}\n"
        "Raw: Schedule a meeting with Sara. Sorry, I meant Roger at 10 a.m. tomorrow.\n"
        "JSON: {\"final_text\":\"Schedule a meeting with Roger at 10 a.m. tomorrow.\",\"corrections_applied\":true,\"confidence\":\"high\"}\n"
        "Raw: Schedule a meeting with Sara. Sorry, I mean Roger at 10 a.m. tomorrow.\n"
        "JSON: {\"final_text\":\"Schedule a meeting with Roger at 10 a.m. tomorrow.\",\"corrections_applied\":true,\"confidence\":\"high\"}\n"
        "Raw: I am sorry Sarah.\n"
        "JSON: {\"final_text\":\"I am sorry Sarah.\",\"corrections_applied\":false,\"confidence\":\"high\"}\n"
        "Raw: Okay, number one I want to review the deck. Number two I want to send the notes.\n"
        "JSON: {\"final_text\":\"1. I want to review the deck.\\n2. I want to send the notes.\",\"corrections_applied\":false,\"confidence\":\"high\"}\n"
        "Raw: I want to make a house then paint it.\n"
        "JSON: {\"final_text\":\"I want to:\\n- make a house\\n- paint it\",\"corrections_applied\":false,\"confidence\":\"high\"}\n"
        "Raw: I need to review the deck and then send it to Sarah.\n"
        "JSON: {\"final_text\":\"I need to:\\n- review the deck\\n- send it to Sarah\",\"corrections_applied\":false,\"confidence\":\"high\"}\n"
        "Raw: Make sure that the README is updated even with the blank audio thing. There was another thing which I wanted to do which is... What was that? Yeah, I think that's it.\n"
        "JSON: {\"final_text\":\"Make sure that the README is updated even with the blank audio thing.\",\"corrections_applied\":true,\"confidence\":\"high\"}\n\n"
        f"Raw transcript: {raw_text}\n"
        f"Rule-cleaned draft: {draft_text}\n"
        "JSON:"
    )
    payload = {
        "model": config.ollama_model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 300,
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
    content = str(result.get("response", "")).strip()
    parsed = _parse_cleanup_json(content)
    final_text = parsed.get("final_text", "").strip()
    corrections_applied = bool(parsed.get("corrections_applied", False))
    confidence = str(parsed.get("confidence", "")).lower()
    if not _valid_llm_cleanup(raw_text, draft_text, final_text, corrections_applied, confidence):
        return ""
    return final_text


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


def _apply_explicit_mean_replacements(text: str) -> str:
    pattern = re.compile(
        r"(?P<before>.*\b[\w'-]+\b)\s*[.!?]?\s*(?:sorry\s*,?\s*)?"
        r"(?:i\s+meant|i\s+mean|what\s+i\s+meant\s+was)\s+(?P<replacement>.+?)(?=$|[!?](?:\s|$))",
        flags=re.IGNORECASE,
    )
    return pattern.sub(
        lambda match: _replace_previous_clause(match.group("before"), match.group("replacement")),
        text,
    )


def _apply_safe_local_replacements(text: str) -> str:
    separator = r"(?:\s+|\s*[,;:]\s*)"
    optional_filler = r"(?:(?:oh|um|uh|erm)\b\s*[,;:]?\s*)?"
    return re.sub(
        rf"\b(?P<old>[\w'-]+){separator}(?P<marker>{LOCAL_REPLACEMENT_MARKER})"
        rf"{separator}{optional_filler}(?P<new>[\w'-]+(?:\s+[\w'-]+){{0,2}})(?=$|[,.!?;:])",
        _replace_safe_local_match,
        text,
        flags=re.IGNORECASE,
    )


def _replace_safe_local_match(match: re.Match) -> str:
    if _looks_like_literal_apology(match.group("old"), match.group("marker")):
        return match.group(0)
    return match.group("new")


def _looks_like_literal_apology(before: str, marker: str) -> bool:
    if marker.lower() != "sorry":
        return False
    words = [word.lower() for word in re.findall(r"[\w'-]+", before)]
    return bool(words and words[-1] in {"am", "i'm", "im", "was", "were", "be", "feel", "felt"})


def _replace_previous_clause(before: str, replacement: str) -> str:
    before = before.rstrip(" ,;:!?")
    replacement = replacement.strip(" ,;:!?")
    before_words = list(re.finditer(r"[\w'-]+", before))
    replacement_words = [word.lower() for word in re.findall(r"[\w'-]+", replacement)]
    if not before_words or not replacement_words:
        return f"{before} {replacement}".strip()

    first_replacement_word = replacement_words[0]
    for word in reversed(before_words[-12:]):
        if word.group(0).lower() == first_replacement_word:
            return f"{before[: word.start()].rstrip()} {replacement}".strip()

    anchors = {"with", "to", "for", "by", "on", "in", "from", "as", "called", "named"}
    if first_replacement_word not in anchors:
        for word in reversed(before_words[-8:]):
            if word.group(0).lower() in anchors:
                return f"{before[: word.end()].rstrip()} {replacement}".strip()

    suffix_word_count = min(max(len(replacement_words), 1), 6, len(before_words))
    target_start = before_words[-suffix_word_count].start()
    return f"{before[:target_start].rstrip()} {replacement}".strip()


def _parse_cleanup_json(content: str) -> dict:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        cleaned = match.group(0)
    parsed = json.loads(cleaned)
    return parsed if isinstance(parsed, dict) else {}


def _valid_llm_cleanup(
    raw_text: str,
    draft_text: str,
    final_text: str,
    corrections_applied: bool,
    confidence: str,
) -> bool:
    if not final_text or confidence not in {"high", "medium", "low"}:
        return False
    if len(final_text) > max(len(raw_text), len(draft_text), 1) * 2.2:
        return False
    raw_has_correction = re.search(CORRECTION_CUE_PATTERN, raw_text, flags=re.IGNORECASE) is not None
    if not raw_has_correction and _word_count(final_text) < _word_count(draft_text) * 0.65:
        return False
    if (
        raw_has_correction
        and not re.search(r"\b(?:scratch that|start over)\b", raw_text, flags=re.IGNORECASE)
        and not re.search(TRAILING_META_CUE_PATTERN, raw_text, flags=re.IGNORECASE)
        and _word_count(final_text) < _word_count(draft_text) * 0.45
    ):
        return False
    if corrections_applied and re.search(r"\b(?:sorry,\s*)?(?:i mean|i meant)\b", final_text, flags=re.IGNORECASE):
        return False
    if corrections_applied and confidence == "low":
        return False
    return True


def _word_count(text: str) -> int:
    return len(re.findall(r"[\w'-]+", text))


def _normalized_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
