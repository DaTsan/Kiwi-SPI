$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
docker compose --env-file .env.local -f compose.local.yaml down
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the local Kiwi environment.' }
Write-Host 'Kiwi stopped. The database and uploaded files are preserved.'
