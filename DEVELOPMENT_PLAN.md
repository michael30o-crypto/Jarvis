# Jarvis 2.0 Development Plan

## Current batch

Batch 1 is architecture, audit, compatibility mapping, test baseline, and inert scaffolding on `jarvis-2.0-architecture`. The legacy `jarvis.py` and `run-jarvis.bat` remain the runtime entry points. The new package is not imported by the current application.

## Proposed implementation order

| Batch | Deliverable | Depends on |
|---|---|---|
| 1 | Architecture, contracts, config schema, compatibility checklist, baseline tests/results | Existing repository audit |
| 2 | Config loader/validator, runtime capability providers, policy model, fake providers, API version skeleton | Batch 1 contracts |
| 3 | Ollama and llama.cpp adapters, model catalog, scheduler/resource reservations, queue/cancel semantics | Batch 2 capability and backend contracts |
| 4 | Versioned memory repository and copy-first migration from current SQLite; optional local semantic index behind config | Batch 2 memory contract; no destructive migration |
| 5 | Tool registry, approval grants, Windows providers, origin/CSRF/auth protection for mutating API routes | Batch 2 permission contract |
| 6 | ASR/TTS provider adapters, chunk-capable speech API, voice library migration/compatibility | Batch 2 speech contract |
| 7 | Dashboard adapter to versioned API, streaming state, accessible approval UX, compatibility checks | Stable API/events and tool/speech contracts |
| 8 | Profile-guided C++20 sidecar(s), packaging, stress/security/release gates | Measured bottleneck, native protocol, completed integration tests |

The exact order of Batches 3-6 can overlap after Batch 2 contracts are frozen. The dashboard can be developed against fake API fixtures while services are in progress. Native implementation is deliberately last and conditional on profiling.

## Parallel workstreams

After Batch 2 contract review, these workstreams can proceed independently:

| Workstream | Owns | Shared dependency / integration gate |
|---|---|---|
| A. Model adapters | `backends/ollama`, `backends/llama_cpp`, adapter contract tests | `ModelBackend`; each adapter tested with a fake local server |
| B. Scheduler and capability discovery | GPU/RAM/CPU probes, model admission, reservations, health | `CapabilityProvider`, `ResourceEstimate`; synthetic resource tests before hardware tests |
| C. Memory | SQLite repository, migrations, lexical/semantic search providers | `MemoryStore`; migrations tested on copied fixtures and preserve legacy DB |
| D. Tools and permissions | Tool schemas, approval service, Windows app/browser providers | `ToolRegistry`, `PermissionPolicy`; deny-by-default tests before UI integration |
| E. Speech | OpenWhispr/ASR and Qwen/system TTS adapters, voice profiles, chunk events | `SpeechProvider`; fixtures/mock services, then hardware smoke tests |
| F. Dashboard | Versioned API client, model/voice status, approvals, telemetry | Frozen API/event schema; browser tests use fake services |
| G. Native C++20 | Only profiled native hot paths or Windows API/audio providers | `native.v1` protocol, ACL and fuzz/size/deadline tests; never blocks Python fallback |

To prevent merge conflicts, only the contract owner changes common types/schema during a batch. Each workstream owns a separate module directory and tests; cross-module changes go through a small contract change proposal with compatibility impact.

## Integration strategy

1. Keep `main` as the working legacy line. Do not port features by rewriting `jarvis.py` in place.
2. Merge one versioned contract and its schema before parallel adapter implementation.
3. Use fake adapters and deterministic fixtures for unit/contract tests; use local model services only in opt-in integration jobs.
4. Keep v2 start-up behind an explicit setting/flag. The default remains the existing `.bat` until the full checklist passes.
5. Put the legacy API and v2 API behind separate adapters. During migration, compare behavior using the same fixtures, not two live writers to user data.
6. Use copy/backup-first SQLite migration with a rollback path. Never delete or overwrite the legacy DB/voice assets during migration.
7. Require a reviewed integration test, security check, and resource benchmark before changing the default launcher or promoting a native service.
8. Push feature branches only after their staged files have been checked for local data, tokens, logs, and model artifacts.

## Test and benchmark gates

- Unit tests cover validation, scheduler admission, cancellation, memory migrations, permissions, and adapters with fakes.
- Contract tests run identically on Windows without a GPU or external service.
- Integration tests are opt-in and use only loopback Ollama/llama.cpp/ASR/TTS endpoints and explicitly installed local model artifacts.
- End-to-end tests exercise existing app features with disposable DB/audio fixtures; they never consume or rewrite the user's voice data.
- Performance reports record hardware, model artifact/hash/quantization, context, warm/cold state, p50/p95, peak VRAM/RAM, and errors. A single timing is not a performance claim.
- Scheduler stress tests prove no reservation overcommit for the configured budget; hardware tests include a low-VRAM/unknown-capability case.

## Batch 2 acceptance criteria

Batch 2 is complete only when all of the following are true:

1. The schema loader rejects unknown keys, remote inference/model URLs, and any non-loopback backend or dashboard bind.
2. Capability discovery distinguishes measured, estimated, and unavailable values and reports CPU, RAM, GPU/VRAM, audio devices, installed local models, and backend health without network access.
3. The scheduler has fake-provider tests for fit, insufficient VRAM, concurrent requests, reservation release on error/cancel, and visible CPU/model fallback.
4. Tool policy denies shell/arbitrary execution, requires a short-lived matching grant for sensitive actions, and has tests that prove denied calls have no side effects.
5. The current entry point and `run-jarvis.bat` still work unchanged; a smoke test confirms the old dashboard/API remains available.
6. All rows in [COMPATIBILITY_CHECKLIST.md](COMPATIBILITY_CHECKLIST.md) have a repeatable verification method; no feature is silently removed.
7. Existing SQLite/voice data is untouched by unit/integration tests. Any migration is copy-first, has a backup, and passes rollback verification.
8. No non-loopback inference, paid API, secret, personal voice file, local model weight, or user database is present in the repository.

## Open decisions for later batches

- Whether v2 requires Python 3.12 as its minimum or supports the current legacy minimum.
- Which local embedding model and quantization fit the memory budget and meet latency/quality needs.
- Which ASR/TTS providers and streaming semantics are available in the supported Windows environment.
- Whether a native C++ sidecar is justified after Python and backend profiles.
- User-configurable approval policy and retention defaults.
- Exact p50/p95 latency targets after repeatable current-system baselines are collected.
