# Local Push-to-Talk Dictation App Plan

## Goal

Build a local Wispr Flow-like dictation tool that runs in the background.

Target behavior:

```text
click into any text box
hold a shortcut key
speak naturally
release the shortcut key
cleaned transcript is inserted into the active text box
```

This plan targets the low-latency implementation from the start. Audio is not sent to ASR as one full recording except as a temporary fallback during debugging. The app captures small audio frames, uses VAD to form speech chunks, transcribes completed chunks while the shortcut is still held, and only finalizes the remaining tail audio after release.

Conceptual product pipeline:

```text
speech -> ASR -> raw text -> cleanup model/rules -> polished text
```

The design explicitly avoids this slow path:

```text
record full audio -> transcribe full audio -> run cleanup -> paste
```

The required low-latency path is:

```text
stream audio while speaking
  -> VAD groups speech into completed chunks
  -> transcribe completed chunks while the shortcut is still held
  -> store chunk transcripts as provisional text
  -> finalize only the last unstable chunk on release
  -> run final reconciliation over the complete transcript
```

## Scope

Implement a desktop background app with:

- Global push-to-talk shortcut.
- macOS as the first target platform.
- Microphone recording while the shortcut is held.
- VAD-based speech chunking.
- Background transcription of completed speech chunks while the shortcut is held.
- Local speech-to-text using `faster-whisper`.
- Lightweight text cleanup for fillers and spacing.
- Two cleanup modes:
  - Fast mode: deterministic rules only.
  - Polished mode: deterministic rules plus a small local LLM.
- Direct text insertion into the active app, with clipboard paste as fallback.
- Basic logs for debugging latency and transcription errors.

The MVP does not need:

- Live text insertion while speaking.
- Floating overlay UI.
- Cloud streaming infrastructure.
- Speaker diarization.
- Always-on wake word detection.
- Cross-device sync.

## Recommended Stack

Use Python for the MVP:

- `faster-whisper` for local Whisper transcription.
- `sounddevice` for microphone capture.
- `pynput` for global hotkey handling.
- macOS Accessibility APIs or AppleScript/System Events for text insertion.
- `pyperclip` as a fallback paste mechanism.
- Default energy-based VAD for speech/silence detection and chunk boundaries.
- Optional future upgrade: `Silero VAD` if energy-based chunking is not accurate enough.
- Optional: `llama.cpp` or `Ollama` for small local LLM cleanup.

Initial implementation assumptions:

```text
target OS: macOS
app style: background Python process
default shortcut: Ctrl+Space
shortcut configurability: required
default cleanup mode: polished
text insertion: direct injection preferred
clipboard paste: fallback only
model downloads on first run: acceptable
```

Start with this model configuration:

```python
WhisperModel("base.en", device="cpu", compute_type="int8")
```

If latency is too high, try:

```python
WhisperModel("tiny.en", device="cpu", compute_type="int8")
```

If accuracy is too low, try:

```python
WhisperModel("small.en", device="cpu", compute_type="int8")
```

Cleanup model target:

```text
Qwen2.5-1.5B-Instruct, quantized
```

Fallback cleanup model if resource use is still too high:

```text
Qwen2.5-0.5B-Instruct, quantized
```

Avoid 7B-class models in the first implementation. They may improve writing quality, but they are likely to increase memory use and release-to-text latency.

## Architecture

```text
Background app
  -> load Whisper model once at startup
  -> optionally warm the local cleanup model
  -> listen for global hotkey
  -> capture small microphone frames while hotkey is held
  -> use VAD to group speech frames into chunks
  -> transcribe completed chunks locally while hotkey is still held
  -> finalize only the remaining tail chunk on release
  -> assemble chunk transcripts in order
  -> reconcile the full transcript so earlier chunks can be corrected
  -> clean transcript with fast or polished mode
  -> insert text into active text field
```

Thread model:

