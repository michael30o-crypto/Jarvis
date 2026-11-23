@echo off
setlocal
cd /d "%~dp0"
set OLLAMA_LLM_LIBRARY=
set OLLAMA_NUM_GPU=

echo Freeing the RTX 5060 so Jarvis can use the GPU...
taskkill /F /IM qwen-tts-demo.exe >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-gpu-apps.ps1"

taskkill /F /IM ollama.exe >nul 2>&1
taskkill /F /IM "ollama app.exe" >nul 2>&1
timeout /t 2 /nobreak >nul
start "Jarvis Ollama" /MIN "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" serve
timeout /t 3 /nobreak >nul
"%~dp0venv\Scripts\python.exe" "%~dp0jarvis.py"
