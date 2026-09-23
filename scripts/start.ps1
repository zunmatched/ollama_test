param([switch]$NoBrowser, [ValidateSet('auto','sqlite','postgres')][string]$Backend = 'auto', [ValidateSet('qwen3.5:4b','stock-agent:4b')][string]$Model = 'qwen3.5:4b')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $projectRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run uv sync first.' }
$runtimePath = Join-Path $projectRoot '.runtime'
New-Item -ItemType Directory -Force -Path $runtimePath | Out-Null
if ($Backend -eq 'auto') {
    if (Test-Path -LiteralPath "$runtimePath\postgres-reader.json") { $Backend = 'postgres' } else { $Backend = 'sqlite' }
}
$env:STOCK_BACKEND = $Backend
if ($Backend -eq 'postgres') {
    if (-not (Test-Path -LiteralPath "$runtimePath\postgres-reader.json")) { throw 'Run scripts/setup-postgres.py --wsl first.' }
    $keeperPath = Join-Path $runtimePath 'wsl-keeper.pid'
    $keeper = $null
    if (Test-Path -LiteralPath $keeperPath) { $keeper = Get-Process -Id (Get-Content $keeperPath) -ErrorAction SilentlyContinue }
    if (-not $keeper -or $keeper.ProcessName -ne 'wsl') {
        $keeper = Start-Process -FilePath wsl.exe -ArgumentList '-d','Ubuntu-22.04','--','sleep','infinity' -WindowStyle Hidden -PassThru
        Set-Content -LiteralPath $keeperPath -Value $keeper.Id
    }
    $wslRoot = '/mnt/' + $projectRoot.Substring(0,1).ToLower() + $projectRoot.Substring(2).Replace('\','/')
    & wsl.exe -d Ubuntu-22.04 --cd $wslRoot -- docker compose --project-name ollama-stock --env-file .runtime/postgres.env up -d --wait
    if ($LASTEXITCODE -ne 0) { throw 'Local PostgreSQL failed to start.' }
}
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MODELS = Join-Path $runtimePath 'models'
$env:OLLAMA_MODEL = $Model
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
if ($models.models.name -notcontains $env:OLLAMA_MODEL) { throw "Model $env:OLLAMA_MODEL is missing. See README.md for download instructions." }
try { $webStatus = Invoke-RestMethod 'http://127.0.0.1:8765/api/status' -TimeoutSec 5; $webReady = $true } catch { $webReady = $false }
if ($webReady) {
    $activeBackend = if ($webStatus.snapshot.database_backend -eq 'PostgreSQL + pgvector') { 'postgres' } else { 'sqlite' }
    if ($activeBackend -ne $Backend -or $webStatus.ollama.model -ne $Model) {
        if ($webStatus.busy) { throw 'A query is running. Finish it before switching database or model.' }
        $listener = Get-NetTCPConnection -LocalPort 8765 -State Listen
        $webProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
        if ($webProcess.CommandLine -notmatch 'uvicorn.*src\.app:app') { throw 'Port 8765 belongs to another service; not stopping it.' }
        Stop-Process -Id $listener.OwningProcess
        $webReady = $false
    }
}
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