```text
main thread: app lifecycle
hotkey thread: detects shortcut down/up
audio thread: records microphone samples
VAD/chunker thread: groups speech into chunks
transcription worker: runs Whisper
text insertion step: injects text directly, or uses clipboard paste as fallback
```

The audio recorder should not block on transcription. Recording must continue even if the transcription worker is busy.

Cleanup mode behavior:

```text
fast mode:
  ASR raw text -> deterministic cleanup -> insert text

polished mode:
  ASR raw text -> deterministic cleanup -> small local LLM cleanup -> insert text
```

Polished mode should be enabled by default. Fast mode must still be available as a fallback if latency, model availability, or resource use is not acceptable.

## Latency Architecture

Low latency comes from overlapping stages, not from waiting until the end and making one large operation fast.

Target pipeline:

```text
hotkey down
  -> start audio capture immediately
  -> stream small audio frames into a buffer
  -> VAD marks speech and silence
  -> completed speech chunks go to ASR
  -> ASR returns provisional raw text chunks
hotkey up
  -> finalize remaining tail audio
  -> join provisional chunks
  -> run final reconciliation and cleanup
  -> insert text
```

Audio handling rule:

```text
normal path: send VAD-completed chunks to ASR while recording continues
release path: send only the final unfinished tail chunk to ASR
fallback/debug path only: send the full recording after release
```

Important distinction:

```text
streaming internally != live insertion into the active app
```

For the first real low-latency version, the app can process audio while the user speaks but still commit text only once on release. This avoids the complexity of editing partial text inside arbitrary apps.

Completed chunk transcripts are provisional. The final tail chunk may change how earlier text should read, especially when the user self-corrects.

Example:

```text
chunk 1: "Send it to John"
chunk 2: "actually Sarah"
final text: "Send it to Sarah."
```

The app should usually correct this at the text layer during final reconciliation, not by re-transcribing all previous audio.

## Local vs Cloud Strategy

The MVP is local-only:

```text
local microphone -> local ASR -> local cleanup -> text insertion
```

This avoids API cost and privacy concerns. The tradeoff is that quality and latency depend on the user's machine.

The intended Phase 3 local architecture is:

```text
local microphone
  -> local ASR
  -> deterministic cleanup
  -> optional small local LLM cleanup
  -> insert text
```

This keeps the app private and API-cost-free while allowing a quality/latency tradeoff per user preference.

A Wispr-like cloud architecture would be:

```text
local microphone
  -> WebSocket / HTTP streaming
  -> regional ASR inference
  -> small cleanup model
  -> polished text response
```

Cloud can reduce latency for heavier models because it can use pre-warmed GPU inference, regional routing, quantized models, batching, and specialized cleanup models. That is out of scope for the MVP.

## Step 1: Push-to-Talk Audio Capture

Create a background process that listens for a global shortcut.

Example behavior:

```text
Ctrl+Space down -> start recording
Ctrl+Space up   -> stop recording
```

Implementation notes:

- Use `pynput` to detect key down and key up.
- Use `sounddevice.InputStream` to capture microphone audio.
- Capture 16 kHz mono audio if possible.
- If the device gives a different sample rate, resample before transcription.
- Capture small frames, around 100-300 ms each.
- Push frames into a VAD/chunking queue immediately.
- Keep a temporary full-session debug buffer only while developing.

Acceptance criteria:

- Pressing the shortcut starts recording.
- Releasing the shortcut stops recording.
- The app captures continuous small audio frames while the shortcut is held.
- Captured frames are available to the VAD/chunker without waiting for key release.

## Step 2: VAD-Based Speech Chunking

Use VAD to group audio frames into speech chunks.

VAD answers:

```text
does this small audio frame contain speech?
```

It does not transcribe speech. It only decides whether each frame contains speech or silence.

Use VAD to:

- Ignore silence.
- Detect when speech starts.
- Detect short pauses.
- Finalize completed speech chunks before the shortcut is released.

Example:

```text
"Hey Sarah, send me the invoice"
[700 ms pause]
"by tomorrow morning"
```

