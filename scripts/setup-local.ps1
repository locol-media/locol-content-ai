<#
.SYNOPSIS
    One-command local install: keys, users database, dependencies, optional LLM key.

.DESCRIPTION
    Runs every one-time setup step docs/deploy-local.md used to list by hand:

      1. checks uv is installed
      2. generates the JWT signing keypair      (scripts/generate-jwt-keys.ps1)
      3. generates the DB encryption key        (scripts/generate-db-encryption-key.ps1)
      4. creates the shared users database      (scripts/create_user_database.py)
      5. syncs BackEnd and Web dependencies     (uv sync)
      6. optionally writes an LLM provider key into BackEnd/config/default/llms/llm.yaml

    Step 6 defaults to leaving that file alone, and recommends setting your key
    in the app instead (Config Manager). llm.yaml is tracked by git, so a key
    written there can be committed into your own repo by accident; a key set in
    the app is encrypted at rest, per user, and never touches a tracked file.

    Every step detects whether it is already done and skips it, so the script
    is safe to re-run on a working install. It NEVER passes -Force to the key
    generators: regenerating keys/db_encryption.key makes every stored LLM API
    key permanently undecryptable, silently. To deliberately replace a key,
    run its generator yourself with -Force.

    Setup only - this does not start anything. Run .\run-web-debug.ps1 after.

.PARAMETER ApiKey
    LLM provider API key to write into llm.yaml. Passing this is itself the
    opt-in: it writes without asking. Remember llm.yaml is tracked by git.

.PARAMETER ApiStyle
    Provider style for -ApiKey: openai, gemini, anthropic, ollama, ... Matches
    the APIstyle field consumed by BackEnd/src/llm.py. Defaults to openai.

.PARAMETER Model
    Optional model identifier for -ApiKey, e.g. google-gla:gemini-2.0-flash.

.PARAMETER SkipLlm
    Leave llm.yaml alone without asking. This is already the default; the switch
    just suppresses the question. Set your key in the app afterwards.

.PARAMETER SkipSync
    Skip 'uv sync' for both projects. run-web-debug.ps1 syncs them anyway.

.PARAMETER NonInteractive
    Never prompt. Without -ApiKey this behaves like -SkipLlm for step 6, which
    is also what step 6 does by default.

.EXAMPLE
    .\scripts\setup-local.ps1

.EXAMPLE
    .\scripts\setup-local.ps1 -ApiStyle gemini -ApiKey "AIza..." -Model "google-gla:gemini-2.0-flash"

.EXAMPLE
    .\scripts\setup-local.ps1 -NonInteractive -SkipLlm
#>

[CmdletBinding()]
param(
    [string]$ApiKey,
    [string]$ApiStyle,
    [string]$Model,
    [switch]$SkipLlm,
    [switch]$SkipSync,
    [switch]$NonInteractive
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir
$backendDir = Join-Path $repoRoot "BackEnd"
$webDir = Join-Path $repoRoot "Web"
$keysDir = Join-Path $repoRoot "keys"
$llmYamlPath = Join-Path $backendDir "config\default\llms\llm.yaml"

# The APIkey value shipped in the committed llm.yaml. Anything equal to this (or
# empty) means "no provider key configured yet".
$llmPlaceholder = "LOCOL MEDIA AUTOMATIC INSERTION"

# Step name -> "created" / "already present" / "skipped (...)", printed as a
# summary at the end so a re-run makes it obvious nothing was touched.
$summary = [ordered]@{}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Write-Skip {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor DarkGray
}

function Write-Done {
    param([string]$Message)
    Write-Host "    $Message" -ForegroundColor Green
}

function Test-KeyFile {
    # A key file counts as present only if it is non-empty and, for a PEM, actually
    # starts with a PEM header. A truncated or placeholder file otherwise fails much
    # later as an opaque parse error from cryptography rather than as missing setup.
    # Same validation run-web-debug.ps1 does before starting the services.
    param([string]$Path, [switch]$Pem)

    $item = Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $item) { return $false }
    if ($item.Length -eq 0) { return $false }
    if ($Pem) {
        $firstLine = Get-Content -LiteralPath $Path -TotalCount 1 -ErrorAction SilentlyContinue
        if ($firstLine -notlike "-----BEGIN*") { return $false }
    }
    return $true
}

function Invoke-RepoScript {
    # Run a sibling .ps1 in a child PowerShell rather than dot-sourcing it, so its
    # own $ErrorActionPreference, param block and -Force guards stay entirely its
    # own - and so an execution-policy restriction on the *caller* doesn't also
    # have to be lifted for the callee.
    param([string]$Name)

    $path = Join-Path $scriptDir $Name
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Missing $path - the repo checkout is incomplete."
    }
    & powershell -NoProfile -ExecutionPolicy Bypass -File $path
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed (exit $LASTEXITCODE). See the error above."
    }
}

