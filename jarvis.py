from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from contextlib import contextmanager
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "jarvis.sqlite3"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen3:8b"
PORT = 8765
VOICE_URL = "http://127.0.0.1:8090"
VOICE_PROMPT = DATA_DIR / "voice_prompt.bin"
VOICE_CONFIG = DATA_DIR / "voice.json"
VOICES_DIR = DATA_DIR / "voices"
AUDIO_CACHE_DIR = DATA_DIR / "audio_cache"
MAX_VOICE_BYTES = 15 * 1024 * 1024
MAX_TRANSCRIPTION_BYTES = 25 * 1024 * 1024
OPENWHISPR_CONFIG = Path.home() / ".openwhispr" / "cli-bridge.json"

GPU_LOCK = threading.Lock()
METRICS_LOCK = threading.Lock()
METRICS = {
    "chat_ms": 0,
    "transcription_ms": 0,
    "voice_ms": 0,
    "last_updated": "",
}
GPU_APPS = {"comfyui", "qwen", "applio"}
COMPETITOR_MARKERS = (
    "ComfyUI_windows_portable",
    "\\Applio\\",
    "Qwen3-TTS",
    "qwen3-tts",
    "qwen-tts-demo",
)

APP_COMMANDS = {
    "calculator": ["calc.exe"],
    "notepad": ["notepad.exe"],
    "explorer": ["explorer.exe"],
    "comfyui": [str(Path.home() / "ComfyUI_windows_portable" / "run_nvidia_gpu.bat")],
    "qwen": [str(Path.home() / "Qwen3-TTS" / "run-qwen-tts.bat")],
    "applio": [str(Path.home() / "Applio" / "run-applio.bat")],
    "openwhispr": [r"C:\Program Files\OpenWhispr\OpenWhispr.exe"],
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "launch_app",
            "description": "Launch an approved local application.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app": {"type": "string", "enum": list(APP_COMMANDS)}
                },
                "required": ["app"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_url",
            "description": "Open an HTTP or HTTPS web address in the default browser.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Capture a task in Jarvis memory.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task complete by its numeric ID.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "integer"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List open tasks.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_note",
            "description": "Save a note or preference for future conversations.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_notes",
            "description": "Recall saved notes and preferences.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM_PROMPT = """You are Jarvis, a calm local Windows assistant designed to reduce cognitive load.
Be concise, practical, and direct. Never claim that an action happened unless a tool result confirms it.
Use tools for app launches, URLs, tasks, and saved notes. If a request requires deletion, payment,
password entry, credentials, arbitrary shell commands, or broad file modification, refuse and suggest
an explicit safer next step. For vague requests, choose one clear next action. Do not role-play JARVIS
from a film; use an original restrained assistant voice.
"""


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with db() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def timestamp() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def voice_settings() -> dict[str, Any]:
    if not VOICE_CONFIG.exists():
        return {}
    try:
        result = json.loads(VOICE_CONFIG.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_voice_settings(**updates: Any) -> dict[str, Any]:
    current = voice_settings()
    current.update(updates)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VOICE_CONFIG.write_text(json.dumps(current), encoding="utf-8")
    return current


def voice_library() -> list[dict[str, Any]]:
    settings = voice_settings()
    voices = settings.get("voices", [])
    if voices or not VOICE_PROMPT.exists():
        return voices if isinstance(voices, list) else []
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    prompt_path = VOICES_DIR / "legacy.bin"
    reference_path = VOICES_DIR / "legacy_reference.wav"
    shutil.copy2(VOICE_PROMPT, prompt_path)
    original_reference = DATA_DIR / "voice_reference.wav"
    if original_reference.exists():
        shutil.copy2(original_reference, reference_path)
    legacy = {
        "id": "legacy",
        "name": "My cloned voice",
        "transcript": str(settings.get("transcript", "")),
        "created_at": str(settings.get("created_at", timestamp())),
    }
    save_voice_settings(voices=[legacy], active_voice_id="legacy")
    return [legacy]


def active_voice() -> dict[str, Any] | None:
    voices = voice_library()
    active_id = str(voice_settings().get("active_voice_id", ""))
    return next((voice for voice in voices if str(voice.get("id")) == active_id), voices[0] if voices else None)


def voice_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "voice"
    suffix = hashlib.sha256(f"{name}:{time.time_ns()}".encode()).hexdigest()[:8]
    return f"{slug}-{suffix}"


def save_message(role: str, content: str) -> None:
    with db() as connection:
        connection.execute(
            "INSERT INTO messages(role, content, created_at) VALUES (?, ?, ?)",
            (role, content, timestamp()),
        )


def recent_messages(limit: int = 16) -> list[dict[str, str]]:
    with db() as connection:
        rows = connection.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]


def gpu_handoff_enabled() -> bool:
    return os.environ.get("JARVIS_SKIP_GPU_HANDOFF") != "1"


def ollama_exe() -> str:
    return str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe")


def record_metric(name: str, elapsed_ms: int) -> None:
    with METRICS_LOCK:
        METRICS[name] = elapsed_ms
        METRICS["last_updated"] = timestamp()


def endpoint_online(url: str, timeout: float = 1.0) -> bool:
    try:
        urllib.request.urlopen(url, timeout=timeout).close()
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def runtime_telemetry() -> dict[str, Any]:
    telemetry: dict[str, Any] = {
        "gpu": {"used_mib": 0, "free_mib": 0, "utilization": 0, "temperature": 0, "power_w": 0.0},
        "models": {"llm": gpu_processor(), "voice_online": endpoint_online(VOICE_URL)},
        "latency": {},
        "storage": {},
    }
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.used,memory.free,utilization.gpu,temperature.gpu,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=6,
            check=False,
        )
        values = [value.strip() for value in result.stdout.splitlines()[0].split(",")]
        if len(values) == 5:
            telemetry["gpu"] = {
                "used_mib": int(values[0]),
                "free_mib": int(values[1]),
                "utilization": int(values[2]),
                "temperature": int(values[3]),
                "power_w": float(values[4]),
            }
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        pass
    usage = shutil.disk_usage(ROOT.drive or str(ROOT))
    telemetry["storage"] = {
        "used_gb": round((usage.total - usage.free) / (1024 ** 3), 1),
        "free_gb": round(usage.free / (1024 ** 3), 1),
    }
    with METRICS_LOCK:
        telemetry["latency"] = dict(METRICS)
    return telemetry


def gpu_processor() -> str:
    if not gpu_handoff_enabled():
        return "test"
    try:
        result = subprocess.run(
            [ollama_exe(), "ps"], capture_output=True, text=True, timeout=8, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return f"unavailable ({error})"
    for line in result.stdout.splitlines():
        if MODEL not in line:
            continue
        if "100% GPU" in line:
            return "100% GPU"
        if "GPU" in line:
            return "partial GPU"
        if "CPU" in line:
            return "CPU"
    return "GPU ready, model idle"


def stop_competing_gpu_apps() -> None:
    if not gpu_handoff_enabled():
        return
    subprocess.run(
        ["taskkill", "/F", "/IM", "qwen-tts-demo.exe"],
        capture_output=True,
        check=False,
    )
    script = (
        "$markers = @('ComfyUI_windows_portable','\\Applio\\','Qwen3-TTS','qwen3-tts','qwen-tts-demo'); "
        "Get-CimInstance Win32_Process | Where-Object { "
        "$cmd = [string]$_.ExecutablePath + ' ' + [string]$_.CommandLine; "
        "$markers | Where-Object { $cmd -like ('*' + $_ + '*') } } | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        check=False,
        timeout=20,
    )


def release_llm_gpu() -> None:
    if not gpu_handoff_enabled():
        return
    subprocess.run(
        [ollama_exe(), "stop", MODEL],
        capture_output=True,
        check=False,
        timeout=30,
    )


def prepare_llm_gpu() -> None:
    if not gpu_handoff_enabled():
        return
    with GPU_LOCK:
        stop_competing_gpu_apps()


def prepare_voice_gpu() -> None:
    if not gpu_handoff_enabled():
        return
    with GPU_LOCK:
        release_llm_gpu()
        try:
            urllib.request.urlopen(VOICE_URL, timeout=2).close()
            return
        except (urllib.error.URLError, TimeoutError, OSError):
            pass
        project = Path.home() / "Qwen3-TTS"
        environment = Path.home() / "Miniconda3" / "envs" / "qwen3-tts"
        executable = environment / "Scripts" / "qwen-tts-demo.exe"
        if not executable.exists():
            raise FileNotFoundError("Qwen voice executable was not found.")
        child_environment = os.environ.copy()
        child_environment["PATH"] = ";".join(
            [
                str(environment / "Library" / "bin"),
                str(environment / "Scripts"),
                str(Path.home() / "Miniconda3" / "condabin"),
                child_environment.get("PATH", ""),
            ]
        )
        child_environment["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
        subprocess.Popen(
            [
                str(executable),
                "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
                "--ip",
                "127.0.0.1",
                "--port",
                "8090",
                "--no-flash-attn",
            ],
            cwd=str(project),
            env=child_environment,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        deadline = time.time() + 120
        while time.time() < deadline:
            try:
                urllib.request.urlopen(VOICE_URL, timeout=2).close()
                return
            except (urllib.error.URLError, TimeoutError, OSError):
                time.sleep(1)
        raise TimeoutError("Qwen voice server did not start after the GPU was freed.")


def run_tool(name: str, arguments: dict[str, Any]) -> str:
    if name == "launch_app":
        app = str(arguments.get("app", ""))
        command = APP_COMMANDS.get(app)
        if not command or not Path(command[0]).exists() and not app in {"calculator", "notepad", "explorer"}:
            return f"Cannot launch {app}: the approved application is not installed."
        if app in GPU_APPS:
            release_llm_gpu()
        subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        return f"Launched {app}."
    if name == "open_url":
        url = str(arguments.get("url", ""))
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "Refused: only HTTP or HTTPS URLs are allowed."
        webbrowser.open(url)
        return f"Opened {url} in the browser."
    if name == "add_task":
        text = str(arguments.get("text", "")).strip()
        if not text:
            return "Refused: the task was empty."
        with db() as connection:
            cursor = connection.execute(
                "INSERT INTO tasks(text, created_at) VALUES (?, ?)", (text, timestamp())
            )
            return f"Added task #{cursor.lastrowid}: {text}"
    if name == "complete_task":
        task_id = int(arguments.get("task_id", 0))
        with db() as connection:
            changed = connection.execute(
                "UPDATE tasks SET completed = 1 WHERE id = ? AND completed = 0", (task_id,)
            ).rowcount
        return f"Completed task #{task_id}." if changed else f"Task #{task_id} was not open."
    if name == "list_tasks":
        with db() as connection:
            rows = connection.execute(
                "SELECT id, text FROM tasks WHERE completed = 0 ORDER BY id"
            ).fetchall()
        return json.dumps([dict(row) for row in rows])
    if name == "save_note":
        text = str(arguments.get("text", "")).strip()
        if not text:
            return "Refused: the note was empty."
        with db() as connection:
            cursor = connection.execute(
                "INSERT INTO notes(text, created_at) VALUES (?, ?)", (text, timestamp())
            )
        return f"Saved note #{cursor.lastrowid}."
    if name == "list_notes":
        with db() as connection:
            rows = connection.execute(
                "SELECT id, text, created_at FROM notes ORDER BY id DESC LIMIT 20"
            ).fetchall()
        return json.dumps([dict(row) for row in rows])
    return f"Unknown tool: {name}"


def ollama_chat(messages: list[dict[str, Any]]) -> dict[str, Any]:
    body = json.dumps(
        {
            "model": MODEL,
            "messages": messages,
            "tools": TOOLS,
            "stream": False,
            "think": False,
            "keep_alive": "30m",
            "options": {"temperature": 0.4, "num_predict": 80, "num_ctx": 4096},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read().decode("utf-8"))


def configure_voice(audio_data_url: str, transcript: str, name: str = "") -> str:
    transcript = transcript.strip()
    name = name.strip() or f"Voice {len(voice_library()) + 1}"
    if not transcript:
        raise ValueError("A transcript of the voice sample is required.")
    try:
        header, encoded = audio_data_url.split(",", 1)
    except ValueError as error:
        raise ValueError("The voice sample must be a data URL.") from error
    if not header.startswith("data:audio/"):
        raise ValueError("Only audio files can be saved as a voice sample.")
    audio = base64.b64decode(encoded, validate=True)
    if not audio:
        raise ValueError("The voice sample is empty.")
    if len(audio) > MAX_VOICE_BYTES:
        raise ValueError("Voice samples must be 15 MB or smaller.")
    reference_path = DATA_DIR / "voice_reference.wav"
    reference_path.write_bytes(audio)
    prepare_voice_gpu()

    from gradio_client import Client, handle_file

    client = Client(VOICE_URL)
    prompt_path, status = client.predict(
        handle_file(str(reference_path)), transcript, False, api_name="/save_prompt"
    )
    if not prompt_path or not Path(prompt_path).exists():
        raise RuntimeError(f"Qwen could not create the voice prompt: {status}")
    voice_id = voice_slug(name)
    VOICES_DIR.mkdir(parents=True, exist_ok=True)
    stored_prompt = VOICES_DIR / f"{voice_id}.bin"
    stored_reference = VOICES_DIR / f"{voice_id}_reference.wav"
    shutil.copy2(prompt_path, stored_prompt)
    shutil.copy2(reference_path, stored_reference)
    shutil.copy2(stored_prompt, VOICE_PROMPT)
    voices = voice_library()
    voice = {
        "id": voice_id,
        "name": name,
        "transcript": transcript,
        "created_at": timestamp(),
    }
    save_voice_settings(
        voices=[item for item in voices if item.get("id") != voice_id] + [voice],
        active_voice_id=voice_id,
        transcript=transcript,
        created_at=voice["created_at"],
        preferred_voice="qwen",
    )
    return str(status)


def transcribe_audio(audio_data_url: str) -> str:
    started_at = time.perf_counter()
    try:
        header, encoded = audio_data_url.split(",", 1)
    except ValueError as error:
        raise ValueError("The recording must be a data URL.") from error
    mime = header.removeprefix("data:").split(";", 1)[0]
    if not mime.startswith("audio/"):
        raise ValueError("Only audio recordings can be transcribed.")
    audio = base64.b64decode(encoded, validate=True)
    if not audio:
        raise ValueError("The recording is empty.")
    if len(audio) > MAX_TRANSCRIPTION_BYTES:
        raise ValueError("Audio recordings must be 25 MB or smaller.")
    suffix = {
        "audio/webm": ".webm",
        "audio/ogg": ".ogg",
        "audio/mp4": ".m4a",
        "audio/wav": ".wav",
        "audio/x-wav": ".wav",
        "audio/mpeg": ".mp3",
    }.get(mime, ".audio")
    recording_path = DATA_DIR / f"utterance-{os.getpid()}-{threading.get_ident()}{suffix}"
    recording_path.write_bytes(audio)
    try:
        config = json.loads(OPENWHISPR_CONFIG.read_text(encoding="utf-8"))
        request = urllib.request.Request(
            f"http://127.0.0.1:{config['port']}/v1/transcribe",
            data=json.dumps({"path": str(recording_path)}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config['token']}",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
        record_metric("transcription_ms", round((time.perf_counter() - started_at) * 1000))
        return str(result.get("data", {}).get("text", "")).strip()
    finally:
        recording_path.unlink(missing_ok=True)


def synthesize_voice(text: str, voice_id: str = "") -> tuple[bytes, str]:
    started_at = time.perf_counter()
    voice = active_voice()
    if voice_id:
        voice = next((item for item in voice_library() if item.get("id") == voice_id), None)
    if not voice:
        raise FileNotFoundError("No cloned voice is configured yet.")
    prompt_path = VOICES_DIR / f"{voice['id']}.bin"
    if not prompt_path.exists():
        if voice.get("id") != "legacy" and VOICE_PROMPT.exists():
            prompt_path = VOICE_PROMPT
        else:
            raise FileNotFoundError("The saved voice prompt is missing.")
    text = text.strip()
    if not text:
        raise ValueError("Speech text cannot be empty.")
    AUDIO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.sha256(f"{voice['id']}\0{text}".encode()).hexdigest()
    cache_path = AUDIO_CACHE_DIR / f"{cache_key}.wav"
    if cache_path.exists():
        record_metric("voice_ms", -1)
        return cache_path.read_bytes(), "audio/wav"
    prepare_voice_gpu()

    from gradio_client import Client, handle_file

    client = Client(VOICE_URL)
    audio_path, status = client.predict(
        handle_file(str(prompt_path)), text, "English", api_name="/load_prompt_and_gen"
    )
    if not audio_path or not Path(audio_path).exists():
        raise RuntimeError(f"Qwen could not synthesize speech: {status}")
    audio = Path(audio_path).read_bytes()
    mime = "audio/wav"
    if Path(audio_path).suffix.lower() == ".mp3":
        mime = "audio/mpeg"
    cache_path.write_bytes(audio)
    record_metric("voice_ms", round((time.perf_counter() - started_at) * 1000))
    return audio, mime


def chat(user_text: str) -> str:
    started_at = time.perf_counter()
    user_text = user_text.strip()
    if not user_text:
        raise ValueError("Message cannot be empty.")
    prepare_llm_gpu()
    save_message("user", user_text)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *recent_messages(),
    ]
    result = ollama_chat(messages)
    assistant = result.get("message", {})
    tool_calls = assistant.get("tool_calls") or []
    if tool_calls:
        messages.append(assistant)
        for call in tool_calls:
            function = call.get("function", {})
            name = str(function.get("name", ""))
            arguments = function.get("arguments") or {}
            messages.append(
                {
                    "role": "tool",
                    "content": run_tool(name, arguments),
                    "tool_name": name,
                }
            )
        result = ollama_chat(messages)
        assistant = result.get("message", {})
    reply = str(assistant.get("content", "")).strip()
    if not reply:
        reply = "I completed the request, but the local model returned no response."
    save_message("assistant", reply)
    record_metric("chat_ms", round((time.perf_counter() - started_at) * 1000))
    return reply


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT / "web"), **kwargs)

    def log_message(self, format_string: str, *args: Any) -> None:
        print("%s - %s" % (self.address_string(), format_string % args))

    def send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/telemetry":
            self.send_json(200, runtime_telemetry())
            return
        if self.path == "/api/state":
            self.send_json(200, {
                "model": MODEL,
                "app": "Jarvis",
                "ollama": OLLAMA_URL,
                "processor": gpu_processor(),
                "voice_ready": VOICE_PROMPT.exists(),
                "voice_transcript": voice_settings().get("transcript", ""),
                "preferred_voice": (
                    "qwen"
                    if VOICE_PROMPT.exists()
                    and voice_settings().get("preferred_voice", "qwen") == "qwen"
                    else "system"
                ),
                "voice_created_at": voice_settings().get("created_at", ""),
                "voices": voice_library(),
                "active_voice_id": voice_settings().get("active_voice_id", ""),
                "tasks": self.task_rows(),
                "notes": self.note_rows(),
            })
            return
        super().do_GET()

    def do_POST(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if self.path == "/api/chat":
                self.send_json(200, {"reply": chat(str(payload.get("message", "")))})
                return
            if self.path == "/api/transcribe":
                text = transcribe_audio(str(payload.get("audio", "")))
                self.send_json(200, {"text": text})
                return
            if self.path == "/api/voice":
                status = configure_voice(
                    str(payload.get("audio", "")),
                    str(payload.get("transcript", "")),
                    str(payload.get("name", "")),
                )
                self.send_json(200, {"ok": True, "status": status, "voices": voice_library()})
                return
            if self.path == "/api/voice-settings":
                preferred_voice = str(payload.get("preferred_voice", ""))
                if preferred_voice not in {"qwen", "system"}:
                    raise ValueError("Voice preference must be qwen or system.")
                if preferred_voice == "qwen" and not voice_library():
                    raise ValueError("Create a Qwen voice before selecting it.")
                active_voice_id = str(payload.get("active_voice_id", ""))
                if active_voice_id:
                    selected = next((item for item in voice_library() if item.get("id") == active_voice_id), None)
                    if not selected:
                        raise ValueError("The selected saved voice was not found.")
                    save_voice_settings(active_voice_id=active_voice_id)
                save_voice_settings(preferred_voice=preferred_voice)
                self.send_json(200, {"ok": True, "preferred_voice": preferred_voice, "active_voice_id": voice_settings().get("active_voice_id", "")})
                return
            if self.path == "/api/speak":
                audio, mime = synthesize_voice(
                    str(payload.get("text", "")), str(payload.get("voice_id", ""))
                )
                self.send_json(200, {
                    "audio": f"data:{mime};base64,{base64.b64encode(audio).decode('ascii')}"
                })
                return
            self.send_json(404, {"error": "Not found"})
        except FileNotFoundError as error:
            self.send_json(409, {"error": str(error)})
        except (ValueError, urllib.error.URLError, TimeoutError) as error:
            self.send_json(503, {"error": str(error)})
        except Exception as error:
            self.send_json(500, {"error": f"Jarvis failed: {type(error).__name__}: {error}"})

    @staticmethod
    def task_rows() -> list[dict[str, Any]]:
        with db() as connection:
            rows = connection.execute(
                "SELECT id, text, completed, created_at FROM tasks ORDER BY id DESC LIMIT 50"
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def note_rows() -> list[dict[str, Any]]:
        with db() as connection:
            rows = connection.execute(
                "SELECT id, text, created_at FROM notes ORDER BY id DESC LIMIT 20"
            ).fetchall()
        return [dict(row) for row in rows]


def start() -> None:
    init_db()
    os.environ.pop("OLLAMA_NUM_GPU", None)
    os.environ.pop("OLLAMA_LLM_LIBRARY", None)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Jarvis: http://127.0.0.1:{PORT}")
    print(f"Model: {MODEL} on GPU when VRAM is free")
    threading.Timer(0.5, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    server.serve_forever()


if __name__ == "__main__":
    start()
