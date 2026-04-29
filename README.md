# my-voice

Local push-to-talk dictation for macOS.

The current default is **accuracy-first**:

```text
hold Shift+Esc
record the full session audio
release Shift+Esc
transcribe the full audio once with local Whisper
lightly clean the text
insert with clipboard paste
```

Chunked/VAD transcription is still present as an experimental mode, but it is disabled by default because full-session transcription is more accurate.

## Install

This project uses `uv` for the local virtual environment. The standard `python3 -m venv` path may fail with this Python installation.

```bash
uv venv --seed .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Runtime-only install:

```bash
uv pip install -e .
```

App-build dependencies:

```bash
uv pip install -e ".[app]"
```

## Terminal Run

```bash
source .venv/bin/activate
my-voice
```

The first run can take longer because Whisper model files may be downloaded.

Terminal mode requires permissions for the terminal app running it, usually iTerm or Terminal:

- System Settings -> Privacy & Security -> Accessibility
- System Settings -> Privacy & Security -> Input Monitoring
- System Settings -> Privacy & Security -> Microphone

The `.app` bundle is preferred for daily use because macOS can attach permissions to `MyVoice.app` instead of the terminal and Python executable.

## macOS App

Build the app:

```bash
chmod +x scripts/install.sh
scripts/install.sh
```

That script runs:

```bash
uv venv --seed .venv
uv pip install -e ".[app]"
chmod +x scripts/build_macos_app.sh
scripts/build_macos_app.sh
```

Run the app:

```bash
open dist/MyVoice.app
```

The app runs without a Dock icon or window. Use the log to confirm status:

```bash
tail -f ~/Library/Logs/my-voice/app.log
```

Expected startup:

```text
Starting my-voice...
Loading macOS hotkey backend...
Config: /Users/.../Library/Application Support/my-voice/config.json
Checking microphone access...
Loading ASR model. First run may download model files...
Ready. Hold <shift>+<esc> to dictate. Press Ctrl+C to quit.
```

Grant permissions to `MyVoice.app`:

- System Settings -> Privacy & Security -> Accessibility -> enable MyVoice.
- System Settings -> Privacy & Security -> Input Monitoring -> enable MyVoice.
- System Settings -> Privacy & Security -> Microphone -> enable MyVoice.

Microphone permission is different from Accessibility/Input Monitoring: macOS usually does not let you add an app manually. `MyVoice.app` must request microphone access first, then it appears in the Microphone list. MyVoice runs a short microphone access check on startup to trigger that prompt.

If you rebuild the app, macOS may treat it as a new binary. Remove the old `MyVoice` entry from Accessibility/Input Monitoring, add the current `dist/MyVoice.app` again, then quit and reopen it.

The app cannot detect the global shortcut until this warning disappears from the log:

```text
This process is not trusted! Input event monitoring will not be possible...
```

Restart after changing permissions:

```bash
pkill MyVoice
open dist/MyVoice.app
```

## Usage

1. Start `MyVoice.app`.
2. Click into a text field in another app.
3. Hold `Shift+Esc`.
4. Speak.
5. Release `Shift+Esc`.
6. Wait for the final transcription to be inserted.

Current default behavior:

- Shortcut: `Shift+Esc`.
- ASR model: `small.en`.
- Cleanup: `polished`, with deterministic spoken-correction rules first and optional Ollama cleanup second.
- Final transcription: full-session audio on release.
- Insertion: clipboard paste.
- Polished LLM cleanup: enabled when Ollama is running; otherwise the app falls back to deterministic cleanup.
- VAD/chunk transcription: off unless `enable_chunk_transcription` is set to `true`.

In the log, the most important accuracy line is:

```text
full session transcribed in ...ms: ...
```

The final inserted output is shown as:

```text
final: ...
```

## Configuration

Terminal mode config:

```text
~/.config/my-voice/config.json
```

App mode config:

```text
~/Library/Application Support/my-voice/config.json
```

Current important settings:

```json
{
  "shortcut": "<shift>+<esc>",
  "asr_model": "small.en",
  "asr_device": "cpu",
  "asr_compute_type": "int8",
  "final_transcription_mode": "full_session",
  "cleanup_mode": "polished",
  "text_insertion_method": "clipboard",
  "enable_chunk_transcription": false,
  "vad_backend": "energy",
  "vad_energy_threshold": 0.012,
  "vad_silence_ms": 1000,
  "vad_preroll_ms": 500,
  "min_chunk_ms": 800,
  "chunk_overlap_ms": 250,
  "ollama_enabled": true,
  "ollama_url": "http://127.0.0.1:11434/api/generate",
  "ollama_model": "qwen2.5:1.5b",
  "ollama_timeout_s": 1.5,
  "request_microphone_on_start": true
}
```

Shortcut examples accepted by the current hotkey backend:

```text
<shift>+<esc>
<ctrl>+<alt>+1
<f1>
```

The macOS `Fn` key is not exposed by the current hotkey backend, so shortcuts such as `Fn+Esc` cannot be configured directly.

## Accuracy Tuning

For best ASR accuracy, keep:

```json
{
  "final_transcription_mode": "full_session",
  "enable_chunk_transcription": false
}
```

If accuracy is still not good enough, try a larger Whisper model:

```json
{
  "asr_model": "medium.en"
}
```

Tradeoff: larger models are slower and use more CPU/RAM.

If you need to debug whether an error came from Whisper or cleanup, temporarily set:

```json
{
  "cleanup_mode": "fast"
}
```

`fast` mode still applies deterministic spoken-correction rules, but skips the LLM rewrite.

## Spoken Corrections

MyVoice applies simple spoken correction commands before final cleanup.

Supported commands:

```text
scratch that
start over
delete last word
delete last sentence
actually
no
rather
I mean
```

Examples:

```text
send John the deck scratch that send Sarah the deck
-> Send Sarah the deck