function Sync-UvProject {
    # Sync can fail on a file another process is holding open - a sharing violation
    # ("os error 32") from an editor, an indexer, or antivirus. That is genuinely
    # transient, so retry a few times before giving up.
    #
    # Anything else repeats identically on every attempt, so read the error rather
    # than waiting out the retries. In particular "os error 396 - The cloud operation
    # cannot be performed on a file with incompatible hardlinks" means a uv cache
    # entry is hardlinked into a cloud-synced folder; `uv cache clean` clears it.
    param(
        [string]$Dir,
        [int]$MaxAttempts = 5,
        [int]$DelaySeconds = 3
    )
    Push-Location $Dir
    try {
        for ($attempt = 1; $attempt -le $MaxAttempts; $attempt++) {
            uv sync
            if ($LASTEXITCODE -eq 0) {
                return $true
            }
            Write-Warning "uv sync failed in $Dir (attempt $attempt/$MaxAttempts) - retrying in $DelaySeconds s in case a file was momentarily locked. If the error above repeats unchanged, it is not a lock; read it."
            Start-Sleep -Seconds $DelaySeconds
        }
        return $false
    } finally {
        Pop-Location
    }
}

function Get-LlmField {
    # Reads a top-level scalar field out of the (single-document, flat) llm.yaml
    # without needing a YAML parser - the whole point of this script is to run
    # before any Python environment exists.
    param([string[]]$Lines, [string]$Field)

    foreach ($line in $Lines) {
        if ($line -match "^\s*$([regex]::Escape($Field))\s*:\s*(.*?)\s*$") {
            return $Matches[1].Trim('"').Trim("'")
        }
    }
    return $null
}

function Set-LlmField {
    # Replaces a field's value in place, appending the line if it isn't there.
    # Line-level rather than re-serialising the file: llm.yaml may carry APIurl or
    # extra documents, all of which load_llms.py honours and a rewrite would drop.
    param([string[]]$Lines, [string]$Field, [string]$Value)

    # Single-quoted YAML, not double: it has no escape sequences at all beyond ''
    # for a literal quote, so nothing an API key can contain - a backslash, a $ -
    # changes the parsed value or breaks out of the string.
    $quoted = "'" + ($Value -replace "'", "''") + "'"
    $replaced = $false
    $out = foreach ($line in $Lines) {
        if (-not $replaced -and $line -match "^\s*$([regex]::Escape($Field))\s*:") {
            $replaced = $true
            "${Field}: $quoted"
        } else {
            $line
        }
    }
    if (-not $replaced) {
        $out = @($out) + @("${Field}: $quoted")
    }
    return @($out)
}

Write-Host "Locol Content AI local setup" -ForegroundColor White
Write-Host "Repo root: $repoRoot" -ForegroundColor DarkGray

# --- 1. Pre-flight -----------------------------------------------------------

Write-Step "Checking prerequisites"

# A VIRTUAL_ENV inherited from the parent shell (typically BackEnd\.venv, left over
# from activating it by hand) does not match whichever project uv is syncing, so uv
# warns and ignores it on every call. Clear it so each `uv` command uses its own .venv.
$env:VIRTUAL_ENV = $null

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw (@(
        "uv is not on PATH. Both services use it as their package manager."
        ""
        "Install it, then re-run this script:"
        "  https://docs.astral.sh/uv/getting-started/installation/"
        ""
        "On Windows:"
        '  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
        ""
        "You do not need to install Python separately - uv provisions its own"
        "interpreter for the Python 3.12+ both projects require."
    ) -join [Environment]::NewLine)
}
Write-Done "uv found: $((Get-Command uv).Source)"

# --- 2. JWT key pairs --------------------------------------------------------

Write-Step "JWT key pairs (keys/{private,public,enc_private,enc_public}_key.pem)"

# Four files, two pairs: RSA for the signature, EC P-256 for the JWE wrapper the
# signed token is sealed in. See scripts/generate-jwt-keys.ps1 for which service
# holds which half. It is all four or none - any partial set means some part of
# the token path has no usable key.
$keyNames = @("private_key.pem", "public_key.pem", "enc_private_key.pem", "enc_public_key.pem")
$presentKeys = @()
$missingKeys = @()
foreach ($keyName in $keyNames) {
    $keyPath = Join-Path $keysDir $keyName
    if (Test-KeyFile -Path $keyPath -Pem) { $presentKeys += $keyPath } else { $missingKeys += $keyPath }
}

