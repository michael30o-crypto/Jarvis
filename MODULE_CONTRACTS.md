# Jarvis 2.0 Module Contracts

**Contract version:** 1 (design/scaffold only). These definitions are not imported by the legacy runtime.

## Common rules

- Public Python interfaces live in `jarvis_v2/contracts.py`; JSON configuration is versioned independently by `schema_version`.
- Every request-scoped asynchronous operation carries a caller-generated `request_id`. Results and diagnostics preserve it across API, orchestrator, scheduler, backend, and tool boundaries.
- Errors use a stable code, safe user-facing message, retryability flag, and redacted diagnostic details. Implementations must not convert failures into successful empty results.
- Names such as model IDs, tool IDs, voice IDs, and capability IDs are stable opaque identifiers. Paths and provider-specific handles are not leaked to the dashboard unless explicitly needed.
- Backend adapters use only loopback endpoints or local model artifacts. A remote URL is not a valid model artifact reference.
- Protocol evolution is additive within a major version. Breaking changes require a new contract version and adapter migration tests.

## Python orchestration interfaces

The additive `jarvis_v2.contracts` module defines standard-library-only dataclasses and `Protocol`s:

| Interface | Responsibility |
|---|---|
| `CapabilityProvider.discover()` | Return a `RuntimeCapabilities` snapshot: CPU, RAM, GPUs/VRAM, audio devices, installed backends/models, health, probe time, and per-field evidence/source |
| `ModelBackend` | List installed local models, report health, estimate resources, load/unload a model, and stream typed generation events |
| `ModelScheduler` | `submit()` admits, queues, or rejects a request with the selected model/backend and visible fallback; `stream()` returns its events and `cancel()` releases the request |
| `MemoryStore` | Append, fetch, list, and search typed records with bounded results and an explicit record kind |
| `PermissionPolicy` | Decide allow/require-confirmation/deny for a typed `ToolCall` before any side effect |
| `ToolRegistry` | List registered tool metadata and invoke only an approved tool with validated arguments and a matching `AuthorizationGrant` |
| `SpeechProvider` | Transcribe local audio and emit `SpeechChunk`s with voice/model metadata; existing whole-file providers can emit one final chunk |
| `NativeServiceClient` | Send a versioned, bounded request to an ACL-protected local C++ service and return a typed response carrying an optional `ServiceError` |

### Model request

`InferenceRequest` carries:

- `request_id`, `purpose`, and optional required `model_id`
- ordered typed messages
- bounded `GenerationOptions` (adapter validates allowed values)
- optional deadline; cancellation is addressed to the request ID through `ModelScheduler.cancel()`
- no shell, arbitrary URL, or user credential fields

`ModelBackend.stream()` emits `GenerationEvent` values (`delta`, `completed`, `usage`, `error`). Error events carry a stable `ServiceError` with a safe message and retryability. The final event includes model/backend identity, finish reason, token counts where available, and duration. Streaming support is declared in `BackendHealth.capabilities`; a non-streaming backend emits one completion event.

`ResourceEstimate` records at least estimated VRAM/RAM bytes and context length. Estimates are advisory; the scheduler also checks current free resources and keeps a configurable safety reserve. `RuntimeCapabilities.field_evidence` marks each reported field as measured, estimated, or unavailable, and `field_sources` identifies the probe/provider.

### Tool invocation

`ToolCall` is `{call_id, tool_id, arguments}`. `PermissionPolicy` returns one of:

- `allow`: safe non-sensitive operation covered by configured policy
- `require_confirmation`: return a preview and wait for an explicit user grant
- `deny`: do not invoke; return a safe reason

`AuthorizationGrant` is scoped to one tool and argument digest, expires quickly, and cannot be reused for a different operation. Tool results include `ok`, a stable `ServiceError` on failure, and user-safe output. No tool adapter accepts arbitrary command strings.

## Python-to-C++ service wire contract

The initial transport is a Windows named pipe with an ACL restricted to the current user SID. The wire format is one UTF-8 JSON object per message, capped at 1 MiB:

```json
{"protocol":"jarvis.native.v1","id":"request-id","method":"capabilities.snapshot","params":{}}
```

Success:

```json
{"protocol":"jarvis.native.v1","id":"request-id","result":{"available":true}}
```

Failure:

```json
{"protocol":"jarvis.native.v1","id":"request-id","error":{"code":"unsupported_method","message":"Method is unavailable","retryable":false}}
```

Methods are service-specific and allowlisted. Calls have deadlines, cancellation/connection-close behavior, and maximum payload limits. No C++ service accepts a command line from a model or opens a non-loopback network listener. See [native/PROTOCOL.md](native/PROTOCOL.md).

## API and configuration contracts

- The dashboard talks to the Python API only. API routes are versioned (`/api/v2/...`) and return typed JSON errors; streaming uses a documented local event stream.
- `jarvis_v2/config.schema.json` is the source schema for the target configuration. The example is illustrative; JSON Schema `default` annotations do not apply values automatically.
- Configuration validation rejects non-loopback endpoints, remote model URLs, unknown keys, and `local_only=false`.
- The existing `/api/*` routes and their payloads remain unchanged until a separately reviewed compatibility adapter is tested.

## Invariants for adapter authors

1. Do not fetch models or call paid/cloud APIs from inference paths.
2. Do not load/unload models outside the scheduler's reservation.
3. Report unsupported operations explicitly; do not return success-shaped fallbacks.
4. Do not perform side effects before policy authorization.
5. Do not put user memory, transcripts, credentials, or model weights in logs or source control.
6. Keep adapters independently fakeable so contract tests do not require GPU hardware.
