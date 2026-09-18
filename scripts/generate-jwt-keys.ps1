<#
.SYNOPSIS
    Generate the two key pairs the session token needs.

.DESCRIPTION
    The token is a nested JWT - an RS256-signed JWS wrapped in an
    ECDH-ES+A256KW JWE - so it takes one key pair per layer, written into
    -OutDir:

      private_key.pem      RSA, PKCS#1, unencrypted. Web SIGNS with this.
      public_key.pem       RSA, SubjectPublicKeyInfo. BackEnd VERIFIES with this.
      enc_private_key.pem  EC P-256, SEC1. BackEnd DECRYPTS with this.
      enc_public_key.pem   EC P-256, SubjectPublicKeyInfo. Web ENCRYPTS with this.

    Note the halves are held crosswise: each service has one private key and
    one public key, so neither can both mint and read a token on its own. See
    BackEnd/src/jwt_auth.py and Web/src/jwt_utils.py; both find this directory
    via the LOCOL_JWT_KEYS_LOCATION env var.

    Uses only .NET cryptography, so it runs on stock Windows PowerShell 5.1
    with no OpenSSL or Python toolchain installed.

    Regenerating these pairs is cheap: it only invalidates existing sessions,
    so users simply log in again.

.PARAMETER OutDir
    Directory to write the key pairs into. Defaults to the repo-root keys/
    directory, resolved from this script's own location.

.PARAMETER KeySize
    RSA key size in bits (default: 2048). Does not affect the EC pair, whose
    curve is fixed at P-256 by the token format.

.PARAMETER Force
    Overwrite existing key pairs in -OutDir.

.EXAMPLE
    ./scripts/generate-jwt-keys.ps1

.EXAMPLE
    ./scripts/generate-jwt-keys.ps1 -KeySize 4096 -Force
#>

