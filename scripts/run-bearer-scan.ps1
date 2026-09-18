<#
.SYNOPSIS
    Run a Bearer SAST scan over first-party source.

.DESCRIPTION
    Writes the report to bearer.log at the repo root (already gitignored).

    Scope comes from bearer.yml and suppressions from bearer.ignore, both
    committed at the repo root - see the comments in bearer.yml for why
    dependencies and build output are excluded.

    Bearer does not need to be installed locally: if it is not on PATH this
    falls back to the official container image, which is how the report is
    normally produced.

.PARAMETER Out
    Write the report here. Defaults to <repo>/bearer.log.

.PARAMETER Severity
    Comma-separated severities to report. Defaults to critical,high,medium,low.

.PARAMETER Fail
    Exit non-zero if any finding is reported. Off by default so an ordinary
    scan always produces a readable report.

.EXAMPLE
    ./scripts/run-bearer-scan.ps1
#>

[CmdletBinding()]
param(
    [string]$Out,
    [string]$Severity = "critical,high,medium,low",
    [switch]$Fail
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

if (-not $Out) {
    $Out = Join-Path $repoRoot "bearer.log"
}

$bearerImage = "bearer/bearer:latest"

# Without --exit-code=0 Bearer returns non-zero whenever it reports a finding,
# which reads as a script failure rather than a completed scan.
$exitCodeArgs = @("--exit-code=0")
if ($Fail) {
    $exitCodeArgs = @()
}

$bearerCmd = Get-Command bearer -ErrorAction SilentlyContinue
$dockerCmd = Get-Command docker -ErrorAction SilentlyContinue

if ($bearerCmd) {
    Write-Host "Scanning with local bearer..." -ForegroundColor Cyan
    & bearer scan $repoRoot --severity $Severity @exitCodeArgs |
        Tee-Object -FilePath $Out
} elseif ($dockerCmd) {
    Write-Host "bearer not on PATH; scanning with $bearerImage..." -ForegroundColor Cyan
    # /tmp/scan matches the paths in previous reports, so findings stay
    # comparable across runs. Mounted read-only: a scan never writes to the tree.
    & docker run --rm `
        -v "${repoRoot}:/tmp/scan:ro" `
        $bearerImage scan /tmp/scan --severity $Severity @exitCodeArgs |
        Tee-Object -FilePath $Out
} else {
    throw "Neither bearer nor docker found on PATH. Install Bearer (https://docs.bearer.com/guides/install/) or Docker and rerun."
}

Write-Host ""
Write-Host "Report written to $Out" -ForegroundColor Green
