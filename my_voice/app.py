from __future__ import annotations

import argparse
import multiprocessing
from queue import Empty, Queue
import signal
import subprocess
import threading
import time
from typing import Any, Callable

from .assembly import assemble_chunks, reconcile_text
from .audio import AudioCapture, AudioCaptureError, AudioFrame
from .cleanup import cleanup_with_metrics
from .config import AppConfig, default_config_path, load_config
from .diagnostics import diagnose_audio
from .feedback import show_feedback
from .insertion import insert_text
from .permissions import request_microphone_permission
from .transcriber import TranscriptChunk, Transcriber
from .vad import AudioChunk, VadChunker


StatusCallback = Callable[[str], None]


class DictationApp:
    def __init__(self, config: AppConfig, keyboard_backend: Any, status_callback: StatusCallback | None = None) -> None:
        self.config = config
        self.keyboard = keyboard_backend
        self.status_callback = status_callback or (lambda state: None)
        self.frames: Queue[AudioFrame] = Queue()
        self.chunks: Queue[AudioChunk] = Queue()
        self.transcripts: Queue[TranscriptChunk] = Queue()
        self.audio = AudioCapture(config.sample_rate, config.channels, config.frame_ms, self.frames)
        self.chunker = VadChunker(
            self.frames,
            self.chunks,
            sample_rate=config.sample_rate,
            frame_ms=config.frame_ms,
            silence_ms=config.vad_silence_ms,
            preroll_ms=config.vad_preroll_ms,
            min_chunk_ms=config.min_chunk_ms,
            overlap_ms=config.chunk_overlap_ms,
            threshold=config.vad_energy_threshold,
        )
        self.transcriber = Transcriber(
            self.chunks,
            self.transcripts,
            backend=config.asr_backend,
            model_name=config.asr_model,
            device=config.asr_device,
            compute_type=config.asr_compute_type,
            sample_rate=config.sample_rate,
            whisper_cpp_binary=config.whisper_cpp_binary,
            whisper_cpp_model=config.whisper_cpp_model,
            whisper_cpp_extra_args=config.whisper_cpp_extra_args,
            whisper_cpp_server_binary=config.whisper_cpp_server_binary,
            whisper_cpp_server_host=config.whisper_cpp_server_host,
            whisper_cpp_server_port=config.whisper_cpp_server_port,
            whisper_cpp_server_start=config.whisper_cpp_server_start,
            whisper_cpp_server_timeout_s=config.whisper_cpp_server_timeout_s,
            whisper_cpp_server_extra_args=config.whisper_cpp_server_extra_args,
        )
        self._recording = threading.Event()
        self._shutdown = threading.Event()
        self._finalizing = threading.Event()
        self._session_started = 0.0
        self._session_stopped = 0.0
        self._session_transcripts: list[TranscriptChunk] = []
        hotkey_keys = self.keyboard.HotKey.parse(config.shortcut)
        self._hotkey_keys = set(hotkey_keys)
        self._hotkey = self.keyboard.HotKey(hotkey_keys, self._on_hotkey_down)
        self._listener: Any | None = None

    def run(self) -> None:
        print(f"Config: {default_config_path()}", flush=True)
        if self.config.request_microphone_on_start:
            print("Checking microphone access...", flush=True)
            request_microphone_permission(self.config)
        print(f"Loading ASR backend: {self.config.asr_backend}", flush=True)
        print("Loading ASR model. First run may download model files...", flush=True)
        self.transcriber.load()
        self.status_callback("idle")
        if self.config.enable_chunk_transcription:
            self.chunker.start()
            self.transcriber.start()
        self._listener = self.keyboard.Listener(on_press=self._for_canonical(self._hotkey.press), on_release=self._on_release)
        self._listener.start()
        print(f"Ready. Hold {self.config.shortcut} to dictate. Press Ctrl+C to quit.", flush=True)
        while not self._shutdown.is_set():
            self._collect_transcripts()
            time.sleep(0.05)

    def stop(self) -> None:
        self._shutdown.set()
        self.audio.stop()
        self.chunker.shutdown()
        self.transcriber.shutdown()
        if self._listener is not None:
            self._listener.stop()

    def _on_hotkey_down(self) -> None:
        if self._recording.is_set():
            return
        print("Recording...")
        self._session_started = time.perf_counter()
        self._session_transcripts.clear()
        self._drain_transcripts()
        self._finalizing.clear()
        if self.config.enable_chunk_transcription:
            self.chunker.begin_session()
        try:
            self.audio.start()
        except AudioCaptureError as exc:
            self.status_callback("error")
            show_feedback("error", self.config)
            print(f"recording start failed: {exc}", flush=True)
            print(
                "Check that no other app is exclusively using the microphone, then run `my-voice --diagnose-audio`.",
                flush=True,
            )
            if self.config.enable_chunk_transcription:
                self.chunker.end_session()
            self._finalizing.clear()
            return
        self._recording.set()
        self.status_callback("recording")
        show_feedback("start", self.config)

    def _on_hotkey_up(self) -> None:
        if not self._recording.is_set():
            return
        self._recording.clear()
        self._finalizing.set()
        self.status_callback("processing")
        self.audio.stop()
        self._session_stopped = time.perf_counter()
        show_feedback("stop", self.config)
        full_session_audio = self.audio.session_audio()
        if self.config.enable_chunk_transcription:
            chunk_wait_started = time.perf_counter()
            self.frames.join()
            self.chunker.end_session()
            chunk_wait_ms = (time.perf_counter() - chunk_wait_started) * 1000
            if chunk_wait_ms:
                print(f"chunk finalization wait: {chunk_wait_ms:.0f}ms", flush=True)
        else:
            self._drain_frames()
        self._finalize_session(full_session_audio)

    def _on_release(self, key: Any | None) -> None:
        canonical = self._listener.canonical(key) if self._listener is not None and key is not None else key
        self._hotkey.release(canonical)
        if self._recording.is_set() and canonical in self._hotkey_keys:
            self._on_hotkey_up()

    def _for_canonical(self, callback):
        def wrapper(key):
            if self._listener is None:
                callback(key)
            else:
                callback(self._listener.canonical(key))

        return wrapper

    def _finalize_session(self, full_session_audio) -> None:
        if self.config.enable_chunk_transcription:
            chunk_transcript_wait_started = time.perf_counter()
            self.chunks.join()
            chunk_transcript_wait_ms = (time.perf_counter() - chunk_transcript_wait_started) * 1000
            if chunk_transcript_wait_ms:
                print(f"chunk transcription wait: {chunk_transcript_wait_ms:.0f}ms", flush=True)
            self._collect_transcripts()
        self._finalizing.clear()
        full_text = ""
        full_asr_ms = 0.0
        if self.config.final_transcription_mode == "full_session" and full_session_audio.size:
            started = time.perf_counter()
            try:
                full_text = self.transcriber.transcribe_samples(full_session_audio)
            except Exception as exc:
                self.status_callback("error")
                print(f"full session transcription failed: {exc!r}", flush=True)
                full_text = ""
            full_asr_ms = (time.perf_counter() - started) * 1000
            if full_text:
                print(f"full session transcribed in {full_asr_ms:.0f}ms: {full_text}", flush=True)

        if not self._session_transcripts and not full_text:
            print("No speech detected.")
            self.status_callback("idle")
            return
        assemble_started = time.perf_counter()
        assembled = assemble_chunks(self._session_transcripts) if self._session_transcripts else ""
        assemble_ms = (time.perf_counter() - assemble_started) * 1000

        reconcile_ms = 0.0
        if full_text:
            source_text = full_text
        else:
            reconcile_started = time.perf_counter()
            source_text = reconcile_text(assembled)
            reconcile_ms = (time.perf_counter() - reconcile_started) * 1000

        cleanup = cleanup_with_metrics(source_text, self.config)
        final_text = cleanup.text
        if assembled:
            print(f"assembled: {assembled}", flush=True)
        print(f"source: {source_text}", flush=True)
        if cleanup.llm_error:
            print(f"llm cleanup fallback: {cleanup.llm_error}", flush=True)
        print(f"final: {final_text}", flush=True)
        insert_started = time.perf_counter()
        inserted = False
        insertion_error = ""
        try:
            insert_text(final_text, self.config.text_insertion_method, self.config.restore_clipboard)
            inserted = True
        except subprocess.SubprocessError as exc:
            insertion_error = _format_subprocess_error(exc)
            print(f"insertion failed: {insertion_error}", flush=True)
            print("The final text should still be on the clipboard if clipboard insertion was attempted.", flush=True)
        insert_ms = (time.perf_counter() - insert_started) * 1000
        total_ms = (time.perf_counter() - self._session_started) * 1000
        recording_ms = (self._session_stopped - self._session_started) * 1000
        print(
            "timing: "
            f"recording={recording_ms:.0f}ms "
            f"asr_backend={self.config.asr_backend} "
            f"asr={full_asr_ms:.0f}ms "
            f"assemble={assemble_ms:.0f}ms "
            f"reconcile={reconcile_ms:.0f}ms "
            f"deterministic_cleanup={cleanup.deterministic_ms:.0f}ms "
            f"llm_cleanup={cleanup.llm_ms:.0f}ms "
            f"cleanup_total={cleanup.total_ms:.0f}ms "
            f"insertion={insert_ms:.0f}ms "
            f"total={total_ms:.0f}ms "
            f"llm_used={cleanup.used_llm} "
            f"inserted={inserted}",
            flush=True,
        )
        if inserted:
            print(f"Inserted {len(final_text)} chars.", flush=True)
            show_feedback("done", self.config)
        self.status_callback("idle")

    def _collect_transcripts(self) -> None:
        while True:
            try:
                item = self.transcripts.get_nowait()
            except Empty:
                return
            if item.error:
                print(f"chunk {item.id} transcription failed after {item.elapsed_ms:.0f}ms: {item.error}", flush=True)
                continue
            print(f"chunk {item.id} transcribed in {item.elapsed_ms:.0f}ms: {item.text}")
            self._session_transcripts.append(item)

    def _drain_transcripts(self) -> None:
        while True:
            try:
                self.transcripts.get_nowait()
            except Empty:
                return

    def _drain_frames(self) -> None:
        while True:
            try:
                self.frames.get_nowait()
                self.frames.task_done()
            except Empty:
                return


