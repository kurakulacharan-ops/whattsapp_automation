$ErrorActionPreference = 'Stop'

$envPath = Join-Path $PSScriptRoot '.env.docker-local'
if (-not (Test-Path -LiteralPath $envPath)) {
    Write-Error 'deploy/.env.docker-local is missing.'
    exit 1
}

$containerEnv = & docker inspect attendance-local-dev-sqlserver-1 --format '{{range .Config.Env}}{{println .}}{{end}}' 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error 'Could not inspect the local SQL container.'
    exit 1
}

$saLine = $containerEnv | Where-Object { $_ -match '^(MSSQL_SA_PASSWORD|SA_PASSWORD)=' } | Select-Object -First 1
if (-not $saLine) {
    Write-Error 'The local SQL container does not expose its configured SA password.'
    exit 1
}
$saPassword = $saLine.Substring($saLine.IndexOf('=') + 1)

$lines = [System.Collections.Generic.List[string]]::new()
foreach ($line in [System.IO.File]::ReadAllLines($envPath)) { $lines.Add($line) }
$passwordLine = -1
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^MSSQL_PASSWORD=') { $passwordLine = $i; break }
}
if ($passwordLine -ge 0) {
    $lines[$passwordLine] = "MSSQL_PASSWORD=$saPassword"
} else {
    $lines.Add("MSSQL_PASSWORD=$saPassword")
}
[System.IO.File]::WriteAllLines($envPath, $lines, [System.Text.UTF8Encoding]::new($false))
Write-Host 'Local app SQL credentials synchronized. No password value was displayed.'
