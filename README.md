# my-voice

Local push-to-talk dictation for macOS.

The current default is **accuracy-first**:

```text
triple-tap Shift
record the full session audio
press Shift once to stop
transcribe the full audio once with local Whisper
apply personal corrections
apply deterministic cleanup and optional local LLM cleanup
insert with clipboard paste
```

Chunked/VAD transcription is still present as an experimental mode, but it is disabled by default because full-session transcription is more accurate. Reconciliation is only used for chunk-only fallback text, not for the default full-session transcript.

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

By default, `scripts/install.sh` also checks Ollama, starts `ollama serve` if needed, pulls `qwen2.5:1.5b` if missing, and warms the model for polished cleanup.

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
Loading ASR backend: faster-whisper
Loading ASR model. First run may download model files...
Ready. Triple-tap Shift to record. Press Shift again to stop. Press Ctrl+C to quit.
```

Grant permissions to `MyVoice.app`:

- System Settings -> Privacy & Security -> Accessibility -> enable MyVoice.
- System Settings -> Privacy & Security -> Input Monitoring -> enable MyVoice.
- System Settings -> Privacy & Security -> Microphone -> enable MyVoice.

Microphone permission is different from Accessibility/Input Monitoring: macOS usually does not let you add an app manually. `MyVoice.app` must request microphone access first, then it appears in the Microphone list. MyVoice runs a short microphone access check on startup to trigger that prompt.

If you rebuild the app, macOS may treat it as a new binary. Remove the old `MyVoice` entry from Accessibility/Input Monitoring, add the current `dist/MyVoice.app` again, then quit and reopen it.

The app cannot detect the Shift trigger until this warning disappears from the log:

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
3. Triple-tap `Shift`.
4. Speak.
5. Press `Shift` once to stop.
6. Wait for the final transcription to be inserted.

Current default behavior:

- Trigger: triple-tap `Shift` to start, single `Shift` tap to stop.
- ASR backend: `faster-whisper`.
- ASR model: `small`.
- Cleanup: `polished`, with deterministic spoken-correction rules first and optional Ollama cleanup second.
- Personal corrections: enabled, editable from the `MV` menu.
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

Each dictation also prints a timing line:

```text
timing: recording=...ms asr_backend=faster-whisper asr=...ms assemble=...ms reconcile=...ms deterministic_cleanup=...ms llm_cleanup=...ms cleanup_total=...ms insertion=...ms total=...ms llm_used=True
```

In the default full-session path, `reconcile=0ms` because the raw full-session Whisper result goes directly into cleanup. Reconciliation is only used when the app has to fall back to assembled chunk text.

## UI Feedback

MyVoice runs in the background and shows a menu-bar status item:

```text
MV    idle
REC   recording
WAIT  processing/transcribing/cleaning
ERR   error
```

The menu-bar item also has:

```text
Record    Triple-tap Shift
Stop      Shift
Personal Corrections...
Open Logs    open ~/Library/Logs/my-voice in Finder
Quit MyVoice
```

The menu `Record` and `Stop` items are useful when your hands are not free for the keyboard trigger. `Personal Corrections...` opens a local editor page for terms that should always be replaced before cleanup.

If you quit from the `MV` menu, start it again with:

```bash
scripts/restart_launch_agent.sh
```

The app can also show macOS notifications for activity:

- recording started: `Recording`
- recording stopped: `Processing`
- text inserted: `Inserted`
- microphone start failed: `Microphone error`

Configure this in the app config:

```json
{
  "feedback_enabled": true,
  "feedback_mode": "notification"
}
```

Supported feedback modes:

```text
notification
sound
both
```

To disable feedback:

```json
{
  "feedback_enabled": false
}
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
  "trigger_mode": "triple_tap_shift",
  "shift_tap_count": 3,
  "shift_tap_window_ms": 1500,
  "shift_stop_grace_ms": 450,
  "asr_backend": "faster-whisper",
  "asr_model": "small",
  "asr_device": "cpu",
  "asr_compute_type": "int8",
  "whisper_cpp_binary": "whisper-cli",
  "whisper_cpp_model": "",
  "whisper_cpp_extra_args": ["-nt"],
  "whisper_cpp_server_binary": "whisper-server",
  "whisper_cpp_server_host": "127.0.0.1",
  "whisper_cpp_server_port": 8178,
  "whisper_cpp_server_start": true,
  "whisper_cpp_server_timeout_s": 30.0,
  "whisper_cpp_server_extra_args": [],
  "final_transcription_mode": "full_session",
  "cleanup_mode": "polished",
  "text_insertion_method": "clipboard",
  "mark_clipboard_transient": true,
  "restore_clipboard": true,
  "refocus_before_insert": true,
  "personal_corrections_enabled": true,
  "personal_corrections_path": "",
  "personal_corrections_editor_port": 8765,
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
  "ollama_timeout_s": 4.0,
  "feedback_enabled": true,
  "feedback_mode": "notification",
  "request_microphone_on_start": true
}
```

Trigger settings:

- `trigger_mode`: currently `triple_tap_shift`.
- `shift_tap_count`: number of standalone Shift taps needed to start recording.
- `shift_tap_window_ms`: maximum time window for the Shift taps.
- `shift_stop_grace_ms`: short delay after starting so the final start tap does not immediately stop recording.

## Personal Corrections

Use this for words or phrases that Whisper often hears incorrectly.

Open the editor from:

```text
MV -> Personal Corrections...
```

The editor runs locally at `http://127.0.0.1:8765/` and saves beside the app config:

