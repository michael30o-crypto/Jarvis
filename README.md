# Jarvis

A private local assistant for this Windows laptop.

## Start

Run `run-jarvis.bat`. The control panel opens at <http://127.0.0.1:8765>.

## Current stack

- Qwen3 8B through Ollama on the RTX 5060
- OpenWhispr for push-to-talk dictation
- Browser speech output with selectable voice, speed, and pitch
- SQLite memory for messages, tasks, and notes
- Allowlisted app and URL controls

## Allowed actions

Jarvis can launch Calculator, Notepad, Explorer, ComfyUI, Qwen3-TTS, Applio, and OpenWhispr. It can open HTTP/HTTPS URLs, capture tasks, complete tasks, and save or recall notes.

It cannot run arbitrary shell commands, delete files, access passwords, or make payments. Keep Ollama and Jarvis bound to localhost.

## Storage

- Ollama runtime: approximately 1.7 GB
- Qwen3 8B Q4 model: approximately 5.2 GB
- Jarvis code and local memory: under 100 MB initially

The RTX 5060 has 8 GB of VRAM. Qwen3 8B needs about 5.6 GB, so Jarvis unloads ComfyUI, Applio, and Qwen-TTS before a reply, then unloads the language model before speaking. Those apps can still be launched, but they cannot all stay loaded at once. The earlier CUDA crash was that VRAM contention, not a broken GPU.
