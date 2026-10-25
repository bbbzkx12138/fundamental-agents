$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    & .\.venv\Scripts\python.exe -m fundamental_agent.check
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
