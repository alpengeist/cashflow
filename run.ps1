$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Error "uv is not installed or not available on PATH."
}

uv run cashflow
