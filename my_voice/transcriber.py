from __future__ import annotations

from dataclasses import dataclass
import json
from queue import Empty, Queue
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
from urllib import error, request
import uuid
import wave

import numpy as np

from .vad import AudioChunk


@dataclass(slots=True)
class TranscriptChunk:
    id: int
    text: str
    elapsed_ms: float
    error: str | None = None


class Transcriber(threading.Thread):
    def __init__(
        self,
        chunks: Queue[AudioChunk],
        transcripts: Queue[TranscriptChunk],
        *,
        backend: str,
        model_name: str,
        device: str,
        compute_type: str,
        sample_rate: int,
        whisper_cpp_binary: str,
        whisper_cpp_model: str,
        whisper_cpp_extra_args: list[str] | None,
        whisper_cpp_server_binary: str,
        whisper_cpp_server_host: str,
        whisper_cpp_server_port: int,
        whisper_cpp_server_start: bool,
        whisper_cpp_server_timeout_s: float,
        whisper_cpp_server_extra_args: list[str],
    ) -> None:
        super().__init__(daemon=True)
        self.chunks = chunks
        self.transcripts = transcripts
        self.backend = backend
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.sample_rate = sample_rate
        self.whisper_cpp_binary = whisper_cpp_binary
        self.whisper_cpp_model = whisper_cpp_model
        self.whisper_cpp_extra_args = whisper_cpp_extra_args or ["-nt"]
        self.whisper_cpp_server_binary = whisper_cpp_server_binary
        self.whisper_cpp_server_host = whisper_cpp_server_host
        self.whisper_cpp_server_port = whisper_cpp_server_port
        self.whisper_cpp_server_start = whisper_cpp_server_start
        self.whisper_cpp_server_timeout_s = whisper_cpp_server_timeout_s
        self.whisper_cpp_server_extra_args = whisper_cpp_server_extra_args
        self._server_process: subprocess.Popen | None = None
        self._shutdown_event = threading.Event()
        self._model = None

    def load(self) -> None:
        if self.backend == "whisper-cpp":
            self._validate_whisper_cpp()
            self._model = "whisper-cpp"
            return
        if self.backend == "whisper-cpp-server":
            self._start_or_connect_whisper_cpp_server()
            self._model = "whisper-cpp-server"
            return
        if self.backend != "faster-whisper":
            raise ValueError(f"Unsupported ASR backend: {self.backend}")

        from faster_whisper import WhisperModel

        self._model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)

    def shutdown(self) -> None:
        self._shutdown_event.set()
        if self._server_process is not None and self._server_process.poll() is None:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._server_process.kill()

    def run(self) -> None:
        if self._model is None:
            self.load()
        while not self._shutdown_event.is_set():
            try:
                chunk = self.chunks.get(timeout=0.1)
            except Empty:
                continue
            try:
                started = time.perf_counter()
                text = self._transcribe(chunk.samples)
                elapsed_ms = (time.perf_counter() - started) * 1000
                self.transcripts.put(TranscriptChunk(id=chunk.id, text=text, elapsed_ms=elapsed_ms))
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                self.transcripts.put(TranscriptChunk(id=chunk.id, text="", elapsed_ms=elapsed_ms, error=repr(exc)))
            finally:
                self.chunks.task_done()

    def _transcribe(self, samples: np.ndarray) -> str:
        return self.transcribe_samples(samples)

    def transcribe_samples(self, samples: np.ndarray) -> str:
        if self._model is None:
            raise RuntimeError("Transcriber model is not loaded")
        if self.backend == "whisper-cpp":
            return self._transcribe_with_whisper_cpp(samples)
        if self.backend == "whisper-cpp-server":
            return self._transcribe_with_whisper_cpp_server(samples)
        segments, _info = self._model.transcribe(
            samples,
            language="en",
            vad_filter=False,
            beam_size=5,
            best_of=5,
            condition_on_previous_text=False,
            temperature=0,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def _validate_whisper_cpp(self) -> None:
        binary_path = Path(self.whisper_cpp_binary).expanduser()
        binary = str(binary_path) if binary_path.exists() else shutil.which(self.whisper_cpp_binary)
        if not binary:
            raise RuntimeError(
                f"whisper.cpp binary not found: {self.whisper_cpp_binary}. "
                "Set whisper_cpp_binary to the full path of whisper-cli."
            )
        self.whisper_cpp_binary = binary
        if not self.whisper_cpp_model:
            raise RuntimeError("whisper_cpp_model is required when asr_backend is whisper-cpp")
        if not Path(self.whisper_cpp_model).expanduser().exists():
            raise RuntimeError(f"whisper.cpp model not found: {self.whisper_cpp_model}")

    def _validate_whisper_cpp_server(self) -> None:
        if not self.whisper_cpp_model:
            raise RuntimeError("whisper_cpp_model is required when asr_backend is whisper-cpp-server")
        if not Path(self.whisper_cpp_model).expanduser().exists():
            raise RuntimeError(f"whisper.cpp model not found: {self.whisper_cpp_model}")
        binary_path = Path(self.whisper_cpp_server_binary).expanduser()
        binary = str(binary_path) if binary_path.exists() else shutil.which(self.whisper_cpp_server_binary)
        if not binary:
            raise RuntimeError(
                f"whisper.cpp server binary not found: {self.whisper_cpp_server_binary}. "
                "Set whisper_cpp_server_binary to the full path of whisper-server."
            )
        self.whisper_cpp_server_binary = binary

    def _start_or_connect_whisper_cpp_server(self) -> None:
        if self._is_whisper_cpp_server_ready():
            return
        if not self.whisper_cpp_server_start:
            raise RuntimeError(f"whisper.cpp server is not reachable at {self._server_base_url()}")
        self._validate_whisper_cpp_server()
        command = [
            self.whisper_cpp_server_binary,
            "-m",
            str(Path(self.whisper_cpp_model).expanduser()),
            "--host",
            self.whisper_cpp_server_host,
            "--port",
            str(self.whisper_cpp_server_port),
            *self.whisper_cpp_server_extra_args,
        ]
        self._server_process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        deadline = time.monotonic() + self.whisper_cpp_server_timeout_s
        while time.monotonic() < deadline:
            if self._server_process.poll() is not None:
                raise RuntimeError(f"whisper.cpp server exited with code {self._server_process.returncode}")
            if self._is_whisper_cpp_server_ready():
                return
            time.sleep(0.2)
        raise RuntimeError(f"Timed out waiting for whisper.cpp server at {self._server_base_url()}")

    def _transcribe_with_whisper_cpp(self, samples: np.ndarray) -> str:
        samples = np.asarray(samples, dtype=np.float32)
        if samples.size == 0:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as audio_file:
            self._write_wav(audio_file.name, samples)
            command = [
                self.whisper_cpp_binary,
                "-m",
                str(Path(self.whisper_cpp_model).expanduser()),
                "-f",
                audio_file.name,
                "-l",
                "en",
                *self.whisper_cpp_extra_args,
            ]
            result = subprocess.run(command, check=True, capture_output=True, text=True)
        return _clean_whisper_cpp_output(result.stdout)

    def _transcribe_with_whisper_cpp_server(self, samples: np.ndarray) -> str:
        samples = np.asarray(samples, dtype=np.float32)
        if samples.size == 0:
            return ""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as audio_file:
            self._write_wav(audio_file.name, samples)
            payload, content_type = _build_multipart_request(
                audio_file.name,
                fields={
                    "response_format": "json",
                    "language": "en",
                    "temperature": "0.0",
                },
            )
        req = request.Request(
            f"{self._server_base_url()}/inference",
            data=payload,
            headers={"Content-Type": content_type},
            method="POST",
        )
        with request.urlopen(req, timeout=self.whisper_cpp_server_timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
        return _parse_whisper_cpp_server_response(body)

    def _is_whisper_cpp_server_ready(self) -> bool:
        req = request.Request(self._server_base_url(), method="GET")
        try:
            with request.urlopen(req, timeout=0.5):
                return True
        except error.HTTPError:
            return True
        except OSError:
            return False

    def _server_base_url(self) -> str:
        return f"http://{self.whisper_cpp_server_host}:{self.whisper_cpp_server_port}"

    def _write_wav(self, path: str, samples: np.ndarray) -> None:
        clipped = np.clip(samples, -1.0, 1.0)
        pcm = (clipped * 32767).astype(np.int16)
        with wave.open(path, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(self.sample_rate)
            handle.writeframes(pcm.tobytes())


def _clean_whisper_cpp_output(output: str) -> str:
    lines: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\[[^\]]+\]\s*", "", line).strip()
        if line:
            lines.append(line)
    return " ".join(lines).strip()


def _build_multipart_request(path: str, fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = f"----myvoice-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
                f"{value}\r\n".encode("utf-8"),
            ]
        )
    filename = Path(path).name
    with open(path, "rb") as handle:
        audio = handle.read()
    parts.extend(
        [
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("utf-8"),
            b"Content-Type: audio/wav\r\n\r\n",
            audio,
            b"\r\n",
            f"--{boundary}--\r\n".encode("utf-8"),
        ]
    )
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def _parse_whisper_cpp_server_response(body: str) -> str:
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return _clean_whisper_cpp_output(body)
    if isinstance(parsed, dict):
        text = parsed.get("text")
        if isinstance(text, str):
            return text.strip()
    return _clean_whisper_cpp_output(body)
