from my_voice.assembly import assemble_chunks, reconcile_text
from my_voice.cleanup import deterministic_cleanup
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

