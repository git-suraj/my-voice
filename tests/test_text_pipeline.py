from pathlib import Path
import tempfile
import time

from my_voice.assembly import assemble_chunks, reconcile_text
from my_voice.cleanup import apply_spoken_corrections, deterministic_cleanup
from my_voice.cleanup import _parse_cleanup_json, _valid_llm_cleanup
from my_voice.cleanup import cleanup_with_metrics
from my_voice.config import AppConfig
from my_voice.personal_corrections import apply_personal_corrections, save_corrections
from my_voice.transcriber import (
    TranscriptChunk,
    _build_multipart_request,
    _clean_asr_text,
    _clean_whisper_cpp_output,
    _parse_whisper_cpp_server_response,
)


def test_assemble_removes_boundary_duplicate() -> None:
    chunks = [
        TranscriptChunk(id=0, text="Hey Sarah can you send", elapsed_ms=1),
        TranscriptChunk(id=1, text="send me the invoice tomorrow", elapsed_ms=1),
    ]
    assert assemble_chunks(chunks) == "Hey Sarah can you send me the invoice tomorrow"


def test_reconcile_self_correction() -> None:
    assert reconcile_text("Send it to John actually Sarah") == "Send it to Sarah"


def test_deterministic_cleanup_removes_fillers() -> None:
    assert deterministic_cleanup("um hey Sarah  can you send the invoice") == "Hey Sarah can you send the invoice"


def test_scratch_that_keeps_text_after_command() -> None:
    assert apply_spoken_corrections("send John the deck scratch that send Sarah the deck") == "send Sarah the deck"


def test_delete_last_word_removes_previous_word() -> None:
    assert apply_spoken_corrections("meet tomorrow delete last word Friday") == "meet Friday"


def test_delete_last_sentence_removes_previous_sentence() -> None:
    assert apply_spoken_corrections("Send the invoice. delete last sentence Remind me tomorrow") == "Remind me tomorrow"


def test_inline_actually_replacement() -> None:
    assert apply_spoken_corrections("send it to John actually Sarah") == "send it to Sarah"


def test_inline_sorry_replacement() -> None:
    assert apply_spoken_corrections("schedule a meeting with John sorry Sarah") == "schedule a meeting with Sarah"


def test_inline_sorry_replacement_with_punctuation_and_filler() -> None:
    assert deterministic_cleanup("Yeah, let's plan for Sarah, sorry, oh, Roger.") == "Yeah, let's plan for Roger."


def test_asr_sentence_boundary_correction_is_left_for_llm() -> None:
    assert deterministic_cleanup("Can you please schedule a meeting with Roger? Sorry, Sarah.")


def test_phrase_level_no_replacement_is_left_for_llm() -> None:
    assert deterministic_cleanup("Meet tomorrow at 10 no Friday at 11")


def test_make_that_clause_replacement_is_left_for_llm() -> None:
    assert deterministic_cleanup("Book a flight to London make that Paris next week")


def test_inline_sorry_replacement_for_object_phrase() -> None:
    assert deterministic_cleanup("Send the pricing deck sorry the architecture deck")


def test_explicit_i_meant_replacement_preserves_following_details() -> None:
    assert (
        deterministic_cleanup("Schedule a meeting with Sara. Sorry, I meant Roger at 10 a.m. tomorrow.")
        == "Schedule a meeting with Roger at 10 a.m. tomorrow."
    )


def test_explicit_i_mean_replacement_preserves_negated_clause() -> None:
    assert (
        deterministic_cleanup("Okay, so I'm just checking if this is working. Sorry, I mean if this is not working.")
        == "Okay, so I'm just checking if this is not working."
    )


def test_cleanup_skips_llm_when_deterministic_correction_applies() -> None:
    result = cleanup_with_metrics(
        "Okay, so I'm just checking if this is working. Sorry, I mean if this is not working.",
        AppConfig(cleanup_mode="polished", ollama_enabled=True),
    )

    assert result.text == "Okay, so I'm just checking if this is not working."
    assert result.used_llm is False


def test_literal_apology_is_not_treated_as_replacement() -> None:
    assert deterministic_cleanup("I am sorry Sarah") == "I am sorry Sarah"


def test_clean_whisper_cpp_output_removes_timestamps() -> None:
    output = """
    [00:00:00.000 --> 00:00:01.000]  Hello there.
    [00:00:01.000 --> 00:00:02.000]  How are you?
    """

    assert _clean_whisper_cpp_output(output) == "Hello there. How are you?"


def test_clean_asr_text_suppresses_blank_audio_markers() -> None:
    assert _clean_asr_text("[BLANK_AUDIO]") == ""
    assert _clean_asr_text("[silence]") == ""
    assert _clean_asr_text("Hello [BLANK_AUDIO] there") == "Hello there"


def test_parse_whisper_cpp_server_json_response() -> None:
    assert _parse_whisper_cpp_server_response('{"text": " Hello there. "}') == "Hello there."


