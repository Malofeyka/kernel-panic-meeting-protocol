[CmdletBinding()]
param(
    [ValidateRange(1, 262144)]
    [int]$ContextSize = 4096,

    [ValidateRange(0, 128)]
    [int]$GpuLayers = 0,

    [ValidateRange(1, 65535)]
    [int]$Port = 8080
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$ModelPath = Join-Path $ProjectRoot "models/gigachat/GigaChat3.1-10B-A1.8B-q4_K_M.gguf"
$ServerPath = Join-Path $ProjectRoot "tools/llama.cpp/llama-server.exe"

if (-not (Test-Path $ModelPath -PathType Leaf)) {
    throw "Модель не найдена: $ModelPath. Сначала запустите scripts/download_gigachat.py."
}
if (-not (Test-Path $ServerPath -PathType Leaf)) {
    throw "llama-server не найден: $ServerPath. Установите llama.cpp b11675."
}

& $ServerPath `
    --model $ModelPath `
    --host 127.0.0.1 `
    --port $Port `
    --ctx-size $ContextSize `
    --n-gpu-layers $GpuLayers `
    --jinja `
    -np 1

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
