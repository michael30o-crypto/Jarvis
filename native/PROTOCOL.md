# Native C++20 Service Boundary

Batch 1 defines a wire contract only. There is no native executable or production C++ code in this batch.

## Why a sidecar

Python owns orchestration, scheduling, persistence, and authorization. A C++20 service is justified only after a repeatable profile identifies a CPU-bound hot path or a Windows API/audio operation that benefits from native code. Initial candidates are small audio-processing primitives or capability probes, not model orchestration or policy.

## Transport and envelope

- Windows named pipe, with an ACL restricted to the current interactive user SID.
- UTF-8 JSON request/response, one object per message, maximum 1 MiB.
- Versioned protocol `jarvis.native.v1`, request ID, allowlisted method, bounded parameters, and a deadline.
- No TCP listener, cloud connection, arbitrary command field, model download, or access to the user's database/voice files.

Request:

```json
{"protocol":"jarvis.native.v1","id":"request-id","method":"capabilities.snapshot","params":{}}
```

Success:

```json
{"protocol":"jarvis.native.v1","id":"request-id","result":{"available":true}}
```

Error:

```json
{"protocol":"jarvis.native.v1","id":"request-id","error":{"code":"unsupported_method","message":"Method is unavailable","retryable":false}}
```

## Responsibilities

- Python validates input, applies permissions, chooses the service, and handles user-visible errors.
- C++ validates protocol version, method, bounds, and caller identity; it performs only its documented operation and returns a typed result.
- The C++ service never interprets model output as commands and never bypasses Python's tool policy.
- Native failure or absence is reported explicitly. A Python implementation may be used only when the caller configured that fallback.

## Testing gate

Before a native service is adopted, add protocol contract tests, malformed/oversized message tests, timeout and process-exit tests, named-pipe ACL tests, and parity/performance comparisons against the Python implementation. Do not ship it merely because a C++ scaffold compiles.