if ($missingKeys.Count -eq 0) {
    Write-Skip "Already present - skipping."
    $summary["JWT key pairs"] = "already present"
} elseif ($presentKeys.Count -gt 0) {
    # An incomplete set is worse than none: the generator refuses to write over the
    # files that exist, and a mismatched pair fails on every login. This script never
    # passes -Force, so hand the decision back rather than guessing.
    throw (@(
        "Found an incomplete set of JWT keys:"
        ($presentKeys | ForEach-Object { "  present: $_" })
        ($missingKeys | ForEach-Object { "  missing: $_" })
        ""
        "A mismatched or partial set fails on every login, and this script will not"
        "overwrite existing keys. Regenerate all four deliberately:"
        "  ./scripts/generate-jwt-keys.ps1 -Force"
        ""
        "That only invalidates existing sessions - users just log in again. Nothing"
        "else in the install is affected."
    ) -join [Environment]::NewLine)
} else {
    Invoke-RepoScript -Name "generate-jwt-keys.ps1"
    $summary["JWT key pairs"] = "created"
}

# --- 3. Database encryption key ----------------------------------------------

Write-Step "Database encryption key (keys/db_encryption.key)"

$dbKeyPath = Join-Path $keysDir "db_encryption.key"
if (Test-KeyFile -Path $dbKeyPath) {
    Write-Skip "Already present - skipping."
    $summary["DB encryption key"] = "already present"
} else {
    Invoke-RepoScript -Name "generate-db-encryption-key.ps1"
    $summary["DB encryption key"] = "created"
    Write-Host ""
    Write-Warning (@(
        "This key is not disposable. It encrypts the stored LLM API keys of every"
        "user, there is one key for all of them, and there is no backup other than"
        "$dbKeyPath. If you lose or replace it after real keys have been saved, those"
        "values are permanently unrecoverable - and silently so. Back the file up out"
        "of band before storing any real data."
    ) -join [Environment]::NewLine)
}

# --- 4. Shared users database ------------------------------------------------

Write-Step "Shared users database (BackEnd/db/persistent_data.sqlite)"

$dbPath = Join-Path $backendDir "db\persistent_data.sqlite"
$dbItem = Get-Item -LiteralPath $dbPath -ErrorAction SilentlyContinue
$dbUsable = $false
if ($dbItem -and $dbItem.Length -gt 0) {
    # A truncated or placeholder file otherwise fails later as "file is not a
    # database". Every real SQLite file opens with this 16-byte magic string.
    $header = [byte[]]::new(16)
    $stream = [System.IO.File]::OpenRead($dbPath)
    try {
        $read = $stream.Read($header, 0, 16)
    } finally {
        $stream.Dispose()
    }
    $dbUsable = ($read -ge 16 -and [Text.Encoding]::ASCII.GetString($header, 0, 15) -eq "SQLite format 3")
}

if ($dbUsable) {
    Write-Skip "Already present - skipping."
    $summary["Users database"] = "already present"
} else {
    if ($dbItem) {
        throw "$dbPath exists but is not a usable SQLite database. Move it aside and re-run this script, or run 'uv run --project BackEnd python scripts/create_user_database.py --force' if you are sure it is disposable."
    }
    Push-Location $repoRoot
    try {
        uv run --project BackEnd python scripts/create_user_database.py
        if ($LASTEXITCODE -ne 0) {
            throw "create_user_database.py failed (exit $LASTEXITCODE). See the error above."
        }
    } finally {
        Pop-Location
    }
    Write-Done "Created $dbPath"
    $summary["Users database"] = "created"
}

# --- 5. Dependencies ---------------------------------------------------------

Write-Step "Python dependencies (uv sync)"

if ($SkipSync) {
    Write-Skip "-SkipSync given - skipping. run-web-debug.ps1 syncs both projects anyway."
    $summary["Dependencies"] = "skipped (-SkipSync)"
} else {
    Write-Host "    Syncing BackEnd..." -ForegroundColor DarkGray
    if (-not (Sync-UvProject -Dir $backendDir)) {
        throw "uv sync kept failing in $backendDir - read the error above, it is not a transient lock."
    }
    Write-Host "    Syncing Web..." -ForegroundColor DarkGray
    if (-not (Sync-UvProject -Dir $webDir)) {
        throw "uv sync kept failing in $webDir - read the error above, it is not a transient lock."
    }
    Write-Done "Both projects synced."
    $summary["Dependencies"] = "synced"
}

# --- 6. LLM provider key -----------------------------------------------------

Write-Step "LLM provider key (BackEnd/config/default/llms/llm.yaml)"