def test_parse_whisper_cpp_server_json_response_suppresses_blank_audio() -> None:
    assert _parse_whisper_cpp_server_response('{"text": "[BLANK_AUDIO]"}') == ""


def test_build_multipart_request_includes_file_and_fields() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        audio = Path(tmpdir) / "sample.wav"
        audio.write_bytes(b"wav-data")

        payload, content_type = _build_multipart_request(str(audio), {"response_format": "json", "language": "en"})

    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="response_format"' in payload
    assert b"name=\"file\"; filename=\"sample.wav\"" in payload
    assert b"wav-data" in payload


def test_parse_cleanup_json_from_model_response() -> None:
    parsed = _parse_cleanup_json(
        '```json\n{"final_text":"Schedule a meeting with Sarah.","corrections_applied":true,"confidence":"high"}\n```'
    )

    assert parsed["final_text"] == "Schedule a meeting with Sarah."
    assert parsed["corrections_applied"] is True
    assert parsed["confidence"] == "high"


def test_valid_llm_cleanup_allows_semantic_correction() -> None:
    assert _valid_llm_cleanup(
        "Okay, so I'm just checking if this is working. Sorry, I mean if this is not working.",
        "Okay, so I'm just checking if this is working. Sorry, if this is not working.",
        "Okay, so I'm just checking if this is not working.",
        True,
        "high",
    )


def test_valid_llm_cleanup_allows_task_bullet_formatting() -> None:
    assert _valid_llm_cleanup(
        "I want to make a house then paint it.",
        "I want to make a house then paint it.",
        "I want to:\n- make a house\n- paint it",
        False,
        "high",
    )


def test_valid_llm_cleanup_allows_numbered_list_formatting() -> None:
    assert _valid_llm_cleanup(
        "Okay, number one I want to review the deck. Number two I want to send the notes.",
        "Okay, number one I want to review the deck. Number two I want to send the notes.",
        "1. I want to review the deck.\n2. I want to send the notes.",
        False,
        "high",
    )


def test_valid_llm_cleanup_allows_trailing_meta_speech_removal() -> None:
    assert _valid_llm_cleanup(
        "Make sure that the README is updated even with the blank audio thing. "
        "There was another thing which I wanted to do which is... What was that? Yeah, I think that's it.",
        "Make sure that the README is updated even with the blank audio thing. "
        "There was another thing which I wanted to do which is... What was that? Yeah, I think that's it.",
        "Make sure that the README is updated even with the blank audio thing.",
        True,
        "high",
    )


def test_valid_llm_cleanup_rejects_large_drop_without_correction() -> None:
    assert not _valid_llm_cleanup(
        "Please schedule a meeting with Sarah at 10 a.m. tomorrow.",
        "Please schedule a meeting with Sarah at 10 a.m. tomorrow.",
        "Schedule a meeting.",
        False,
        "high",
    )


def test_valid_llm_cleanup_rejects_large_drop_with_weak_correction() -> None:
    assert not _valid_llm_cleanup(
        "I am sorry Sarah.",
        "I am sorry Sarah.",
        "Sarah.",
        True,
        "high",
    )


def test_valid_llm_cleanup_rejects_unapplied_i_mean_phrase() -> None:
    assert not _valid_llm_cleanup(
        "Okay, I mean Friday.",
        "Okay, Friday.",
        "Okay, I mean Friday.",
        True,
        "high",
    )


def test_personal_corrections_apply_whole_words() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "corrections.json"
        save_corrections(path, {"cong": "Kong"})
        result = apply_personal_corrections(
            "cong gateway not congress",
            AppConfig(personal_corrections_path=str(path)),
        )

    assert result.text == "Kong gateway not congress"
    assert result.applied == 1


def test_personal_corrections_apply_longer_phrases_first() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "corrections.json"
        save_corrections(path, {"kong connect": "Kong Konnect", "kong": "Kong"})
        result = apply_personal_corrections(
            "open kong connect and kong gateway",
            AppConfig(personal_corrections_path=str(path)),
        )

    assert result.text == "open Kong Konnect and Kong gateway"
    assert result.applied == 2


def test_personal_corrections_can_be_disabled() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "corrections.json"
        save_corrections(path, {"cong": "Kong"})
        result = apply_personal_corrections(
            "cong gateway",
            AppConfig(personal_corrections_path=str(path), personal_corrections_enabled=False),
        )

    assert result.text == "cong gateway"
    assert result.applied == 0


def test_personal_corrections_cache_reloads_when_file_changes() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "corrections.json"
        config = AppConfig(personal_corrections_path=str(path))
        save_corrections(path, {"cong": "Kong"})
        first = apply_personal_corrections("cong gateway", config)

        time.sleep(0.01)
        save_corrections(path, {"cong": "Kong Inc"})
        second = apply_personal_corrections("cong gateway", config)

    assert first.text == "Kong gateway"
    assert second.text == "Kong Inc gateway"
