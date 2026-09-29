<#
.SYNOPSIS
    Starts BackEnd (FastAPI) and Web (Streamlit) together for local debugging.

.DESCRIPTION
    BackEnd is launched in its own console window (uvicorn, reload scoped to src/).
    Web is run in the foreground of this window (streamlit) so its logs stay
    directly visible. Ctrl+C in this window stops both processes.

.PARAMETER DebugLogging
    Raises Streamlit's log level from info to debug. Debug logs every file-watcher
    event - including the wall of __pycache__ churn Python emits while importing the
    app's own modules - so it buries anything useful. Use it only when diagnosing
    session or hot-reload behaviour.

.PARAMETER BackendPort
    Port for the FastAPI BackEnd. Defaults to $env:LOCOL_BACKEND_PORT, then 8000.
    The value is exported to the Web process too, so its LOCOL_API_URL default
    follows whichever port was actually used.

.PARAMETER WebPort
    Port for the Streamlit Web app. Defaults to $env:LOCOL_WEB_PORT, then 8501.

.EXAMPLE
    .\run-web-debug.ps1
    .\run-web-debug.ps1 -DebugLogging
    .\run-web-debug.ps1 -BackendPort 9000 -WebPort 9501
#>

param(
    [switch]$DebugLogging,
    [int]$BackendPort = $(if ($env:LOCOL_BACKEND_PORT) { $env:LOCOL_BACKEND_PORT } else { 8000 }),
    [int]$WebPort = $(if ($env:LOCOL_WEB_PORT) { $env:LOCOL_WEB_PORT } else { 8501 })
)

$ErrorActionPreference = "Stop"

# A VIRTUAL_ENV inherited from the parent shell (typically BackEnd\.venv, left over from
# activating it by hand) does not match whichever project uv is syncing, so uv warns and
# ignores it on every call. Clear it so each `uv` command just uses its project's .venv.
$env:VIRTUAL_ENV = $null

# Both child processes inherit these. The BackEnd is started via the uvicorn CLI below
# so it takes --port rather than this, but Web's LOCOL_API_URL default is derived from
# LOCOL_BACKEND_PORT (see Web/src/locol-lib/apiClient.py) - without exporting it, a
# -BackendPort run would leave Web calling 8000 while the API listens elsewhere.
$env:LOCOL_BACKEND_PORT = $BackendPort
$env:LOCOL_WEB_PORT = $WebPort

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $repoRoot "BackEnd"
$webDir = Join-Path $repoRoot "Web"

