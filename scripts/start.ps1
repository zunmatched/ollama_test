param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run uv sync first.' }
$runtimePath = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MODELS = Join-Path $runtimePath 'models'
$env:OLLAMA_MODEL = 'stock-agent:4b'
$ollamaPath = Join-Path $runtimePath 'ollama\ollama.exe'
if (-not (Test-Path -LiteralPath $ollamaPath)) {
    $installed = Get-Command ollama -ErrorAction SilentlyContinue
    if ($installed) { $ollamaPath = $installed.Source } else { throw 'Install Ollama first. See README.md.' }
    Remove-Item Env:OLLAMA_MODELS -ErrorAction SilentlyContinue
}
try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 2 }
catch {
    Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WindowStyle Hidden -WorkingDirectory $projectRoot -RedirectStandardOutput "$runtimePath\ollama-out.log" -RedirectStandardError "$runtimePath\ollama-error.log" | Out-Null
    $ready = $false
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        Start-Sleep -Seconds 1
        try { $null = Invoke-RestMethod 'http://127.0.0.1:11434/api/version' -TimeoutSec 1; $ready = $true; break } catch {}
    }
    if (-not $ready) { throw 'Ollama failed to start; inspect .runtime/ollama-error.log.' }
}
$models = Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5
if ($models.models.name -notcontains $env:OLLAMA_MODEL) { throw 'Run ollama create stock-agent:4b -f models/Modelfile first (see README).' }
try { $null = Invoke-RestMethod 'http://127.0.0.1:8765/api/status' -TimeoutSec 5; $webReady = $true } catch { $webReady = $false }
if (-not $webReady) {
    Start-Process -FilePath $pythonPath -ArgumentList '-m','uvicorn','src.app:app','--host','127.0.0.1','--port','8765' -WindowStyle Hidden -WorkingDirectory $projectRoot -RedirectStandardOutput "$runtimePath\web-out.log" -RedirectStandardError "$runtimePath\web-error.log" | Out-Null
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        Start-Sleep -Seconds 1
        try { $null = Invoke-RestMethod 'http://127.0.0.1:8765/api/status' -TimeoutSec 5; $webReady = $true; break } catch {}
    }
}
if (-not $webReady) { throw 'Web service failed to start; inspect .runtime/web-error.log.' }
Write-Output 'Demo ready: http://127.0.0.1:8765'
if (-not $NoBrowser) { Start-Process 'http://127.0.0.1:8765' }