```text
~/Library/Application Support/my-voice/config.json
~/Library/Application Support/my-voice/corrections.json
```

Example corrections:

```text
cong          -> Kong
kong connect  -> Kong Konnect
control plane -> Control Plane
cube ctl      -> kubectl
```

The app applies corrections before deterministic cleanup and LLM cleanup:

```text
ASR transcript -> personal corrections -> deterministic cleanup -> optional LLM cleanup -> insertion
```

Corrections can be single words or multi-word phrases. They use whole-word and whole-phrase matching. This means `cong` can become `Kong`, but `congress` will not become `Kongress`. Longer phrases are applied first, so `kong connect` can become `Kong Konnect` before a separate `kong` rule is considered.

Config:

```json
{
  "personal_corrections_enabled": true,
  "personal_corrections_path": "",
  "personal_corrections_editor_port": 8765
}
```

Clipboard insertion settings:

- `text_insertion_method`: `clipboard` is the most reliable option on macOS. `direct` uses AppleScript keystrokes and avoids the clipboard, but it is less reliable for long text and punctuation. `auto` tries direct insertion first and falls back to clipboard paste.
- `mark_clipboard_transient`: adds macOS pasteboard marker types to MyVoice's temporary clipboard entry so clipboard managers such as Maccy can ignore dictated text. The real paste payload remains normal string text. The marker types are `org.nspasteboard.TransientType`, `org.nspasteboard.AutoGeneratedType`, and `org.nspasteboard.ConcealedType`.
- `restore_clipboard`: restores the previous clipboard text after MyVoice pastes the dictated text. The restored text is also marked as a transient restore to avoid duplicate clipboard-history entries where supported.
- `refocus_before_insert`: remembers the last non-MyVoice foreground app and reactivates it before pasting. This is important when you stop recording from the `MV` menu, because opening the menu can steal focus from the text field.

## Accuracy Tuning

For best ASR accuracy, keep:

```json
{
  "final_transcription_mode": "full_session",
  "enable_chunk_transcription": false
}
```

The default `small` model is multilingual and is a latency/accuracy compromise for Indian English, names, and mixed phrasing. If accuracy is still not good enough, try a larger Whisper model:

```json
{
  "asr_model": "medium"
}
```

Tradeoff: larger models are slower and use more CPU/RAM.

## ASR Backends

MyVoice supports three ASR backend modes:

```text
faster-whisper      default Python backend, simple setup, CPU-friendly with int8
whisper-cpp         simple whisper.cpp CLI backend, starts whisper-cli per recording
whisper-cpp-server  deeper whisper.cpp backend, keeps whisper-server/model warm
```