VAD should create:

```text
chunk 1: "Hey Sarah, send me the invoice"
chunk 2: "by tomorrow morning"
```

Implementation notes:

- Use a short silence threshold to close a chunk, for example 500-800 ms.
- Keep a small pre-roll buffer so the start of speech is not cut off.
- Keep a small overlap between chunks if words are getting clipped.
- Mark the current open chunk as unstable until a pause or key release finalizes it.

Acceptance criteria:

- Silence is not sent to Whisper.
- A pause finalizes a speech chunk.
- Completed chunks are available for transcription while recording continues.

## Step 3: Chunked Transcription While Speaking

Send each VAD-completed chunk to `faster-whisper` as soon as it is finalized.

Example:

```text
spoken: "um hey Sarah can you send me the invoice tomorrow"
raw transcript: "Um, hey Sarah, can you send me the invoice tomorrow."
```

Implementation notes:

- Load `WhisperModel` once at startup.
- Do not reload the model for every dictation.
- Measure transcription time with timestamps.
- Use English-only models first if the main use case is English.
- Keep a queue of finalized audio chunks.
- Run a transcription worker that consumes the queue.
- Preserve chunk order using chunk IDs.
- Do not wait for key release to transcribe completed chunks.
- On key release, finalize and transcribe only the remaining open chunk.
- Store each chunk transcript as provisional, not final.

Acceptance criteria:

- Completed speech chunks are transcribed locally while the shortcut is still held.
- No network API is required.
- Model load happens once, not per dictation.
- Releasing the shortcut does not trigger transcription of the entire recording.
- Earlier chunk transcripts remain revisable until final text insertion.

## Step 4: Stable Text Assembly and Final Reconciliation

Combine chunk transcripts without duplicates or broken phrases, then reconcile the complete transcript before insertion.

Why this matters:

```text
chunk 1: "Hey Sarah can you send"
chunk 2: "send me the invoice tomorrow"
bad join: "Hey Sarah can you send send me the invoice tomorrow"
good join: "Hey Sarah can you send me the invoice tomorrow"
```

It also allows later chunks to correct earlier chunks:

```text
chunk 1: "Schedule it for Tuesday"
chunk 2: "no Wednesday afternoon"
final text: "Schedule it for Wednesday afternoon."
```

Implementation notes:

- Keep chunk IDs and timestamps.
- Preserve order even if chunk 2 finishes before chunk 1.
- Remove duplicate words across chunk boundaries.
- Keep the final 0.5-1.0 seconds as unstable until release.
- Treat all chunk transcripts as provisional until final insertion.
- Run a final reconciliation pass over the full assembled transcript after the tail chunk is transcribed.
- Prefer text-layer reconciliation over re-transcribing all audio.
- Only re-transcribe the full audio as a debug fallback or if chunk assembly quality is unacceptable.

Acceptance criteria:

- Long dictations do not duplicate words at chunk boundaries.
- Final text reads like one coherent dictation.
- The joiner is deterministic and fast.
- Self-corrections in later chunks can update earlier text.
- Only the reconciled final text is inserted.

## Step 5: Lightweight Cleanup

Add a deterministic cleanup function before insertion.

Initial cleanup rules:

- Remove common fillers: `um`, `uh`, `erm`, `hmm`.
- Remove repeated whitespace.
- Fix spaces before punctuation.
- Capitalize the first character.
- Preserve normal words like `the`, `a`, `to`, `for`, `is`.

Important: do not remove generic NLP stop words. Dictation cleanup should remove fillers and false starts, not grammatically important words.

Example:

```text
raw: "Um, hey Sarah, can you send me the invoice tomorrow?"
clean: "Hey Sarah, can you send me the invoice tomorrow?"
```

Acceptance criteria:

- Obvious fillers are removed.
- Meaning is preserved.
- Cleanup is fast enough to run inline before insertion.
- This mode works even if no local LLM is installed or running.

