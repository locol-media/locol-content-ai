<#
.SYNOPSIS
    Extract a Reddit user's posts and comments to a plain-text writing sample.

.DESCRIPTION
    Pulls the full text of a public Reddit account's submissions and comments and
    writes them to a single UTF-8 text file, newest first.

    CREDENTIALS ARE EFFECTIVELY REQUIRED. Reddit now gates its public JSON endpoints
    behind a logged-in session: as of August 2026 www.reddit.com/user/<name>/*.json
    returns 403 to every logged-out request, and old.reddit.com redirects to
    /login/?reason=lor2. That is not the old cloud-IP reputation block - it was
    reproduced from an ordinary residential connection - so running this script
    locally does not by itself get you past it.

    What still works is OAuth. Register a "script" app at
    https://www.reddit.com/prefs/apps, then set REDDIT_CLIENT_ID and
    REDDIT_CLIENT_SECRET (or pass -ClientId/-ClientSecret) and the script
    authenticates against oauth.reddit.com.

    The anonymous path is left in because it costs nothing to try and Reddit's
    posture keeps shifting, but expect it to fail with a 403.

    Context: BackEnd/src/find_your_voice.py analyses Google/Serper search snippets
    rather than reading Reddit. This script exists to get whole posts instead.

    Only public data is read, through Reddit's documented endpoints, rate-limited,
    and with an identifying User-Agent as their API rules require.

    Uses only Windows PowerShell 5.1 features, so it runs on a stock Windows box
    with no PowerShell 7 or Python toolchain installed.

.PARAMETER Username
    Reddit username to fetch, with or without a leading "u/".

.PARAMETER OutFile
    Path of the text file to write. Defaults to
    <repoRoot>/temp/reddit-<username>-<timestamp>.txt. The temp/ directory is
    gitignored, so harvested personal content will not land in a commit by accident.

.PARAMETER MaxItems
    Maximum number of items to fetch per content type (default: 500). Reddit's user
    listings stop at roughly 1000 items regardless of what you ask for.

.PARAMETER Since
    Only include items created on or after this date.

.PARAMETER Subreddit
    Only include items from these subreddits (case-insensitive, no r/ prefix needed).

.PARAMETER MinLength
    Drop items whose body is shorter than this many characters (default: 80). Filters
    out "lol"/"this" comments that add noise but no stylistic signal. Use 0 to keep
    everything.

.PARAMETER IncludePosts
    Fetch submissions. If neither -IncludePosts nor -IncludeComments is given, both
    are fetched.

.PARAMETER IncludeComments
    Fetch comments. If neither -IncludePosts nor -IncludeComments is given, both
    are fetched.

.PARAMETER ClientId
    Reddit app client ID. Defaults to $env:REDDIT_CLIENT_ID. See the NOTES section
    for how to register an app and where on the page the ID actually appears - it is
    not the field you would expect.

.PARAMETER ClientSecret
    Reddit app client secret. Defaults to $env:REDDIT_CLIENT_SECRET. OAuth is used
    only when BOTH the ID and the secret are present; supplying just one silently
    falls back to the anonymous path, which Reddit now refuses.

.PARAMETER UserAgent
    User-Agent header to send. Reddit throttles generic agents aggressively, so the
    default identifies this script and the account being read.

.PARAMETER Force
    Overwrite -OutFile if it already exists.

.EXAMPLE
    # Credentials for this session only, then fetch.
    $env:REDDIT_CLIENT_ID = "Xy7kQ2mBn4pLwR8vTz9aQg"
    $env:REDDIT_CLIENT_SECRET = "s3cr3t-value-from-the-app-page"
    ./scripts/fetch-reddit-user.ps1 -Username spez -MaxItems 25

.EXAMPLE
    # Persist the credentials for your Windows user, so every future session has them.
    # Takes effect in NEW sessions - the current window keeps its old values.
    [Environment]::SetEnvironmentVariable("REDDIT_CLIENT_ID", "Xy7kQ2mBn4pLwR8vTz9aQg", "User")
    [Environment]::SetEnvironmentVariable("REDDIT_CLIENT_SECRET", "s3cr3t-value", "User")

.EXAMPLE
    # Pass them explicitly instead of using environment variables.
    ./scripts/fetch-reddit-user.ps1 -Username spez -ClientId "Xy7k..." -ClientSecret "s3cr3t..."

.EXAMPLE
    ./scripts/fetch-reddit-user.ps1 -Username spez -Subreddit announcements -Since (Get-Date).AddYears(-2)

.NOTES
    ----------------------------------------------------------------------------
    PROVIDING CREDENTIALS
    ----------------------------------------------------------------------------

    1. Register a Reddit app
    ------------------------
    a. Sign in to Reddit, then open https://www.reddit.com/prefs/apps
    b. Click "create another app..." at the bottom (or "are you a developer?
       create an app..." if you have never made one).
    c. Fill in the form:
         name          anything, e.g. locol-voice-fetch
         type          select "script"   <- important, not "web app"
         description   optional
         about url     optional
         redirect uri  http://localhost:8080
                       Required by the form even though this script never uses it;
                       the client-credentials flow has no browser redirect step.
    d. Click "create app".

    2. Find the two values
    ----------------------
    On the resulting app card:

      * CLIENT ID is the short unlabelled string shown directly beneath the app
        name, just under the words "personal use script". It is roughly 22
        characters. It is NOT labelled "client id", which is where most people
        get stuck.

      * CLIENT SECRET is the value in the field explicitly labelled "secret".

    3. Give them to the script - pick one
    -------------------------------------
    Current session only (simplest; gone when you close the window):

        $env:REDDIT_CLIENT_ID = "your-client-id"
        $env:REDDIT_CLIENT_SECRET = "your-secret"

    Persisted for your Windows user (survives reboots; applies to NEW sessions):

        [Environment]::SetEnvironmentVariable("REDDIT_CLIENT_ID", "your-client-id", "User")
        [Environment]::SetEnvironmentVariable("REDDIT_CLIENT_SECRET", "your-secret", "User")

    Directly as parameters:

        -ClientId "your-client-id" -ClientSecret "your-secret"

        Be aware this writes the secret into your PowerShell history file
        (%APPDATA%\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt),
        where it persists in plain text. The environment-variable routes avoid that.

    4. Confirm it worked
    --------------------
    A successful run prints "Authenticating with Reddit (client Xy7k...)" before
    fetching. If you instead see the warning about no credentials being found, the
    variables are not reaching the script - check for typos in the variable names,
    and remember that SetEnvironmentVariable does not affect the session you ran it in.

    Never commit these values. Keep them in your environment, not in a file in the
    repository.

    ----------------------------------------------------------------------------
    CAVEATS
    ----------------------------------------------------------------------------

    Registration may no longer be self-service. Reddit's Responsible Builder Policy
    (updated June 2026) has been reported to require a request and manual approval
    before a new OAuth client is issued, though other sources say the prefs/apps
    form still works immediately. Open the page and see which applies to you.

    Reddit's free tier is 100 queries per minute and is for NON-COMMERCIAL use.
    Commercial use requires prior written approval from Reddit and is charged per
    call. One user's full history is only about ten requests, so the rate limit is
    not the constraint - the licensing classification is. Review Reddit's Data API
    Terms before using this in a commercial product.

.LINK
    https://www.reddit.com/prefs/apps

.LINK
    https://www.redditinc.com/policies/data-api-terms
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Username,

    [string]$OutFile,

    [ValidateRange(1, 1000)]
    [int]$MaxItems = 500,

    [datetime]$Since,

    [string[]]$Subreddit,

    [ValidateRange(0, 100000)]
    [int]$MinLength = 80,

    [switch]$IncludePosts,
    [switch]$IncludeComments,

    [string]$ClientId = $env:REDDIT_CLIENT_ID,
    [string]$ClientSecret = $env:REDDIT_CLIENT_SECRET,

    [string]$UserAgent,

    [switch]$Force
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

# PowerShell 5.1 still negotiates TLS 1.0 by default; Reddit refuses it.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

# --- Helpers -----------------------------------------------------------------

function Get-StatusCode {
    param($ErrorRecord)

    # Only WebException carries a response we can read a status off; a DNS or TLS
    # failure has none, and 0 means "no HTTP answer at all".
    $response = $ErrorRecord.Exception.Response
    if ($response -and $response.StatusCode) {
        return [int]$response.StatusCode
    }
    return 0
}

function Get-RetryAfterSeconds {
    param($ErrorRecord, [int]$Fallback)

    try {
        $value = $ErrorRecord.Exception.Response.Headers["Retry-After"]
        if ($value) {
            $seconds = 0
            if ([int]::TryParse($value, [ref]$seconds) -and $seconds -gt 0) {
                return [Math]::Min($seconds, 120)
            }
        }
    } catch {
        # Header missing or unreadable - fall through to the caller's backoff.
    }
    return $Fallback
}

function Invoke-RedditRequest {
    <#
        One HTTP call with retry. Returns the parsed JSON body.
        Uses Invoke-WebRequest rather than Invoke-RestMethod because 5.1's
        Invoke-RestMethod exposes no response headers, and we want Retry-After.
    #>
    param(
        [string]$Uri,
        [hashtable]$Headers,
        [string]$Method = "Get",
        $Body
    )

    $maxAttempts = 4
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        try {
            $params = @{
                Uri             = $Uri
                Method          = $Method
                Headers         = $Headers
                UserAgent       = $script:EffectiveUserAgent
                UseBasicParsing = $true
                TimeoutSec      = 30
            }
            if ($null -ne $Body) {
                $params["Body"] = $Body
            }
            $response = Invoke-WebRequest @params
            return ($response.Content | ConvertFrom-Json)
        } catch {
            $status = Get-StatusCode $_

            if (($status -eq 429 -or $status -ge 500) -and $attempt -lt $maxAttempts) {
                $backoff = Get-RetryAfterSeconds $_ ([Math]::Pow(2, $attempt))
                Write-Warning "Reddit returned $status; retrying in $backoff s (attempt $attempt of $maxAttempts)."
                Start-Sleep -Seconds $backoff
                continue
            }

            switch ($status) {
                401 {
                    throw "Reddit rejected the credentials (401). Check REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET, and that the app is registered as a 'script' app."
                }
                403 {
                    throw "Reddit refused the request (403). Reddit now requires a logged-in session for these endpoints, so anonymous access fails regardless of which IP you run from. Register a 'script' app at https://www.reddit.com/prefs/apps and set REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET to use the authenticated API instead."
                }
                404 {
                    throw "No such user: u/$Username (404). The account may also be suspended or shadowbanned."
                }
                429 {
                    throw "Reddit is rate-limiting this client (429) and did not recover after $maxAttempts attempts. Wait a few minutes, or authenticate to get a higher limit."
                }
                0 {
                    throw "Could not reach Reddit: $($_.Exception.Message)"
                }
                default {
                    throw "Reddit request failed with HTTP ${status}: $($_.Exception.Message)"
                }
            }
        }
    }
}

function Get-RedditAccessToken {
    param([string]$ClientId, [string]$ClientSecret)

    $pair = "${ClientId}:${ClientSecret}"
    $basic = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes($pair))

    # Application-only ("client credentials") flow. It carries the read scope, which
    # is all that public user listings need - no account password involved.
    $result = Invoke-RedditRequest `
        -Uri "https://www.reddit.com/api/v1/access_token" `
        -Method "Post" `
        -Headers @{ Authorization = "Basic $basic" } `
        -Body @{ grant_type = "client_credentials" }

    if (-not $result.access_token) {
        throw "Reddit did not return an access token. Confirm the app at https://www.reddit.com/prefs/apps is a 'script' app and the secret is current."
    }
    return $result.access_token
}

function ConvertFrom-UnixTime {
    param([double]$Seconds)
    return [DateTimeOffset]::FromUnixTimeSeconds([long]$Seconds).UtcDateTime
}

function ConvertTo-RedditItem {
    <# Normalise a raw listing child into the shape the rest of the script uses. #>
    param($Child)

    $data = $Child.data
    $isPost = ($Child.kind -eq "t3")

    $kind = "COMMENT"
    $title = $null
    $body = $data.body
    if ($isPost) {
        $kind = "POST"
        $title = $data.title
        $body = $data.selftext
    }

    return [pscustomobject]@{
        Kind       = $kind
        Subreddit  = $data.subreddit
        Title      = $title
        Body       = $body
        Score      = $data.score
        CreatedUtc = ConvertFrom-UnixTime $data.created_utc
        Permalink  = "https://www.reddit.com$($data.permalink)"
    }
}

function Get-RedditListing {
    <# Page through /user/<name>/<kind>, newest first, up to -MaxItems. #>
    param(
        [string]$Username,
        [ValidateSet("submitted", "comments")]
        [string]$Kind,
        [int]$MaxItems
    )

    $items = New-Object System.Collections.Generic.List[object]
    $after = $null

    do {
        $pageSize = [Math]::Min(100, $MaxItems - $items.Count)
        # raw_json=1 matters: without it every &, < and > comes back HTML-escaped
        # and corrupts the text sample.
        $uri = "$script:ApiBase/user/$Username/$Kind" +
               "?limit=$pageSize&raw_json=1&sort=new"
        if ($after) {
            $uri += "&after=$after"
        }

        $response = Invoke-RedditRequest -Uri $uri -Headers $script:AuthHeaders
        $children = @($response.data.children)
        if ($children.Count -eq 0) {
            break
        }

        $reachedCutoff = $false
        foreach ($child in $children) {
            $item = ConvertTo-RedditItem $child
            if ($script:SinceUtc -and $item.CreatedUtc -lt $script:SinceUtc) {
                # Listing is newest-first, so everything past here is older too.
                $reachedCutoff = $true
                break
            }
            $items.Add($item)
        }

        Write-Host "  fetched $($items.Count) $Kind..." -ForegroundColor DarkGray

        $after = $response.data.after
        if ($reachedCutoff) {
            break
        }

        if ($after -and $items.Count -lt $MaxItems) {
            Start-Sleep -Milliseconds $script:PageDelayMs
        }
    } while ($after -and $items.Count -lt $MaxItems)

    return $items.ToArray()
}

function Test-KeepItem {
    param($Item)

    $body = if ($Item.Body) { $Item.Body.Trim() } else { "" }

    # Deleted/removed bodies are placeholders, not the user's writing.
    if ($body -eq "[deleted]" -or $body -eq "[removed]") {
        return $false
    }

    if ($Subreddit -and ($Subreddit -notcontains $Item.Subreddit)) {
        return $false
    }

    if ($MinLength -gt 0 -and $body.Length -lt $MinLength) {
        # A link post has no selftext, but its title is still the user's own words.
        if (-not ($Item.Kind -eq "POST" -and $Item.Title)) {
            return $false
        }
    }

    return $true
}

function Write-TextFileUtf8NoBom {
    param([string]$Path, [string]$Text)

    # Out-File/Set-Content on 5.1 emit a BOM or the ANSI codepage, either of which
    # mangles the em-dashes and emoji that are exactly the stylistic cues we want.
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
}

# --- Main --------------------------------------------------------------------

$Username = $Username.Trim() -replace '^/?(u/|user/)', ''
if ($Username -notmatch '^[A-Za-z0-9_-]{3,20}$') {
    throw "'$Username' is not a valid Reddit username (3-20 characters: letters, digits, underscore, hyphen)."
}

if (-not $IncludePosts -and -not $IncludeComments) {
    $IncludePosts = $true
    $IncludeComments = $true
}

$script:SinceUtc = $null
if ($PSBoundParameters.ContainsKey("Since")) {
    $script:SinceUtc = $Since.ToUniversalTime()
}

if (-not $UserAgent) {
    $UserAgent = "windows:locol-ai-fetch-reddit-user:v1.0 (by /u/$Username)"
}
$script:EffectiveUserAgent = $UserAgent

if (-not $OutFile) {
    $tempDir = Join-Path $repoRoot "temp"
    $stamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $OutFile = Join-Path $tempDir "reddit-$Username-$stamp.txt"
}

$outDir = Split-Path -Parent $OutFile
if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
    New-Item -ItemType Directory -Path $outDir -Force | Out-Null
}

if (-not $Force -and (Test-Path -LiteralPath $OutFile)) {
    throw "Refusing to overwrite $OutFile. Pass -Force to replace it."
}

# Authenticate if we can, otherwise fall back to the public endpoints.
$script:AuthHeaders = @{}
$script:ApiBase = "https://www.reddit.com"
$script:PageDelayMs = 1200
$sourceLabel = "www.reddit.com (anonymous)"

if ($ClientId -and $ClientSecret) {
    $hint = if ($ClientId.Length -gt 4) { $ClientId.Substring(0, 4) } else { $ClientId }
    Write-Host "Authenticating with Reddit (client $hint...)" -ForegroundColor Cyan
    $token = Get-RedditAccessToken -ClientId $ClientId -ClientSecret $ClientSecret
    $script:AuthHeaders = @{ Authorization = "Bearer $token" }
    $script:ApiBase = "https://oauth.reddit.com"
    $script:PageDelayMs = 600
    $sourceLabel = "oauth.reddit.com (authenticated)"
} else {
    Write-Warning "No Reddit app credentials found. Falling back to the public endpoints, which Reddit now 403s for logged-out clients - this will probably fail. Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET to use the authenticated API."
}

Write-Host "Fetching content for u/$Username..." -ForegroundColor Cyan

$posts = @()
$comments = @()

if ($IncludePosts) {
    $posts = @(Get-RedditListing -Username $Username -Kind "submitted" -MaxItems $MaxItems)
}
if ($IncludeComments) {
    $comments = @(Get-RedditListing -Username $Username -Kind "comments" -MaxItems $MaxItems)
}

$kept = @($posts + $comments | Where-Object { Test-KeepItem $_ } | Sort-Object CreatedUtc -Descending)

if ($kept.Count -eq 0) {
    $filters = @("-MinLength $MinLength")
    if ($Subreddit) {
        $filters += "-Subreddit $($Subreddit -join ',')"
    }
    if ($script:SinceUtc) {
        $filters += "-Since $($script:SinceUtc.ToString('yyyy-MM-dd'))"
    }
    throw "Nothing to write: u/$Username returned no content matching the current filters ($($filters -join ', '))."
}

$keptPosts = @($kept | Where-Object { $_.Kind -eq "POST" }).Count
$keptComments = $kept.Count - $keptPosts

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("=== Reddit writing sample: u/$Username ===")
$lines.Add("Fetched:  $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))")
$lines.Add("Source:   $sourceLabel")
$lines.Add("Items:    $keptPosts posts, $keptComments comments")
$lines.Add("")

foreach ($item in $kept) {
    $date = $item.CreatedUtc.ToString("yyyy-MM-dd")
    $lines.Add("--- $($item.Kind) | r/$($item.Subreddit) | $date | score $($item.Score) ---")
    if ($item.Title) {
        $lines.Add($item.Title)
        $lines.Add("")
    }
    if ($item.Body -and $item.Body.Trim()) {
        $lines.Add($item.Body.Trim())
    }
    $lines.Add("")
}

$text = ($lines -join "`r`n")
Write-TextFileUtf8NoBom -Path $OutFile -Text $text

$resolved = (Resolve-Path -LiteralPath $OutFile).Path
Write-Host "Wrote $keptPosts posts and $keptComments comments ($($text.Length) characters)" -ForegroundColor Green
Write-Host "Wrote $resolved" -ForegroundColor Green
