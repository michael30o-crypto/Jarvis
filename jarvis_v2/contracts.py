"""Typed, dependency-free interfaces for the proposed Jarvis 2.0 modules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Literal, Mapping, Protocol, Sequence

BackendId = Literal["ollama", "llama_cpp", "qwen3_tts"]
ModelRole = Literal["chat", "asr", "tts", "embedding", "vision", "rerank"]
MessageRole = Literal["system", "user", "assistant", "tool"]
MemoryKind = Literal["message", "task", "note", "fact"]
GenerationKind = Literal["delta", "completed", "usage", "error"]
PermissionOutcome = Literal["allow", "require_confirmation", "deny"]
CapabilityEvidence = Literal["measured", "estimated", "unavailable"]
AdmissionStatus = Literal["admitted", "queued", "rejected"]


@dataclass(frozen=True)
class ServiceError:
    code: str
    safe_message: str
    retryable: bool
    diagnostics: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceEstimate:
    vram_bytes: int = 0
    ram_bytes: int = 0
    context_tokens: int = 0
    gpu_required: bool = False


@dataclass(frozen=True)
class ModelDescriptor:
    model_id: str
    backend_id: BackendId
    local_ref: str
    roles: frozenset[ModelRole]
    context_tokens: int | None = None
    resources: ResourceEstimate = field(default_factory=ResourceEstimate)


@dataclass(frozen=True)
class BackendHealth:
    backend_id: BackendId
    available: bool
    detail: str = ""
    checked_at: str = ""
    capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ChatMessage:
    role: MessageRole
    content: str
    name: str | None = None


@dataclass(frozen=True)
class GenerationOptions:
    max_tokens: int = 256
    temperature: float = 0.7
    top_p: float = 0.9
    stop: tuple[str, ...] = ()


@dataclass(frozen=True)
class InferenceRequest:
    request_id: str
    purpose: ModelRole
    messages: tuple[ChatMessage, ...]
    model_id: str | None = None
    options: GenerationOptions = field(default_factory=GenerationOptions)
    deadline_ms: int | None = None


@dataclass(frozen=True)
class GenerationEvent:
    request_id: str
    kind: GenerationKind
    text: str = ""
    model_id: str = ""
    backend_id: str = ""
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None
    duration_ms: int | None = None
    error: ServiceError | None = None


@dataclass(frozen=True)
class GpuCapability:
    device_id: str
    name: str
    total_vram_bytes: int | None
    free_vram_bytes: int | None
    compute_capability: str | None = None
    supported_dtypes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeCapabilities:
    discovered_at: str
    platform: str
    cpu_logical_count: int | None
    ram_total_bytes: int | None
    ram_available_bytes: int | None
    gpus: tuple[GpuCapability, ...] = ()
    audio_inputs: tuple[str, ...] = ()
    audio_outputs: tuple[str, ...] = ()
    backends: tuple[BackendHealth, ...] = ()
    models: tuple[ModelDescriptor, ...] = ()
    field_evidence: Mapping[str, CapabilityEvidence] = field(default_factory=dict)
    field_sources: Mapping[str, str] = field(default_factory=dict)
    unavailable_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class MemoryRecord:
    record_id: str
    kind: MemoryKind
    content: str
    created_at: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    tool_id: str
    arguments: Mapping[str, Any]


@dataclass(frozen=True)
class AuthorizationGrant:
    grant_id: str
    tool_id: str
    arguments_digest: str
    expires_at_epoch_ms: int


@dataclass(frozen=True)
class PermissionDecision:
    outcome: PermissionOutcome
    reason: str
    grant: AuthorizationGrant | None = None
    preview: str | None = None


@dataclass(frozen=True)
class SchedulerAdmission:
    request_id: str
    status: AdmissionStatus
    model_id: str | None = None
    backend_id: BackendId | None = None
    queue_position: int | None = None
    fallback_reason: str | None = None
    error: ServiceError | None = None


@dataclass(frozen=True)
class ToolDescriptor:
    tool_id: str
    description: str
    argument_schema: Mapping[str, Any]
    requires_confirmation: bool


@dataclass(frozen=True)
class NativeServiceResponse:
    request_id: str
    result: Mapping[str, Any] | None = None
    error: ServiceError | None = None


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    ok: bool
    output: str = ""
    error: ServiceError | None = None


@dataclass(frozen=True)
class SpeechChunk:
    request_id: str
    audio: bytes
    media_type: str
    final: bool
    voice_id: str | None = None
    model_id: str | None = None


class CapabilityProvider(Protocol):
    async def discover(self) -> RuntimeCapabilities: ...


class ModelBackend(Protocol):
    async def list_models(self) -> Sequence[ModelDescriptor]: ...

    async def health(self) -> BackendHealth: ...

    async def estimate(self, model_id: str, context_tokens: int) -> ResourceEstimate: ...

    async def load(self, model_id: str) -> None: ...

    async def unload(self, model_id: str) -> None: ...

    def stream(self, request: InferenceRequest) -> AsyncIterator[GenerationEvent]: ...


class ModelScheduler(Protocol):
    async def submit(self, request: InferenceRequest) -> SchedulerAdmission: ...

    def stream(self, request_id: str) -> AsyncIterator[GenerationEvent]: ...

    async def cancel(self, request_id: str) -> bool: ...


class MemoryStore(Protocol):
    async def append(self, record: MemoryRecord) -> str: ...

    async def get(self, record_id: str) -> MemoryRecord | None: ...

    async def list_records(
        self, kind: MemoryKind | None = None, limit: int = 100
    ) -> Sequence[MemoryRecord]: ...

    async def search(
        self, query: str, limit: int, kind: MemoryKind | None = None
    ) -> Sequence[MemoryRecord]: ...


class PermissionPolicy(Protocol):
    async def decide(self, call: ToolCall) -> PermissionDecision: ...


class ToolRegistry(Protocol):
    async def list_tools(self) -> Sequence[ToolDescriptor]: ...

    async def invoke(
        self, call: ToolCall, grant: AuthorizationGrant | None = None
    ) -> ToolResult: ...


class SpeechProvider(Protocol):
    async def transcribe(self, audio: bytes, media_type: str) -> str: ...

    def synthesize(
        self, request_id: str, text: str, voice_id: str
    ) -> AsyncIterator[SpeechChunk]: ...


class NativeServiceClient(Protocol):
    async def request(
        self, method: str, params: Mapping[str, Any], timeout_ms: int
    ) -> NativeServiceResponse: ...