## Step 6: Insert Text Into Active App

After transcription and cleanup, insert the result into the currently focused text field.

Implementation notes:

- Prefer direct text injection on macOS.
- Use macOS Accessibility permissions to interact with the focused text field where possible.
- Investigate AppleScript/System Events for keystroke-based insertion.
- Keep clipboard paste as a fallback for apps where direct insertion is unreliable.
- If clipboard fallback is used, save and restore the previous clipboard content when possible.

Acceptance criteria:

- User can click into a text field in another app.
- User dictates with the shortcut.
- The transcript appears in that text field after release.
- Direct insertion works in common macOS text fields.
- Clipboard fallback is available when direct insertion fails.

## Step 7: Polished Mode With Optional Local LLM

After the deterministic cleanup is reliable, optionally add a local LLM cleanup step.

Use it for:

- Removing false starts.
- Handling self-corrections.
- Improving punctuation.
- Making the dictated text read naturally.

Example:

```text
raw: "um hey John can you send me the invoice actually send it to Sarah by tomorrow morning thanks"
clean: "Hey Sarah, can you send me the invoice by tomorrow morning? Thanks."
```

Suggested prompt:

```text
Clean this dictated text for direct insertion into a text field.
Remove filler words, repeated words, and false starts.
Add punctuation and capitalization.
Preserve the original meaning.
Do not summarize.
Return only the final text.

Text: ...
```

Implementation notes:

- Do not put a slow LLM cleanup on the critical path by default.
- Make it configurable.
- Keep deterministic cleanup as the fallback.
- Use a small model and a constrained prompt.
- Keep context tiny: only the current dictation, not chat history.
- Start with `Qwen2.5-1.5B-Instruct` quantized.
- If resource use is too high, fall back to `Qwen2.5-0.5B-Instruct` quantized.
- Expose a simple setting for cleanup mode: `fast` or `polished`.
- Add a timeout for polished mode. If the LLM is too slow, insert the deterministic cleanup result.
- Log local LLM latency separately from ASR latency.
- Default to polished mode when the local cleanup model is installed and responsive.

Acceptance criteria:

- Cleanup improves natural speech without changing meaning.
- The app still works if the LLM is disabled.
- Latency remains acceptable.
- Fast mode and polished mode can be compared on the same dictated phrase.
- Polished mode failure does not block text insertion.

## Future: Streaming Cleanup

After chunked ASR is reliable, experiment with cleanup on stable partial text.

Possible flow:

```text
ASR partial text -> mark as unstable
ASR final phrase -> mark as stable
stable phrase -> cleanup worker
release -> final reconciliation pass over joined text
```

Avoid sending every partial ASR update to a cleanup model. Partial transcripts can change, and cleaning unstable text can introduce flicker, duplicate work, and incorrect corrections.

Example:

```text
partial: "send it to John"
later:   "send it to John no actually Sarah"
final:   "Send it to Sarah."
```

The cleanup layer should operate on stable chunks for previews, but the committed output should always come from the final reconciled transcript.

## Latency Strategy

Main rules:

- Load the transcription model once at startup.
- Use a small model first: `base.en` or `tiny.en`.
- Use CPU int8 quantization for the MVP.
- Record immediately on key down.
- Capture small audio frames, around 100-300 ms.
- Avoid sending silence to Whisper.
- Transcribe completed chunks while the key is still held.
- Keep the last short tail of audio unstable until release.
- Keep chunk transcripts provisional until final reconciliation.
- Keep cleanup lightweight before text insertion.
- Keep polished mode as the default, but fallback to fast mode on timeout or model error.
- Add a timeout around local LLM cleanup.
- Log timing for every stage.

Track these timings:

```text
hotkey_down_to_recording_started_ms
recording_duration_ms
audio_finalize_ms
vad_chunking_ms
chunk_queue_wait_ms
transcription_ms
text_assembly_ms
final_reconciliation_ms
deterministic_cleanup_ms
local_llm_cleanup_ms
text_insertion_ms
total_release_to_text_ms
```