The app pipeline stays the same for all three:

```text
record audio -> transcribe -> deterministic cleanup -> optional Ollama cleanup -> insert text
```

Only the ASR implementation changes.

Default faster-whisper config:

```json
{
  "asr_backend": "faster-whisper",
  "asr_model": "small",
  "asr_device": "cpu",
  "asr_compute_type": "int8"
}
```

Optional whisper.cpp config:

```json
{
  "asr_backend": "whisper-cpp",
  "whisper_cpp_binary": "/path/to/whisper-cli",
  "whisper_cpp_model": "/path/to/ggml-small.bin",
  "whisper_cpp_extra_args": ["-nt"]
}
```

`whisper_cpp_binary` must point to a working `whisper-cli` executable. `whisper_cpp_model` must point to a local whisper.cpp model file. The default extra arg `-nt` disables timestamps so MyVoice receives plain text.

This mode shells out to `whisper-cli` for each final recording. That is useful for comparing accuracy and total timing, but it is not the lowest-latency design because the process starts for every dictation.

Deeper whisper.cpp server config:

```json
{
  "asr_backend": "whisper-cpp-server",
  "whisper_cpp_server_binary": "/path/to/whisper-server",
  "whisper_cpp_model": "/path/to/ggml-small.bin",
  "whisper_cpp_server_host": "127.0.0.1",
  "whisper_cpp_server_port": 8178,
  "whisper_cpp_server_start": true,
  "whisper_cpp_server_timeout_s": 30.0,
  "whisper_cpp_server_extra_args": []
}
```

In `whisper-cpp-server` mode, MyVoice checks `http://127.0.0.1:8178` on startup. If nothing is listening and `whisper_cpp_server_start` is `true`, it starts `whisper-server` with the configured model and waits for it to become ready. Each recording is sent to:

```text
POST /inference
multipart file=<temporary wav>
response_format=json
language=en
temperature=0.0
```

This keeps the ASR model loaded between dictations, which should remove most process/model startup overhead compared with `whisper-cpp`.

Use the log timing line to compare:

```text
timing: recording=...ms asr_backend=whisper-cpp-server asr=...ms cleanup_total=...ms insertion=...ms total=...ms
```

If you need to debug whether an error came from Whisper or cleanup, temporarily set:

```json
{
  "cleanup_mode": "fast"
}
```

`fast` mode still applies deterministic spoken-correction rules, but skips the LLM rewrite.

## Spoken Corrections

MyVoice uses a hybrid correction strategy:

```text
deterministic cleanup for safe local edits
LLM cleanup for broader natural self-corrections
validation before accepting the LLM output
```

The deterministic layer is intentionally conservative. It handles commands that are predictable and low-risk.

Deterministic commands:

```text
scratch that
start over
delete last word
delete last sentence
actually
sorry
no
rather
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

These rules are deterministic and run locally.

Broader corrections are handled in `polished` mode by Ollama, because they require semantic understanding:

```text
sorry, I mean ...
sorry, I meant ...
that's not what I meant ...
what I meant was ...
make that ...
instead ...
actually ...
```

Ollama receives both:

```text
Raw transcript
Rule-cleaned draft
```

The prompt asks the model to return structured JSON:

```json
{
  "final_text": "...",
  "corrections_applied": true,
  "confidence": "high"
}
```

Examples intended for polished mode:

```text
Schedule a meeting with Sara. Sorry, I meant Roger at 10 a.m. tomorrow.
-> Schedule a meeting with Roger at 10 a.m. tomorrow.

Okay, so I'm just checking if this is working. Sorry, I mean if this is not working.
-> Okay, so I'm just checking if this is not working.
```

The app validates the LLM response before accepting it. It rejects empty output, malformed JSON, low-confidence corrections, suspiciously large drops, and outputs that still contain unapplied correction phrases such as `I mean`.

The LLM is also responsible for removing trailing meta-speech when you abandon a thought or think out loud at the end of a dictation. For example:

```text
Make sure that the README is updated even with the blank audio thing. There was another thing which I wanted to do which is... What was that? Yeah, I think that's it.
-> Make sure that the README is updated even with the blank audio thing.
```

The LLM also handles spoken lists.

Numbered list example:

```text
Okay, number one I want to review the deck. Number two I want to send the notes.
-> 1. I want to review the deck.
   2. I want to send the notes.