if (-not (Test-Path -LiteralPath $llmYamlPath)) {
    Write-Warning "$llmYamlPath not found - skipping. Restore it from git to configure a provider."
    $summary["LLM provider key"] = "skipped (llm.yaml missing)"
} elseif ($SkipLlm) {
    Write-Skip "-SkipLlm given - leaving llm.yaml alone. Set your key in the app."
    $summary["LLM provider key"] = "set it in the app (-SkipLlm)"
} else {
    $lines = @(Get-Content -LiteralPath $llmYamlPath)
    $currentKey = Get-LlmField -Lines $lines -Field "APIkey"
    $configured = $currentKey -and $currentKey -ne $llmPlaceholder

    if ($configured -and -not $ApiKey) {
        Write-Skip "A provider key is already configured - skipping."
        $summary["LLM provider key"] = "already present"
    } else {
        $newKey = $ApiKey
        $newStyle = $ApiStyle
        $newModel = $Model

        if (-not $newKey) {
            if ($NonInteractive) {
                Write-Skip "-NonInteractive given and no -ApiKey - leaving llm.yaml alone."
                $newKey = $null
            } else {
                # Recommend the in-app route and state the risk BEFORE offering the
                # choice. Writing here seeds the same shared key into every future
                # user's database; a key set in Config Manager is encrypted at rest,
                # belongs to one user, and never touches a tracked file.
                Write-Host "    Recommended: leave this file alone and set your key in the app."
                Write-Host ""
                Write-Host "      1. .\run-web-debug.ps1, then open http://localhost:8501"
                Write-Host "      2. Register an account"
                Write-Host "      3. Sidebar '$([char]0x2699) Settings and Tools' -> '$([char]0x2699) Config Manager'"
                Write-Host "      4. Tab 'LLMs' -> expand 'Locol AI Default' -> set 'API Key' -> 'Update'"
                Write-Host ""
                Write-Warning "llm.yaml is TRACKED BY GIT (unlike keys/, which is ignored). A key written here can be committed into your own repo, and it is seeded into every user's database rather than just yours."
                Write-Host ""
                $answer = (Read-Host "    Write a provider key into llm.yaml anyway? [y/N]").Trim()
                if ($answer -match '^(y|yes)$') {
                    $newKey = (Read-Host "    API key (blank to skip)").Trim()
                    if ($newKey) {
                        if (-not $newStyle) {
                            $styleAnswer = (Read-Host "    API style [openai, gemini, anthropic, ollama] (default: openai)").Trim()
                            $newStyle = if ($styleAnswer) { $styleAnswer } else { "openai" }
                        }
                        if (-not $newModel) {
                            $newModel = (Read-Host "    Model (blank for the provider default)").Trim()
                        }
                    }
                } else {
                    Write-Skip "Leaving llm.yaml alone."
                    $newKey = $null
                }
            }
        }

        if ($newKey) {
            if (-not $newStyle) { $newStyle = "openai" }
            $lines = Set-LlmField -Lines $lines -Field "APIkey" -Value $newKey
            $lines = Set-LlmField -Lines $lines -Field "APIstyle" -Value $newStyle
            if ($newModel) {
                $lines = Set-LlmField -Lines $lines -Field "model" -Value $newModel
            }
            # LF endings, no BOM - matches how the file is committed, so writing a key
            # doesn't show up in git as a whole-file rewrite.
            $encoding = New-Object System.Text.UTF8Encoding($false)
            [System.IO.File]::WriteAllText($llmYamlPath, (($lines -join "`n") + "`n"), $encoding)
            Write-Done "Wrote APIstyle '$newStyle' and your key to $llmYamlPath"
            Write-Warning "Do not commit your key: 'git diff -- BackEnd/config/default/llms/llm.yaml' will show it."
            $summary["LLM provider key"] = "written to llm.yaml ($newStyle)"
        } else {
            Write-Skip "llm.yaml still holds the placeholder. Set your key in the app:"
            Write-Skip "  '$([char]0x2699) Config Manager' -> 'LLMs' -> 'Locol AI Default' -> 'API Key'"
            $summary["LLM provider key"] = "set it in the app (recommended)"
        }
    }
}

# --- Summary -----------------------------------------------------------------

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host ""
foreach ($entry in $summary.GetEnumerator()) {
    Write-Host ("  {0,-20} {1}" -f $entry.Key, $entry.Value)
}
Write-Host ""
Write-Host "Next: start both services from the repo root" -ForegroundColor Cyan
Write-Host "  .\run-web-debug.ps1"
Write-Host ""
Write-Host "Then open http://localhost:8501 and register an account."
Write-Host "Set your LLM provider key there: '$([char]0x2699) Settings and Tools' -> '$([char]0x2699) Config Manager'"
Write-Host "-> 'LLMs' -> 'Locol AI Default' -> 'API Key' -> 'Update'."
Write-Host "See docs/deploy-local.md for ports, configuration and troubleshooting."