[CmdletBinding()]
param(
    [string]$OutDir,
    [ValidateRange(2048, 16384)]
    [int]$KeySize = 2048,
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Split-Path -Parent $scriptDir

if (-not $OutDir) {
    $OutDir = Join-Path $repoRoot "keys"
}

# --- Minimal DER encoder -----------------------------------------------------
# .NET's PEM helpers (ExportRSAPrivateKeyPem) are .NET 5+ only, so we encode the
# two structures by hand to keep a single code path across PowerShell 5.1 and 7.

function ConvertTo-DerLength {
    param([int]$Length)

    if ($Length -lt 0x80) {
        return [byte[]]@([byte]$Length)
    }

    $lengthBytes = New-Object System.Collections.Generic.List[byte]
    $remaining = $Length
    while ($remaining -gt 0) {
        $lengthBytes.Insert(0, [byte]($remaining -band 0xFF))
        $remaining = $remaining -shr 8
    }
    return [byte[]](@([byte](0x80 -bor $lengthBytes.Count)) + $lengthBytes.ToArray())
}

function New-DerTlv {
    param([byte]$Tag, [byte[]]$Content)

    $length = [byte[]](ConvertTo-DerLength $Content.Length)
    return [byte[]](@($Tag) + $length + $Content)
}

function New-DerInteger {
    param([byte[]]$Value)

    # DER INTEGERs are big-endian, minimally encoded, and signed - strip leading
    # zero bytes, then re-add one if the top bit would make the value negative.
    $start = 0
    while ($start -lt ($Value.Length - 1) -and $Value[$start] -eq 0) {
        $start++
    }
    $trimmed = [byte[]]$Value[$start..($Value.Length - 1)]
    if ($trimmed[0] -band 0x80) {
        $trimmed = [byte[]](@([byte]0) + $trimmed)
    }
    return [byte[]](New-DerTlv 0x02 $trimmed)
}

function New-DerSequence {
    param([byte[]]$Content)
    return [byte[]](New-DerTlv 0x30 $Content)
}

function ConvertTo-Pkcs1PrivateKey {
    param([System.Security.Cryptography.RSAParameters]$Parameters)

    $content = [byte[]]@()
    $content += [byte[]](New-DerInteger ([byte[]]@(0)))          # version
    $content += [byte[]](New-DerInteger $Parameters.Modulus)     # n
    $content += [byte[]](New-DerInteger $Parameters.Exponent)    # e
    $content += [byte[]](New-DerInteger $Parameters.D)           # d
    $content += [byte[]](New-DerInteger $Parameters.P)           # p
    $content += [byte[]](New-DerInteger $Parameters.Q)           # q
    $content += [byte[]](New-DerInteger $Parameters.DP)          # d mod (p-1)
    $content += [byte[]](New-DerInteger $Parameters.DQ)          # d mod (q-1)
    $content += [byte[]](New-DerInteger $Parameters.InverseQ)    # q^-1 mod p
    return [byte[]](New-DerSequence $content)
}

function ConvertTo-SubjectPublicKeyInfo {
    param([System.Security.Cryptography.RSAParameters]$Parameters)

    # AlgorithmIdentifier { OID 1.2.840.113549.1.1.1 (rsaEncryption), NULL }
    $rsaOid = [byte[]]@(0x06, 0x09, 0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01, 0x01)
    $null_ = [byte[]]@(0x05, 0x00)
    $algorithmId = [byte[]](New-DerSequence ([byte[]]($rsaOid + $null_)))

    $rsaPublicKey = [byte[]](New-DerSequence ([byte[]](
        [byte[]](New-DerInteger $Parameters.Modulus) +
        [byte[]](New-DerInteger $Parameters.Exponent)
    )))

    # BIT STRING content is prefixed with the count of unused trailing bits (0).
    $bitString = [byte[]](New-DerTlv 0x03 ([byte[]](@([byte]0) + $rsaPublicKey)))
    return [byte[]](New-DerSequence ([byte[]]($algorithmId + $bitString)))
}

function New-DerOctetString {
    param([byte[]]$Content)
    return [byte[]](New-DerTlv 0x04 $Content)
}

function New-DerObjectIdentifier {
    # Pre-encoded OID contents; only two are needed, so encoding arcs is overkill.
    param([string]$Oid)

    switch ($Oid) {
        # id-ecPublicKey
        "1.2.840.10045.2.1"   { return [byte[]](New-DerTlv 0x06 ([byte[]]@(0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x02, 0x01))) }
        # prime256v1 / P-256 / secp256r1
        "1.2.840.10045.3.1.7" { return [byte[]](New-DerTlv 0x06 ([byte[]]@(0x2A, 0x86, 0x48, 0xCE, 0x3D, 0x03, 0x01, 0x07))) }
        default { throw "Unsupported OID: $Oid" }
    }
}

function ConvertTo-FixedWidth {
    param([byte[]]$Value, [int]$Width)

    # EC scalars and coordinates are fixed-width in SEC1 (32 bytes for P-256).
    # .NET usually returns exactly that, but a leading zero byte can be trimmed.
    if ($Value.Length -eq $Width) { return $Value }
    if ($Value.Length -gt $Width) { return [byte[]]$Value[($Value.Length - $Width)..($Value.Length - 1)] }
    return [byte[]](@([byte]0) * ($Width - $Value.Length) + $Value)
}

function ConvertTo-Sec1EcPrivateKey {
    param([System.Security.Cryptography.ECParameters]$Parameters)

    # RFC 5915 ECPrivateKey ::= SEQUENCE {
    #   version INTEGER (1), privateKey OCTET STRING,
    #   parameters [0] NamedCurve OPTIONAL, publicKey [1] BIT STRING OPTIONAL }
    $d = [byte[]](ConvertTo-FixedWidth $Parameters.D 32)
    $x = [byte[]](ConvertTo-FixedWidth $Parameters.Q.X 32)
    $y = [byte[]](ConvertTo-FixedWidth $Parameters.Q.Y 32)

    $curveOid = [byte[]](New-DerObjectIdentifier "1.2.840.10045.3.1.7")
    # 0x04 marks an uncompressed point; the leading 0x00 is the BIT STRING's
    # count of unused trailing bits.
    $point = [byte[]](@([byte]0x04) + $x + $y)
    $publicBitString = [byte[]](New-DerTlv 0x03 ([byte[]](@([byte]0) + $point)))

    $content = [byte[]]@()
    $content += [byte[]](New-DerInteger ([byte[]]@(1)))
    $content += [byte[]](New-DerOctetString $d)
    $content += [byte[]](New-DerTlv 0xA0 $curveOid)          # [0] constructed
    $content += [byte[]](New-DerTlv 0xA1 $publicBitString)   # [1] constructed
    return [byte[]](New-DerSequence $content)
}

function ConvertTo-EcSubjectPublicKeyInfo {
    param([System.Security.Cryptography.ECParameters]$Parameters)

    $algorithmId = [byte[]](New-DerSequence ([byte[]](
        [byte[]](New-DerObjectIdentifier "1.2.840.10045.2.1") +
        [byte[]](New-DerObjectIdentifier "1.2.840.10045.3.1.7")
    )))

    $x = [byte[]](ConvertTo-FixedWidth $Parameters.Q.X 32)
    $y = [byte[]](ConvertTo-FixedWidth $Parameters.Q.Y 32)
    $point = [byte[]](@([byte]0x04) + $x + $y)
    $bitString = [byte[]](New-DerTlv 0x03 ([byte[]](@([byte]0) + $point)))

    return [byte[]](New-DerSequence ([byte[]]($algorithmId + $bitString)))
}

function Format-Pem {
    param([string]$Label, [byte[]]$Der)

    $base64 = [Convert]::ToBase64String($Der)
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("-----BEGIN $Label-----")
    for ($i = 0; $i -lt $base64.Length; $i += 64) {
        $take = [Math]::Min(64, $base64.Length - $i)
        $lines.Add($base64.Substring($i, $take))
    }
    $lines.Add("-----END $Label-----")
    # LF endings, no BOM - cryptography's PEM parser rejects a BOM.
    return (($lines -join "`n") + "`n")
}

function Write-TextFileUtf8NoBom {
    param([string]$Path, [string]$Text)
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Text, $encoding)
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

# --- Main --------------------------------------------------------------------

if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
}
$OutDir = (Resolve-Path -LiteralPath $OutDir).Path