Initial target:

```text
short dictation: text appears within 0.5-2.0 seconds after release
```

Later target:

```text
chunked dictation: text appears within 0.2-0.8 seconds after release
```

Expected latency shape:

```text
streaming/chunked ASR while speaking: near-zero perceived cost
final tail ASR after release: 100-500 ms depending on model and hardware
deterministic cleanup: <50 ms
optional local LLM cleanup: model-dependent, likely 200 ms to multiple seconds
text insertion: <100 ms
```

Cleanup mode targets:

```text
fast mode: prioritize release-to-text latency
polished mode: default mode; allow modest extra latency for better formatting and false-start cleanup
```

## Risks and Tradeoffs

- `faster-whisper` is easy for Python prototyping but can be heavier to package.
- `whisper.cpp` may be better later for a polished native Mac app, especially on Apple Silicon with Metal.
- Direct text injection is preferred but may require macOS Accessibility permissions and can vary by target app.
- Clipboard paste is simpler but temporarily overwrites the clipboard, so it should remain a fallback.
- Live insertion into arbitrary apps is difficult because partial transcripts can be revised.
- Removing stop words is risky; remove fillers instead.
- Local LLM cleanup can improve quality but may add noticeable latency.
- Starting with live insertion would make correctness much harder because the app must revise already-inserted text.
- Cloud streaming could improve quality/latency with stronger models, but adds infrastructure, privacy, and operating cost.
- Polished mode must have a timeout and fallback so a slow local LLM does not make dictation feel broken.

## Build Order

1. Create a CLI/background Python app.
2. Load `WhisperModel` once on startup.
3. Add configuration for shortcut and cleanup mode.
4. Implement configurable `Ctrl+Space` hotkey down/up detection.
5. Capture small audio frames while the hotkey is held.
6. Add VAD-based speech chunking.
7. Queue completed speech chunks for transcription while recording continues.
8. On release, finalize and transcribe only the remaining open chunk.
9. Assemble chunk transcripts in order.
10. Run final reconciliation over the complete assembled transcript.
11. Clean transcript with deterministic rules.
12. Add local LLM cleanup using a small quantized model.
13. Default to polished mode with timeout fallback to fast mode.
14. Insert text directly into the active text field.
15. Add clipboard fallback for apps where direct insertion fails.
16. Add timing logs.
17. Add optional floating preview for partial transcripts.
18. Consider replacing `faster-whisper` with `whisper.cpp` for packaging/performance.
19. Consider cloud streaming only if local quality/latency is not good enough.

## Definition of Done for Low-Latency MVP

The low-latency MVP is done when:

- The app runs in the background.
- A configurable global shortcut controls recording.
- Audio is captured in small frames while the shortcut is held.
- VAD converts frames into completed speech chunks.
- Completed chunks are transcribed while recording continues.
- Releasing the shortcut finalizes only the remaining tail chunk.
- Chunk transcripts are provisional until final reconciliation.
- Later chunks can correct earlier text before insertion.
- Speech is transcribed locally.
- Cleaned text is inserted into the active text box.
- The model is not reloaded for each dictation.
- A short dictation appears quickly after release because most completed chunks were already processed.
- Polished mode is the default when the local cleanup model is available.
- Fast cleanup mode works as a fallback without any local LLM.
- The app logs enough timing data to identify latency bottlenecks.

## Definition of Done for Phase 3

Phase 3 is done when:

- The app supports `fast` and `polished` cleanup modes.
- Fast mode uses deterministic cleanup only.
- Polished mode uses deterministic cleanup plus a small local LLM.
- Polished mode is enabled by default.
- The recommended polished model is `Qwen2.5-1.5B-Instruct` quantized.
- Polished mode has a timeout and falls back to fast mode.
- Both modes run locally without paid API calls.
- Logs clearly separate ASR time, deterministic cleanup time, local LLM cleanup time, and text insertion time.