meet tomorrow delete last word Friday
-> Meet Friday

Send the invoice. delete last sentence Remind me tomorrow
-> Remind me tomorrow

send it to John actually Sarah
-> Send it to Sarah
```

These rules are deterministic and run locally. In `polished` mode, Ollama gets the already-corrected text and can improve punctuation/formatting.

## Audio Diagnostics

If dictation records but produces no text:

```bash
my-voice --diagnose-audio
```

The diagnostic prints:

- available audio devices
- RMS and peak audio levels
- current VAD threshold
- how many frames VAD classifies as speech

If audio is present but below threshold, lower:

```json
{
  "vad_energy_threshold": 0.006
}
```

In default accuracy mode, VAD does not control final transcription. It only matters if `enable_chunk_transcription` is `true` or when using diagnostics.

## Polished Cleanup

Polished cleanup uses a small local LLM through Ollama. It is enabled by default in the current config:

```json
{
  "cleanup_mode": "polished",
  "ollama_enabled": true
}
```

To disable it:

```json
{
  "cleanup_mode": "fast"
}
```

Install and start Ollama:

```bash
brew install --cask ollama
open -a Ollama
```

Or run the server manually:

```bash
ollama serve
```

Pull the default cleanup model:

```bash
ollama pull qwen2.5:1.5b
```

Check that Ollama is reachable:

```bash
curl http://127.0.0.1:11434/api/tags
```

Quick model test:

```bash
ollama run qwen2.5:1.5b "Clean this dictated text: um hey john send the invoice tomorrow"
```

The app calls Ollama locally:

```text
http://127.0.0.1:11434/api/generate
```

If Ollama is not running, the model is missing, or the request exceeds `ollama_timeout_s`, the app falls back to deterministic cleanup.

No paid API call is used for polishing.

## Build Scripts

Build app:

```bash
scripts/install.sh
```

Rebuild app only:

```bash
scripts/build_macos_app.sh
```

Uninstall built app artifacts:

```bash
scripts/uninstall.sh
```

Remove build artifacts plus config, logs, and `.venv`:

```bash
scripts/uninstall.sh --all
```

macOS privacy permissions must be removed manually in System Settings.

## Troubleshooting

Check app log:

```bash
tail -f ~/Library/Logs/my-voice/app.log
```

Stop app:

```bash
pkill MyVoice
```

Start app:

```bash
open dist/MyVoice.app
```

If the shortcut does nothing, check for this log warning:

```text
This process is not trusted! Input event monitoring will not be possible...
```

If present, re-add `dist/MyVoice.app` in Accessibility and Input Monitoring.

If transcription is accurate in the log but inserted text is missing characters, make sure:

```json
{
  "text_insertion_method": "clipboard"
}
```

If transcription itself is wrong, check:

```text
full session transcribed in ...ms: ...
source: ...
final: ...
```

`full session transcribed` is the raw Whisper result. `final` is the text after cleanup.