$privateKeyPath = Join-Path $OutDir "private_key.pem"
$publicKeyPath = Join-Path $OutDir "public_key.pem"
$encPrivateKeyPath = Join-Path $OutDir "enc_private_key.pem"
$encPublicKeyPath = Join-Path $OutDir "enc_public_key.pem"

if (-not $Force) {
    foreach ($existing in @($privateKeyPath, $publicKeyPath, $encPrivateKeyPath, $encPublicKeyPath)) {
        if (Test-Path -LiteralPath $existing) {
            throw "Refusing to overwrite existing key(s) in $OutDir. Pass -Force to replace them."
        }
    }
}

Write-Host "Generating a $KeySize-bit RSA key pair..." -ForegroundColor Cyan

$rsa = New-Object System.Security.Cryptography.RSACryptoServiceProvider($KeySize)
try {
    $rsa.PersistKeyInCsp = $false
    $parameters = $rsa.ExportParameters($true)

    $privatePem = Format-Pem "RSA PRIVATE KEY" ([byte[]](ConvertTo-Pkcs1PrivateKey $parameters))
    $publicPem = Format-Pem "PUBLIC KEY" ([byte[]](ConvertTo-SubjectPublicKeyInfo $parameters))
} finally {
    $rsa.Dispose()
}

Write-TextFileUtf8NoBom -Path $privateKeyPath -Text $privatePem
Protect-KeyFile -Path $privateKeyPath

Write-TextFileUtf8NoBom -Path $publicKeyPath -Text $publicPem

Write-Host "Generating a P-256 EC key pair..." -ForegroundColor Cyan

# ECCurve/ECParameters need .NET Framework 4.7+, which ships with Windows 10 1703
# and later, so this stays inside the "stock PowerShell 5.1" promise above. -KeySize
# does not apply: P-256 is fixed by the ECDH-ES+A256KW choice in the token format.
# Created via ECDsa purely because it is the simplest generator for a P-256 pair -
# the SEC1/SPKI encodings below carry no algorithm usage, so BackEnd loads the
# result for ECDH key agreement exactly as OpenSSL's `ecparam -genkey` output.
if (-not ("System.Security.Cryptography.ECCurve" -as [type])) {
    throw "EC key generation needs .NET Framework 4.7 or later. Install a current .NET Framework, or generate the keys with scripts/generate-jwt-keys.sh (requires OpenSSL)."
}

# [ECCurve+NamedCurves], not [ECCurve]::NamedCurves.nistP256. On Windows
# PowerShell 5.1 the latter silently evaluates to a default-valued ECCurve struct
# with an empty OID - no error - and Create() then returns $null, which surfaces
# several lines later as "You cannot call a method on a null-valued expression".
# The nested-type syntax resolves the static property properly on 5.1 and 7.
$curve = [System.Security.Cryptography.ECCurve+NamedCurves]::nistP256
if (-not $curve.Oid.Value) {
    throw "Could not resolve the P-256 named curve from .NET. Generate the keys with scripts/generate-jwt-keys.sh (requires OpenSSL) instead."
}

$ecdsa = [System.Security.Cryptography.ECDsa]::Create($curve)
if (-not $ecdsa) {
    throw "Failed to create a P-256 key. Generate the keys with scripts/generate-jwt-keys.sh (requires OpenSSL) instead."
}
try {
    $ecParameters = $ecdsa.ExportParameters($true)

    $encPrivatePem = Format-Pem "EC PRIVATE KEY" ([byte[]](ConvertTo-Sec1EcPrivateKey $ecParameters))
    $encPublicPem = Format-Pem "PUBLIC KEY" ([byte[]](ConvertTo-EcSubjectPublicKeyInfo $ecParameters))
} finally {
    $ecdsa.Dispose()
}

Write-TextFileUtf8NoBom -Path $encPrivateKeyPath -Text $encPrivatePem
Protect-KeyFile -Path $encPrivateKeyPath

Write-TextFileUtf8NoBom -Path $encPublicKeyPath -Text $encPublicPem

Write-Host "Wrote $privateKeyPath (RSA private - Web signs)" -ForegroundColor Green
Write-Host "Wrote $publicKeyPath (RSA public - BackEnd verifies)" -ForegroundColor Green
Write-Host "Wrote $encPrivateKeyPath (EC private - BackEnd decrypts)" -ForegroundColor Green
Write-Host "Wrote $encPublicKeyPath (EC public - Web encrypts)" -ForegroundColor Green
