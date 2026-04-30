from my_voice.assembly import assemble_chunks, reconcile_text
from my_voice.cleanup import apply_spoken_corrections, deterministic_cleanup
from my_voice.transcriber import TranscriptChunk


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