```

Task list example:

```text
I want to make a house then paint it.
-> I want to:
   - make a house
   - paint it
```

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

If recording fails immediately with:

```text
recording start failed: Could not open microphone input stream: ...
```

then macOS or PortAudio could not open the microphone. Common causes:

- another app is using the microphone in a way that blocks access
- macOS Microphone permission for `MyVoice.app` is missing or stale
- the selected default input device changed or became unavailable
- Core Audio is temporarily stuck

Try:

```bash
my-voice --diagnose-audio
```

Then quit apps using the microphone, re-open `dist/MyVoice.app`, or remove and re-add `dist/MyVoice.app` under:

```text
System Settings -> Privacy & Security -> Microphone
```

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

`scripts/install.sh` can start the Ollama server automatically after Ollama is installed.

Or run the server manually:

```bash
ollama serve
```

Pull the default cleanup model:

```bash
ollama pull qwen2.5:1.5b
```

`scripts/install.sh` also pulls and warms this model by default. To skip Ollama setup:

```bash
scripts/install.sh --no-ollama
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

If Ollama is not running, the model is missing, or the request exceeds `ollama_timeout_s`, the app falls back to deterministic cleanup and logs:

```text
llm cleanup fallback: ...
```

No paid API call is used for polishing.

## Build Scripts

Install dependencies, build the app, and register it as a long-running background app:

```bash
scripts/install.sh
```

The installer also checks Ollama/Qwen, resets stale macOS permission entries for the local build, then prints next steps for checking status, watching logs, and re-enabling permissions.

This creates `dist/MyVoice.app` and registers:

```text
~/Library/LaunchAgents/com.myvoice.app.plist
```

macOS will start MyVoice when you log in and restart it if it exits. After sleep/wake, the process should continue running; if Core Audio temporarily fails after wake, the app logs the microphone error and the next trigger can retry.

The LaunchAgent starts `dist/MyVoice.app` through macOS `open`, not by running the internal executable directly. This keeps macOS privacy permissions tied to the same app bundle shown in System Settings.

When permissions are reset, MyVoice is intentionally stopped. Re-enable MyVoice in Accessibility, Input Monitoring, and Microphone first, then start it:

```bash
scripts/restart_launch_agent.sh
```

After start, look for the `MV` menu-bar item. It changes to `REC` while recording and `WAIT` while processing.

Build without installing the LaunchAgent:

```bash
scripts/install.sh --no-launch-agent
```

Build without resetting macOS permission entries:

```bash
scripts/install.sh --no-permission-reset
```

Build without checking or starting Ollama:

```bash
scripts/install.sh --no-ollama
```

Use a different Ollama cleanup model:

```bash
OLLAMA_MODEL=qwen2.5:3b scripts/install.sh
```

Rebuild app only:

```bash
scripts/build_macos_app.sh
```

Install or refresh only the LaunchAgent:

```bash
scripts/install_launch_agent.sh
```

Check background status:

```bash
scripts/launch_agent_status.sh
```

If LaunchAgent installation fails with `Bootstrap failed: 5`, the installer prints the exact `launchctl` output and diagnostic commands. This usually means launchd has stale state for the service or macOS rejected the plist/app path.

Stop and remove the background LaunchAgent:

```bash
scripts/uninstall_launch_agent.sh
```

Uninstall built app artifacts:

```bash
scripts/uninstall.sh
```

Remove build artifacts plus config, logs, and `.venv`:

```bash
scripts/uninstall.sh --all
```

`--all` preserves whisper.cpp model files under:

```text
~/Library/Application Support/my-voice/models/
```

This avoids re-downloading large `ggml-*.bin` files after every clean reinstall.

