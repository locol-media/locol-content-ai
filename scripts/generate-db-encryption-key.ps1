<#
.SYNOPSIS
    Generate a fresh Fernet key for encrypting APIkey values at rest.

.DESCRIPTION
    Writes db_encryption.key into -OutDir. BackEnd's config_manager.py,
    load_llms.py, and llm.py all read this same key via the
    LOCOL_DB_ENCRYPTION_KEY_LOCATION env var (see BackEnd/src/db_crypto.py).

    The key is 32 cryptographically random bytes in URL-safe base64 - the
    format cryptography.fernet.Fernet expects.

    Uses only .NET cryptography, so it runs on stock Windows PowerShell 5.1
    with no OpenSSL or Python toolchain installed.

    WARNING: unlike the JWT keypair, this key protects data at rest, not just
    sessions. Once any APIkey values have been encrypted under a given key,
    regenerating the key with -Force makes those values permanently
    undecryptable. db_crypto.py raises rather than guessing, and leaves the
    stored values alone, so the original key still recovers them - but nothing
    else will. Only use -Force before any real data has been encrypted with the
    current key.

.PARAMETER OutDir
    Directory to write the key into. Defaults to the repo-root keys/ directory,
    resolved from this script's own location.

.PARAMETER Force
    Overwrite an existing key in -OutDir.

.EXAMPLE
    ./scripts/generate-db-encryption-key.ps1
#>

[CmdletBinding()]
param(
    [string]$OutDir,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

if (-not $OutDir) {
    $OutDir = Join-Path $repoRoot "keys"
}

function Protect-KeyFile {
    param([string]$Path)

    # Best-effort equivalent of chmod 600: drop inherited ACEs, grant only the
    # current user. Never fatal - a restrictive ACL is a bonus, not a guarantee.
    try {
        $account = "$env:USERDOMAIN\$env:USERNAME"
        & icacls $Path /inheritance:r /grant:r "${account}:(R,W)" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Could not restrict permissions on $Path (icacls exit $LASTEXITCODE). Protect this file yourself."
        }
    } catch {
        Write-Warning "Could not restrict permissions on ${Path}: $($_.Exception.Message)"
    }
}

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}
$OutDir = (Resolve-Path -LiteralPath $OutDir).Path

$keyPath = Join-Path $OutDir "db_encryption.key"

if (-not $Force -and (Test-Path -LiteralPath $keyPath)) {
    throw "Refusing to overwrite existing key at $keyPath. Pass -Force to replace it."
}

$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
try {
    $rng.GetBytes($bytes)
} finally {
    $rng.Dispose()
}

# Fernet keys use the URL-safe base64 alphabet.
$key = [Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')

# No BOM, no trailing newline - db_crypto.py strips whitespace, but keep the
# file byte-identical to what Fernet.generate_key() produced.
[System.IO.File]::WriteAllText($keyPath, $key, (New-Object System.Text.UTF8Encoding($false)))
Protect-KeyFile -Path $keyPath

Write-Host "Wrote $keyPath" -ForegroundColor Green
