# Existing Feature Compatibility Checklist

This is the migration gate for replacing parts of the existing app. "Present" means the source currently implements the feature; it does not imply full integration testing. Batch 1 does not change runtime code.

| Existing feature | Current source/dependency | Baseline verification | Required before v2 default |
|---|---|---|---|
| Windows startup and dashboard | `run-jarvis.bat`, `jarvis.py`, `web/index.html`; Ollama and Python venv | Current `/api/state` smoke test returned HTTP 200; launcher file unchanged | Launch on a clean Windows profile; confirm browser, loopback bind, readiness, shutdown, and restart |
| Text conversation and history | Ollama `qwen3:8b`; SQLite `messages` table | Unit test mocks model and checks user/assistant persistence | Local-model integration plus context-order, error, cancellation, and migration tests |
| Tasks and completion | `run_tool` and SQLite `tasks` table | `test_tasks_are_persisted` passes | API and UI flows, persistence across restart, input validation |
| Notes and recall | `run_tool` and SQLite `notes` table | Source-audited; no dedicated automated test | Save/list limits, persistence, authorization, migration |
| Allowlisted app launching | `APP_COMMANDS`, Windows `subprocess.Popen` | Source-audited; no process-launch test | Test each allowlisted provider with fakes; require policy grant where configured; deny unknown IDs |
| HTTP(S) URL opening | URL parser and `webbrowser.open` | `test_non_http_url_is_refused` passes | Validate approval, malformed/local-address policy, and no navigation on denied calls |
| Microphone capture | Browser `MediaRecorder`, `getUserMedia`, selectable device and gain | Source-audited; no browser/device integration test | Browser permission and device tests; verify cleanup on stop/error and privacy copy |
| Transcription | OpenWhispr local bridge; token from user config; temporary audio file deleted in `finally` | No ASR integration test; user token is not in repository | Mock bridge contract, local-service integration, audio limit/type/error tests |
| System speech | Browser `speechSynthesis`, voice/rate/pitch settings | Source-audited; no browser speech test | Browser test for voice availability, mute, replay, and fallback errors |
| Cloned voice and saved voices | Qwen3-TTS local Gradio service; `data/voices`, prompt/reference audio, `voice.json` | No voice/model integration test; user data excluded from Git | Disposable sample tests plus voice-library migration and cache tests; preserve original samples/transcripts |
| Voice replay and output gain | Dashboard replay buttons and Web Audio API | Source-audited; no browser audio test | Browser test and end-to-end playback check |
| GPU handoff/telemetry | `nvidia-smi`, Ollama CLI, process cleanup script | Unit tests skip GPU handoff; one current dashboard state smoke test | Fake process tests, real hardware stress test, no unintended process termination |
| Responsive dashboard and visualization | Single-page HTML/CSS/JS and Canvas | Source-audited; no automated browser suite | Desktop/mobile browser regression and accessibility checks |
| Local-only behavior | Loopback URLs in current Python constants | Source-audited; no network-egress test | Test rejects non-loopback config and prove no inference/telemetry egress |

## Data preservation requirements

- Keep existing `data/jarvis.sqlite3`, `voice.json`, voice prompts/references, and audio cache intact.
- Keep the legacy SQLite schema readable until a copy-first migration is verified.
- Do not add any file from `data/`, `venv/`, local model caches, or credentials to a commit.
- New tests use temporary directories and generated fixtures, not the user's saved voice or memory.

## Current checklist status

- [x] Existing feature set and source owners audited.
- [x] Three current unit tests pass (details in [TEST_BASELINE.md](TEST_BASELINE.md)).
- [x] Legacy entry point and startup script remain untouched by Batch 1.
- [ ] Each feature has the v2 automated verification required above.
- [ ] V2 passes complete desktop, voice, migration, and GPU-scheduler parity tests.
