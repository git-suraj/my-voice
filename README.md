# my-voice

Local push-to-talk dictation for macOS.

The current default is **accuracy-first**:

```text
hold Shift+Esc
record the full session audio
release Shift+Esc
transcribe the full audio once with local Whisper
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

Each dictation also prints a timing line:

```text
timing: recording=...ms asr=...ms assemble=...ms reconcile=...ms deterministic_cleanup=...ms llm_cleanup=...ms cleanup_total=...ms insertion=...ms total=...ms llm_used=True
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

The menu-bar item also has a `Quit MyVoice` menu item.

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
  "ollama_timeout_s": 4.0,
  "feedback_enabled": true,
  "feedback_mode": "notification",
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
sorry
no
not
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

These rules are deterministic and run locally.

In `polished` mode, Ollama receives both:

```text
Raw transcript
Rule-cleaned draft
```

The prompt asks the model to resolve broader natural self-corrections, including:

```text
that's not what I meant
what I meant was
make that
instead
```

Examples intended for polished mode:

```text
I need the report by Tuesday that's not what I meant by Thursday
-> I need the report by Thursday.

book a flight to London make that Paris next week
-> Book a flight to Paris next week.
```

The LLM prompt is intentionally conservative: it should apply corrections and formatting, but not summarize, expand, or invent details.

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

The installer also resets stale macOS permission entries for the local build, then prints next steps for checking status, watching logs, and re-enabling permissions.

This creates `dist/MyVoice.app` and registers:

```text
~/Library/LaunchAgents/com.myvoice.app.plist
```

macOS will start MyVoice when you log in and restart it if it exits. After sleep/wake, the process should continue running; if Core Audio temporarily fails after wake, the app logs the microphone error and the next shortcut press can retry.

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

macOS privacy permissions must be removed manually in System Settings.

If the `MV` menu-bar item remains after uninstall, a stale MyVoice helper process is still running. Run:

```bash
scripts/uninstall_launch_agent.sh
pkill -f "MyVoice.app/Contents/MacOS/MyVoice"
```

The uninstall scripts include this cleanup, but macOS can leave a menu-bar item visible briefly until the process fully exits.

## Clean Reinstall

Use this when macOS permissions look stale, the shortcut is not trusted, or you want a clean local setup.

Uninstall everything:

```bash
scripts/uninstall.sh --all
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

If the shortcut does nothing, check for this log warning:

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