To explicitly remove those model files too:

```bash
scripts/uninstall.sh --models
```

macOS privacy permissions must be removed manually in System Settings.

If the `MV` menu-bar item remains after uninstall, a stale MyVoice helper process is still running. Run:

```bash
scripts/uninstall_launch_agent.sh
pkill -f "MyVoice.app/Contents/MacOS/MyVoice"
```

The uninstall scripts include this cleanup, but macOS can leave a menu-bar item visible briefly until the process fully exits.

## Clean Reinstall

Use this when macOS permissions look stale, the keyboard trigger is not trusted, or you want a clean local setup.

Uninstall everything:

```bash
scripts/uninstall.sh --all
```

This removes the app build, config, logs, and `.venv`, but keeps downloaded whisper.cpp models in:

```text
~/Library/Application Support/my-voice/models/
```

Then manually remove or disable old `MyVoice` entries from:

```text
System Settings -> Privacy & Security -> Accessibility
System Settings -> Privacy & Security -> Input Monitoring
System Settings -> Privacy & Security -> Microphone
```

Install again:

```bash
scripts/install.sh
```

The installer builds the app and resets stale macOS permission entries. After reset, MyVoice is intentionally not started yet.

Enable `MyVoice` in:

```text
System Settings -> Privacy & Security -> Accessibility
System Settings -> Privacy & Security -> Input Monitoring
System Settings -> Privacy & Security -> Microphone
```

Then start MyVoice:

```bash
scripts/restart_launch_agent.sh
```

You should see `MV` in the macOS menu bar. If you quit it from the `MV` menu, launch it again with:

```bash
scripts/restart_launch_agent.sh
```

Check status:

```bash
scripts/launch_agent_status.sh
```

Watch logs:

```bash
tail -f ~/Library/Logs/my-voice/app.log
```

Expected good startup: the log does not show:

```text
This process is not trusted!
```

Expected UI: the menu bar shows `MV` when idle, `REC` while recording, and `WAIT` while processing.

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
scripts/restart_launch_agent.sh
```

The menu-bar item should appear as `MV`. If you do not see it, check hidden menu-bar items or menu-bar overflow utilities.

If the Shift trigger does nothing, check for this log warning:

```text
This process is not trusted! Input event monitoring will not be possible...
```

If present, re-add `dist/MyVoice.app` in both Accessibility and Input Monitoring. The app is ad-hoc signed during local builds, so macOS can keep a stale permission entry after a rebuild even when `MyVoice` appears enabled in System Settings.

To clear stale macOS permission entries:

```bash
scripts/reset_macos_permissions.sh
```

Then restart the LaunchAgent and re-enable MyVoice in:

```text
System Settings -> Privacy & Security -> Accessibility
System Settings -> Privacy & Security -> Input Monitoring
System Settings -> Privacy & Security -> Microphone
```

After re-enabling permissions, restart MyVoice:

```bash
scripts/restart_launch_agent.sh
```

If transcription is accurate in the log but inserted text is missing characters, make sure:

```json
{
  "text_insertion_method": "clipboard"
}
```

If the log shows an AppleScript paste failure like:

```text
insertion failed: ... osascript ... exited 1
```

then ASR and cleanup already succeeded, but macOS blocked the paste action. The app leaves the final text on the clipboard when clipboard insertion was attempted, so you can paste manually with `Cmd+V`.

Check that `dist/MyVoice.app` is enabled under:

```text
System Settings -> Privacy & Security -> Accessibility
System Settings -> Privacy & Security -> Input Monitoring
```

If transcription itself is wrong, check:

```text
full session transcribed in ...ms: ...
source: ...
final: ...
timing: ...
```

`full session transcribed` is the raw Whisper result. `source` is the text sent into cleanup. `final` is the inserted text after deterministic and optional LLM cleanup. `timing` shows where latency was spent.

If `timing` shows `llm_used=False`, the LLM did not return usable text. Check for a nearby `llm cleanup fallback:` line. A value like `llm_cleanup=1504ms` with a `1.5` second timeout usually means Ollama timed out.