def _format_subprocess_error(exc: subprocess.SubprocessError) -> str:
    if isinstance(exc, subprocess.CalledProcessError):
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        detail = stderr or stdout
        if detail:
            return f"{exc.cmd} exited {exc.returncode}: {detail}"
        return f"{exc.cmd} exited {exc.returncode}"
    return str(exc)


def main(status_callback: StatusCallback | None = None, keyboard_backend: Any | None = None) -> None:
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description="Local push-to-talk dictation for macOS")
    parser.add_argument("--diagnose-audio", action="store_true", help="record a short sample and print microphone levels")
    parser.add_argument("--seconds", type=float, default=3.0, help="diagnostic recording length")
    args = parser.parse_args()

    config = load_config()
    if args.diagnose_audio:
        diagnose_audio(config, seconds=args.seconds)
        return

    print("Starting my-voice...", flush=True)
    if keyboard_backend is None:
        print("Loading macOS hotkey backend...", flush=True)
        from pynput import keyboard
    else:
        print("Using preloaded macOS hotkey backend...", flush=True)
        keyboard = keyboard_backend

    app = DictationApp(config, keyboard, status_callback=status_callback)

    def handle_signal(signum, frame) -> None:
        app.stop()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
    try:
        app.run()
    finally:
        app.stop()


if __name__ == "__main__":
    main()
