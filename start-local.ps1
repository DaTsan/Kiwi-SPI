param([switch]$NoBuild)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker Desktop is required. Install it and enable Linux containers.'
}

function New-LocalSecret([int]$Length = 24) {
    $secretBytes = New-Object byte[] $Length
    $secretGenerator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $secretGenerator.GetBytes($secretBytes) }
    finally { $secretGenerator.Dispose() }
    return -join ($secretBytes | ForEach-Object { $_.ToString('x2') })
}

$envPath = Join-Path $PSScriptRoot '.env.local'
if (-not (Test-Path -LiteralPath $envPath)) {
    $envLines = @(
        'KIWI_ADMIN_USERNAME=admin'
        'KIWI_ADMIN_EMAIL=admin@localhost.local'
        "KIWI_ADMIN_PASSWORD=Kiwi-$(New-LocalSecret 8)"
        "KIWI_DB_PASSWORD=$(New-LocalSecret)"
        "KIWI_DB_ROOT_PASSWORD=$(New-LocalSecret)"
        "KIWI_SECRET_KEY=$(New-LocalSecret 48)"
    )
    [System.IO.File]::WriteAllText($envPath, ($envLines -join "`n") + "`n", (New-Object System.Text.UTF8Encoding($false)))
    Write-Host 'Created .env.local with local credentials.'
}

$dockerReady = $false
try {
    docker info --format '{{.ServerVersion}}' *> $null
    $dockerReady = $LASTEXITCODE -eq 0
} catch {
    $dockerReady = $false
}
if (-not $dockerReady) {
    docker desktop start
    if ($LASTEXITCODE -ne 0) { throw 'Could not start Docker Desktop. Open it and wait for the engine to start.' }
}

$composeArgs = @('compose', '--env-file', '.env.local', '-f', 'compose.local.yaml', 'up', '-d', '--wait', '--wait-timeout', '240')
if (-not $NoBuild) { $composeArgs += '--build' }
& docker @composeArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Kiwi startup failed. See: docker compose --env-file .env.local -f compose.local.yaml logs --tail 100'
}

Write-Host ''
Write-Host 'Kiwi SPI is running at http://127.0.0.1:8000'
Write-Host 'Login: admin (password: KIWI_ADMIN_PASSWORD in .env.local).'
Write-Host 'Stop with: .\stop-local.ps1'
