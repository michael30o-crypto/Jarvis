$markers = @(
    "ComfyUI_windows_portable",
    "\\Applio\\",
    "Qwen3-TTS",
    "qwen3-tts",
    "qwen-tts-demo"
)

Get-CimInstance Win32_Process | Where-Object {
    $commandLine = [string]$_.ExecutablePath + " " + [string]$_.CommandLine
    @($markers | Where-Object { $commandLine -like ("*" + $_ + "*") }).Count -gt 0
} | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}
