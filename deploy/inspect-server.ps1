# Read-only preflight. Does not read env files, tokens, or connection strings.
$ErrorActionPreference = 'Continue'
$os = Get-CimInstance Win32_OperatingSystem
[pscustomobject]@{
    OperatingSystem = $os.Caption
    Version = $os.Version
    Architecture = $os.OSArchitecture
    MemoryGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
} | Format-List

Get-Service -Name sshd, docker, com.docker.service -ErrorAction SilentlyContinue |
    Select-Object Name, Status | Format-Table

if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker version --format 'Docker client: {{.Client.Version}}; server: {{if .Server}}{{.Server.Version}}{{else}}unavailable{{end}}'
    docker info --format 'Container OS: {{.OSType}}; architecture: {{.Architecture}}; host: {{.OperatingSystem}}'
    docker compose version
} else {
    Write-Output 'Docker CLI is not installed or is not on PATH.'
}

if (Get-Command Get-VM -ErrorAction SilentlyContinue) {
    Get-VM | Select-Object Name, State, Generation | Format-Table
}