function Sync-UvProject {
    # Sync can fail on a file another process is holding open - a sharing violation
    # ("os error 32") from an editor, an indexer, or antivirus. That is genuinely
    # transient, so retry a few times before giving up.
    #
    # Anything else repeats identically on every attempt, so read the error rather
    # than waiting out the retries. In particular "os error 396 - The cloud operation
    # cannot be performed on a file with incompatible hardlinks" means a uv cache
    # entry is hardlinked into a cloud-synced folder. uv installs by
    # hardlinking out of its shared cache, and the sync client's filter refuses to
    # add another link. `uv cache clean` clears it permanently.
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

function Assert-VenvEntryPoint {
    # Fails with an explicit message if <Dir>\.venv\Scripts\<Exe> cannot launch.
    #
    # Console scripts in a uv venv are Windows "trampoline" .exe shims that carry the
    # absolute path of their own venv's python.exe appended to the end of the file.
    # That path is baked in at install time and nothing rewrites it afterwards, so
    # renaming or moving the checkout leaves every shim in both .venv directories
    # pointing at a python.exe that no longer exists. The shim then dies with the bare
    # line "Failed to canonicalize script path" - no mention of the path it tried, no
    # mention of which shim - and the `uv sync` above does NOT repair it: the packages
    # are still installed at the right versions, so sync has nothing to do. Checking
    # the baked-in path here costs microseconds and names the real cause.
    param([string]$Dir, [string]$Exe)

    $exePath = Join-Path $Dir ".venv\Scripts\$Exe"
    $problem = $null
    if (-not (Test-Path -LiteralPath $exePath)) {
        $problem = "$exePath is missing"
    } else {
        $bytes = [System.IO.File]::ReadAllBytes($exePath)
        $tailLength = [Math]::Min(1024, $bytes.Length)
        $tail = [Text.Encoding]::ASCII.GetString($bytes, $bytes.Length - $tailLength, $tailLength)
        # The last such path in the footer is the interpreter the shim execs.
        $paths = [regex]::Matches($tail, '[A-Za-z]:\\[^\x00\r\n"]*?pythonw?\.exe')
        if ($paths.Count -gt 0) {
            $embedded = $paths[$paths.Count - 1].Value
            if (-not (Test-Path -LiteralPath $embedded)) {
                $problem = "$Exe is hardwired to $embedded, which does not exist"
            }
        }
        # No match means a shim layout this check doesn't recognise (a future uv, or a
        # plain .exe). Say nothing rather than guess it is broken.
    }
    if (-not $problem) { return }

    throw (@(
        "The $Exe launcher in $Dir\.venv is unusable:"
        "  - $problem"
        ""
        "This is what a moved or renamed checkout looks like. uv bakes the absolute path"
        "of the venv's python.exe into every console-script .exe it installs, so the"
        "shims still refer to wherever this repo used to live. Run one directly and all"
        "it prints is 'Failed to canonicalize script path'."
        ""
        "Rebuild the launchers, keeping the same dependency versions:"
        "  uv sync --reinstall --project $Dir"
        ""
        "Both projects are affected together, so the other one likely needs it too:"
        "  uv sync --reinstall --project $backendDir"
        "  uv sync --reinstall --project $webDir"
        ""
        "Deleting $Dir\.venv and re-running this script also works, and takes longer."
    ) -join [Environment]::NewLine)
}

function Stop-ProcessTree {
    # Children first: $backend.Id is the `uv` launcher, and uvicorn - plus, under
    # --reload, the worker it spawns - are its descendants. Killing only the launcher
    # leaves them holding the BackEnd port, which is what breaks the *next* run of this script.
    param([int]$ProcessId)
    Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue |
        ForEach-Object { Stop-ProcessTree -ProcessId $_.ProcessId }
    Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
}

function Test-HttpReachable {
    # Returns @{ Reachable = <bool>; Error = <string> }.
    #
    # Deliberately not Invoke-WebRequest. Its -TimeoutSec maps to
    # HttpWebRequest.Timeout, which bounds the connect and the response headers but
    # NOT the body read - and Invoke-WebRequest always downloads and parses the whole
    # body before returning. A server that sends "200 OK" and then holds the
    # connection open hangs the call with no timeout to rescue it, which looks like
    # the script freezing *after* the BackEnd has already logged the 200.
    # GetResponse() returns as soon as the headers arrive; closing the response
    # without touching the body removes that whole class of hang.
    param(
        [string]$Url,
        [int]$TimeoutMs = 2000
    )
    $request = [System.Net.HttpWebRequest]::CreateHttp($Url)
    $request.Method = "GET"
    $request.Timeout = $TimeoutMs
    $request.ReadWriteTimeout = $TimeoutMs
    $request.AllowAutoRedirect = $false
    $request.KeepAlive = $false
    $request.Proxy = $null
    try {
        $response = $request.GetResponse()
        $response.Close()
        return @{ Reachable = $true; Error = $null }
    } catch [System.Net.WebException] {
        # Any HTTP response - including the 4xx/5xx that throw here - means the
        # server answered, so it is reachable. Only a transport-level failure
        # (timed out, connection refused) means not-up-yet.
        if ($_.Exception.Response) {
            $_.Exception.Response.Close()
            return @{ Reachable = $true; Error = $null }
        }
        return @{ Reachable = $false; Error = $_.Exception.Message }
    } catch {
        return @{ Reachable = $false; Error = $_.Exception.Message }
    }
}

function Get-MissingKeyFiles {
    # Returns one entry per required key file that is absent, empty, or plainly not the
    # file it claims to be - all of them, so a fresh clone gets a single message listing
    # everything it needs instead of one failure per re-run.
    #
    # Both services default their keys directory to the literal string '../keys', which
    # they resolve against the process CWD, not against the module file. That only lands
    # on the repo-root keys/ because BackEnd runs with CWD=BackEnd\ and Web with
    # CWD=Web\ (see -WorkingDirectory and Push-Location below), so a *relative*
    # LOCOL_*_LOCATION override has to be joined against the consuming service's
    # directory to match what the app will actually open.
    param(
        [string]$RepoRoot,
        [string]$BackendDir,
        [string]$WebDir
    )

    function Resolve-KeysDir {
        param([string]$EnvValue, [string]$ServiceDir)
        if (-not $EnvValue) { return Join-Path $RepoRoot "keys" }
        if ([System.IO.Path]::IsPathRooted($EnvValue)) { return $EnvValue }
        return Join-Path $ServiceDir $EnvValue
    }

    $jwtDirWeb = Resolve-KeysDir -EnvValue $env:LOCOL_JWT_KEYS_LOCATION -ServiceDir $WebDir
    $jwtDirBackend = Resolve-KeysDir -EnvValue $env:LOCOL_JWT_KEYS_LOCATION -ServiceDir $BackendDir
    $dbKeyDir = Resolve-KeysDir -EnvValue $env:LOCOL_DB_ENCRYPTION_KEY_LOCATION -ServiceDir $BackendDir

    $required = @(
        @{ File = "private_key.pem";     Dir = $jwtDirWeb;     Pem = $true;
           Purpose = "Web signs session tokens with it";
           Script = "generate-jwt-keys" }
        @{ File = "public_key.pem";      Dir = $jwtDirBackend; Pem = $true;
           Purpose = "BackEnd verifies every authenticated request with it";
           Script = "generate-jwt-keys" }
        @{ File = "enc_public_key.pem";  Dir = $jwtDirWeb;     Pem = $true;
           Purpose = "Web encrypts session tokens to BackEnd with it";
           Script = "generate-jwt-keys" }
        @{ File = "enc_private_key.pem"; Dir = $jwtDirBackend; Pem = $true;
           Purpose = "BackEnd decrypts every session token with it";
           Script = "generate-jwt-keys" }
        @{ File = "db_encryption.key"; Dir = $dbKeyDir;      Pem = $false;
           Purpose = "BackEnd encrypts stored LLM API keys with it";
           Script = "generate-db-encryption-key" }
    )

    $missing = @()
    foreach ($key in $required) {
        $path = Join-Path $key.Dir $key.File
        $item = Get-Item -LiteralPath $path -ErrorAction SilentlyContinue
        $reason = $null
        if (-not $item) {
            $reason = "not found"
        } elseif ($item.Length -eq 0) {
            $reason = "present but empty"
        } elseif ($key.Pem) {
            # A truncated or placeholder .pem otherwise fails much later, as an opaque
            # PEM parse error from cryptography rather than as a missing-setup problem.
            $firstLine = Get-Content -LiteralPath $path -TotalCount 1 -ErrorAction SilentlyContinue
            if ($firstLine -notlike "-----BEGIN*") {
                $reason = "present but not a PEM file (no -----BEGIN header)"
            }
        }
        if ($reason) {
            $missing += [pscustomobject]@{
                Path    = $path
                Reason  = $reason
                Purpose = $key.Purpose
                Script  = $key.Script
            }
        }
    }
    return $missing
}

function Test-MasterDatabase {
    # Returns a reason string if BackEnd/db/persistent_data.sqlite is unusable, else $null.
    #
    # This is the shared accounts database holding the `users` table. Nothing in the app
    # creates the db/ directory: db_manager.py's only os.makedirs covers db/users, so
    # sqlite3.connect("./db/persistent_data.sqlite") fails outright with "unable to open
    # database file" when db/ is absent - and register_user()/login_user() wrap that in a
    # broad `except`, so the browser is told "Registration failed" with no hint that the
    # setup step was never run. Checking here names the real cause.
    param([string]$BackendDir)

    $dbPath = Join-Path $BackendDir "db\persistent_data.sqlite"
    $item = Get-Item -LiteralPath $dbPath -ErrorAction SilentlyContinue
    if (-not $item) {
        return "not found at $dbPath"
    }
    if ($item.Length -eq 0) {
        return "$dbPath is empty"
    }
    # A truncated or placeholder file otherwise fails later as "file is not a database".
    # Every real SQLite file opens with the 16-byte magic string below.
    $header = [byte[]]::new(16)
    $stream = [System.IO.File]::OpenRead($dbPath)
    try {
        $read = $stream.Read($header, 0, 16)
    } finally {
        $stream.Dispose()
    }
    if ($read -lt 16 -or [Text.Encoding]::ASCII.GetString($header, 0, 15) -ne "SQLite format 3") {
        return "$dbPath is not a SQLite database file"
    }
    return $null
}

# keys/ is gitignored, so a fresh clone has none of it - and every one of these files
# fails late rather than at startup, because each is read lazily on first use.
# jwt_auth.py at least no longer fails in *disguise*: a missing public_key.pem or
# enc_private_key.pem now raises KeyConfigurationError and returns a 500 with
# "Server authentication key is not configured" plus an [ERROR] line naming the path,
# where it used to be swallowed into "401 Token verification failed" and look exactly
# like a bad token. On the Web side a missing private_key.pem or enc_public_key.pem
# throws inside Streamlit's login handler; a missing db_encryption.key 500s on any
# LLM-config read. Check first anyway: this costs milliseconds, the two dependency
# syncs below do not.
$missingKeys = @(Get-MissingKeyFiles -RepoRoot $repoRoot -BackendDir $backendDir -WebDir $webDir)
if ($missingKeys) {
    $detail = $missingKeys | ForEach-Object { "  - $($_.Path) ($($_.Reason)) - $($_.Purpose)" }
    # setup-local.ps1 is safe to suggest unconditionally: it skips every step that is
    # already done and never passes -Force to anything. The individual generators are
    # listed too, but only the ones actually needed - both refuse to overwrite an
    # existing file and exit non-zero, so naming the whole set when just one key is
    # missing hands you a command guaranteed to fail. And never suggest -Force here:
    # on db_encryption.key it makes every stored API key permanently undecryptable,
    # silently (see docs/deploy-local.md, "this key is not disposable").
    $fixes = $missingKeys | Select-Object -ExpandProperty Script -Unique |
        ForEach-Object { "  ./scripts/$($_).ps1" }
    throw (@(
        "Required key file(s) missing - the one-time setup has not been run:"
        $detail
        ""
        "Run the installer from the repo root. It creates whatever is missing and"
        "leaves anything already set up untouched:"
        "  ./scripts/setup-local.ps1"
        ""
        "Or generate just these keys:"
        $fixes
        ""
        "If PowerShell blocks a script as unsigned, run it as:"
        "  powershell -ExecutionPolicy Bypass -File ./scripts/<script-name>.ps1"
        ""
        "See docs/deploy-local.md section 4 (One-time setup)."
    ) -join [Environment]::NewLine)
}

# Same rationale as the key files above: the other half of the one-time setup, missing in
# exactly the same way on a fresh clone (db/ is gitignored), and failing just as late.
$dbProblem = Test-MasterDatabase -BackendDir $backendDir
if ($dbProblem) {
    throw (@(
        "The shared users database is missing or unusable - the one-time setup has not been run:"
        "  - $dbProblem"
        ""
        "Run the installer from the repo root. It creates whatever is missing and leaves"
        "anything already set up untouched:"
        "  ./scripts/setup-local.ps1"
        ""
        "Or create just the database:"
        "  uv run --project BackEnd python scripts/create_user_database.py"
        ""
        "It only creates the shared users table; per-user databases under BackEnd/db/users/"
        "are created automatically when each account registers. The script refuses to touch"
        "an existing file unless you pass --force."
        ""
        "See docs/deploy-local.md section 4 (One-time setup)."
    ) -join [Environment]::NewLine)
}

Write-Host "Syncing BackEnd dependencies..." -ForegroundColor Cyan
if (-not (Sync-UvProject -Dir $backendDir)) {
    throw "uv sync kept failing in $backendDir - read the error above, it is not a transient lock."
}
Assert-VenvEntryPoint -Dir $backendDir -Exe "uvicorn.exe"

# An orphaned BackEnd from an earlier run keeps the port bound. The uvicorn started
# below would then die on bind while the readiness probe still gets its 200 - from the
# *stale* process - so the script would report "BackEnd is up" and Web would spend the
# session talking to the previous run's code. Refuse to start in that state instead.
$stale = @(Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
if ($stale) {
    $described = ($stale | ForEach-Object {
        "$((Get-Process -Id $_ -ErrorAction SilentlyContinue).ProcessName) (PID $_)"
    }) -join ", "
    throw "Port $BackendPort is already in use by $described - most likely an orphaned BackEnd from a previous run. Stop it with 'taskkill /PID $($stale[0]) /T /F' and re-run, or pass -BackendPort <other>."
}

Write-Host "Starting BackEnd (FastAPI) on http://localhost:$BackendPort ..." -ForegroundColor Cyan
# BackEnd/src/main.py's own `uvicorn.run(..., reload=True)` watches the whole
# BackEnd/ dir, including .venv - thousands of files the app never imports from,
# where a single `uv sync` touching a package restarts the server mid-request.
# (It was worse when this repo lived in Dropbox, whose syncing kept the watcher in
# a permanent reload storm, but scoping it is worth doing regardless.) Launch via
# the uvicorn CLI instead so the watcher only covers src/ - --app-dir src makes
# sibling imports resolve the same way they do when running src/main.py directly.
$backend = Start-Process -FilePath "uv" -ArgumentList "run", "--no-sync", "uvicorn", "main:app", `
    "--app-dir", "src", "--host", "0.0.0.0", "--port", "$BackendPort", "--reload", "--reload-dir", "src" `
    -WorkingDirectory $backendDir -PassThru

try {
    Write-Host "Waiting for BackEnd to become reachable..." -ForegroundColor Cyan
    # Probe 127.0.0.1, never "localhost" - this is deliberate, don't "tidy" it back.
    # uvicorn above binds --host 0.0.0.0, i.e. IPv4 only, so nothing ever listens on
    # ::1 - and "localhost" resolves to ::1 first on Windows. Where closed loopback
    # ports are dropped rather than refused (no RST), the ::1 attempt eats the whole
    # -TimeoutSec budget before .NET can fall back to IPv4, so a "localhost" probe
    # times out forever even while the BackEnd is up and serving.
    $probeUrl = "http://127.0.0.1:$BackendPort/docs"
    $timeoutSeconds = 20
    $ready = $false
    $lastError = $null
    $exitedEarly = $false
    $timer = [Diagnostics.Stopwatch]::StartNew()
    while ($timer.Elapsed.TotalSeconds -lt $timeoutSeconds) {
        if ($backend.HasExited) {
            $exitedEarly = $true
            break
        }
        $probe = Test-HttpReachable -Url $probeUrl -TimeoutMs 2000
        if ($probe.Reachable) {
            $ready = $true
            break
        }
        $lastError = $probe.Error
        if ($timer.Elapsed.TotalSeconds -lt $timeoutSeconds) {
            Start-Sleep -Seconds 1
        }
    }
    $timer.Stop()
    $elapsed = [int][Math]::Round($timer.Elapsed.TotalSeconds)
    if ($ready) {
        Write-Host "BackEnd is up (after ${elapsed}s)." -ForegroundColor Green
    } elseif ($exitedEarly) {
        Write-Warning "BackEnd process exited after ${elapsed}s (exit code $($backend.ExitCode)) - check its window for errors. Continuing anyway."
    } else {
        Write-Warning "BackEnd did not respond within ${timeoutSeconds}s - continuing anyway, check its window for errors. Last probe of ${probeUrl}: $lastError"
    }

    Write-Host "Syncing Web dependencies..." -ForegroundColor Cyan
    if (-not (Sync-UvProject -Dir $webDir)) {
        throw "uv sync kept failing in $webDir - read the error above, it is not a transient lock."
    }
    Assert-VenvEntryPoint -Dir $webDir -Exe "streamlit.exe"

    Write-Host "Starting Web (Streamlit) on http://localhost:$WebPort ..." -ForegroundColor Cyan
    $streamlitLogLevel = if ($DebugLogging) { "debug" } else { "info" }
    Push-Location $webDir
    try {
        uv run --no-sync streamlit run src/main.py "--server.port=$WebPort" "--logger.level=$streamlitLogLevel"
        $webExit = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    # Streamlit in the foreground means its own failures are the last thing on screen,
    # but a bare exit code scrolls past unexplained - and Ctrl+C lands here too, which
    # is not a failure. Name both readings rather than leaving the code to interpret.
    if ($webExit -ne 0) {
        Write-Warning "Streamlit exited with code $webExit. That is expected if you stopped it with Ctrl+C; otherwise the cause is in its output above."
    }
}
finally {
    if ($backend -and -not $backend.HasExited) {
        Write-Host "Stopping BackEnd (PID $($backend.Id))..." -ForegroundColor Cyan
        Stop-ProcessTree -ProcessId $backend.Id
    }
    # `uv` often exits once it has handed off to uvicorn, so $backend can already be
    # gone while its orphaned descendants still serve the BackEnd port. The pre-flight
    # check above guarantees the port was free before we started, so anything listening
    # on it now is ours to stop.
    foreach ($listenerPid in @(Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique)) {
        Write-Host "Stopping leftover BackEnd listener (PID $listenerPid)..." -ForegroundColor Cyan
        Stop-ProcessTree -ProcessId $listenerPid
    }
}
