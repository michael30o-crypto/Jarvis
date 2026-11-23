# Jarvis Test Baseline

## Environment observed

- Windows, Python 3.12.10 in the project venv
- `gradio_client` 2.2.0 in the venv
- Ollama 0.40.17
- Local model catalog includes `qwen3:8b` (5.2 GB)
- Separate Qwen TTS environment observed with `qwen_tts` 0.1.1, PyTorch 2.11.0+cu128, and Transformers 4.57.3
- OpenWhispr is installed locally; its bridge config/token are outside the repository
- RTX 5060 with 8 GB VRAM (hardware stated in the existing README)
- No project requirements/lock file or automated CI workflow exists

The environment versions above are a snapshot. They are not yet a supported-version declaration or reproducible installation manifest.

## Baseline command and result

Command:

```powershell
& 'C:\Users\micha\Jarvis\venv\Scripts\python.exe' -m unittest discover -s 'C:\Users\micha\Jarvis' -p 'test_*.py' -v
```

Result: **3 tests passed** in 0.061 seconds.

| Test | Result | Coverage |
|---|---|---|
| `test_non_http_url_is_refused` | Pass | Refuses a `file:` URL |
| `test_plain_chat_is_saved` | Pass | Mocks Ollama and verifies user/assistant message persistence |
| `test_tasks_are_persisted` | Pass | Adds and lists a task in a temporary SQLite DB |

The suite sets `JARVIS_SKIP_GPU_HANDOFF=1` and uses a temporary DB. It does not exercise live model inference or process management.

## Batch 1 post-change verification

- The same unittest discovery command passed again: **3 tests passed**.
- `jarvis_v2` passed `compileall` and a runtime import/construction smoke test for the new contract types.
- Both JSON files parsed, and manual checks confirmed the example's schema version, local-only flags, loopback backend URLs, and local model references.
- Full Draft 2020-12 schema validation was not run because no JSON Schema validator is installed in the existing venv. No dependency was added just for this scaffold.
- The already-running legacy app's `GET /api/state` endpoint returned HTTP 200 after the changes (`qwen3:8b`, `GPU ready, model idle`).

## Existing runtime smoke test

`GET http://127.0.0.1:8765/api/state` returned HTTP 200 before Batch 1 changes and identified `qwen3:8b` / `GPU ready, model idle`. This proves only that the local app state endpoint responded; it does not prove a live chat, microphone, transcription, or cloned-voice request.

## Not covered / not run

- Live Ollama response, tool-call loop, or model cancellation
- Microphone permissions/capture and OpenWhispr transcription
- Qwen3-TTS generation, saved voice setup, replay, or system speech
- App process launch/termination and GPU handoff
- Browser UI behavior, responsive layout, accessibility, or JavaScript error paths
- Migration/backup/restore, semantic retrieval, or concurrent DB load
- llama.cpp, scheduler, capability providers, C++ service, or cross-backend integration (not implemented)

These are not available baseline tests in the repository. They require separate local services, audio devices, model assets, or new components; no cloud test was used.

## Preliminary performance observation

Two short warm cloned-voice calls in an earlier local probe reported 8.30 s and 8.52 s in the app's `voice_ms` metric. They are ad hoc samples with different short phrases, not a statistically valid baseline or an acceptance target. Future reports must separate cold model-load time from warm generation, report audio duration/real-time factor, and include p50/p95 across repeated trials.

## Required test layers for future batches

1. **Unit:** config validation, resource estimator, policy decisions, memory queries/migrations, and adapter error handling.
2. **Contract:** fake Ollama/llama.cpp/speech/native providers; version and error shape checks.
3. **Integration:** loopback-only local services with explicitly installed models; disposable DB and generated audio.
4. **Desktop:** approved app launches, URL policy, microphone and browser speech in Windows; test with fakes first.
5. **Performance:** cold/warm model-load and first-token latency, tokens/sec, speech first-audio latency and real-time factor, ASR latency, memory search p50/p95, peak VRAM/RAM, and scheduler admission/queue behavior.
6. **Release:** complete compatibility checklist, no unexpected egress, no model/data/secret files in Git, and `run-jarvis.bat` smoke test.
