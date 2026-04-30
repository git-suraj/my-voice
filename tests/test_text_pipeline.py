from pathlib import Path
import tempfile

from my_voice.assembly import assemble_chunks, reconcile_text
from my_voice.cleanup import apply_spoken_corrections, deterministic_cleanup
from my_voice.transcriber import (
    TranscriptChunk,
    _build_multipart_request,
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


def test_clean_whisper_cpp_output_removes_timestamps() -> None:
    output = """
    [00:00:00.000 --> 00:00:01.000]  Hello there.
    [00:00:01.000 --> 00:00:02.000]  How are you?
    """

    assert _clean_whisper_cpp_output(output) == "Hello there. How are you?"


def test_parse_whisper_cpp_server_json_response() -> None:
    assert _parse_whisper_cpp_server_response('{"text": " Hello there. "}') == "Hello there."


def test_build_multipart_request_includes_file_and_fields() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        audio = Path(tmpdir) / "sample.wav"
        audio.write_bytes(b"wav-data")

        payload, content_type = _build_multipart_request(str(audio), {"response_format": "json", "language": "en"})

    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="response_format"' in payload
    assert b"name=\"file\"; filename=\"sample.wav\"" in payload
    assert b"wav-data" in payload
