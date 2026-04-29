from __future__ import annotations

import argparse
import multiprocessing
from queue import Empty, Queue
import signal
import threading
import time
from typing import Any

from .assembly import assemble_chunks, reconcile_text
from .audio import AudioCapture, AudioFrame
from .cleanup import polished_cleanup
from .config import AppConfig, default_config_path, load_config
from .diagnostics import diagnose_audio
from .insertion import insert_text
from .permissions import request_microphone_permission
from .transcriber import TranscriptChunk, Transcriber
from .vad import AudioChunk, VadChunker


class DictationApp:
    def __init__(self, config: AppConfig, keyboard_backend: Any) -> None:
        self.config = config
        self.keyboard = keyboard_backend
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
            model_name=config.asr_model,
            device=config.asr_device,
            compute_type=config.asr_compute_type,
        )
        self._recording = threading.Event()
        self._shutdown = threading.Event()
        self._finalizing = threading.Event()
        self._session_started = 0.0
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
        print("Loading ASR model. First run may download model files...", flush=True)
        self.transcriber.load()
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
        self.audio.start()
        self._recording.set()

    def _on_hotkey_up(self) -> None:
        if not self._recording.is_set():
            return
        self._recording.clear()
        self._finalizing.set()
        self.audio.stop()
        full_session_audio = self.audio.session_audio()
        if self.config.enable_chunk_transcription:
            self.frames.join()
            self.chunker.end_session()
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
            self.chunks.join()
            self._collect_transcripts()
        self._finalizing.clear()
        full_text = ""
        if self.config.final_transcription_mode == "full_session" and full_session_audio.size:
            started = time.perf_counter()
            full_text = self.transcriber.transcribe_samples(full_session_audio)
            elapsed_ms = (time.perf_counter() - started) * 1000
            print(f"full session transcribed in {elapsed_ms:.0f}ms: {full_text}", flush=True)

        if not self._session_transcripts and not full_text:
            print("No speech detected.")
            return
        assembled = assemble_chunks(self._session_transcripts)
        source_text = full_text or assembled
        reconciled = reconcile_text(source_text)
        cleanup_started = time.perf_counter()
        final_text = polished_cleanup(reconciled, self.config)
        cleanup_ms = (time.perf_counter() - cleanup_started) * 1000
        print(f"assembled: {assembled}", flush=True)
        print(f"source: {source_text}", flush=True)
        print(f"reconciled: {reconciled}", flush=True)
        print(f"final: {final_text}", flush=True)
        insert_started = time.perf_counter()
        insert_text(final_text, self.config.text_insertion_method, self.config.restore_clipboard)
        insert_ms = (time.perf_counter() - insert_started) * 1000
        total_ms = (time.perf_counter() - self._session_started) * 1000
        print(f"Inserted {len(final_text)} chars. cleanup={cleanup_ms:.0f}ms insertion={insert_ms:.0f}ms total={total_ms:.0f}ms")

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


def main() -> None:
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
    print("Loading macOS hotkey backend...", flush=True)
    from pynput import keyboard

    app = DictationApp(config, keyboard)

    def handle_signal(signum, frame) -> None:
        app.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)
    try:
        app.run()
    finally:
        app.stop()


if __name__ == "__main__":
    main()
