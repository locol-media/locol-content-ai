import json
import os
from functools import lru_cache
from typing import Optional

from fastapi import HTTPException, Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwcrypto import jwk, jwt
from jwcrypto.common import JWException
from jwcrypto.jwt import JWTExpired

security = HTTPBearer()

# The session token is a nested JWT: an RS256-signed JWS wrapped in a JWE that only
# this service can decrypt. Web/src/jwt_utils.py mints it and must agree on all
# three algorithms below.
#
# Order matters on the way back: decrypt first, then verify the signature. The JWE
# layer only proves the token was encrypted to us, not who wrote it - ECDH-ES needs
# nothing but our public key, so decrypting successfully says nothing about the
# sender. The RS256 signature inside is the only thing that authenticates the claim,
# and it is checked against a public key this service cannot sign with.
#
# Both lists are passed explicitly on every call. jwcrypto's default_allowed_algs is
# permissive - it includes "dir" (no key agreement at all), bare "ECDH-ES", and the
# password-based PBES2-* family - so relying on the default would let an attacker
# nominate a weaker algorithm. One list covers both "alg" and "enc".
JWS_ALG = "RS256"
JWE_ALG = "ECDH-ES+A256KW"
JWE_ENC = "A256GCM"

_JWE_ALGS = [JWE_ALG, JWE_ENC]
_JWS_ALGS = [JWS_ALG]


class KeyConfigurationError(RuntimeError):
    """A key file is missing or unreadable - a deployment fault, not a bad token."""


def _keys_dir():
    return os.environ.get('LOCOL_JWT_KEYS_LOCATION', '../keys')


def _load_key(filename: str):
    """Read a PEM key file into a JWK, failing loudly if it is absent or malformed.

    Parsed here rather than at use time so that a deployment problem is reported as
    one, instead of surfacing later as an unreadable token."""
    path = os.path.join(_keys_dir(), filename)
    try:
        with open(path, 'rb') as key_file:
            data = key_file.read()
    except OSError as e:
        raise KeyConfigurationError(
            f"Could not read {path}. Set LOCOL_JWT_KEYS_LOCATION to the directory "
            f"holding the JWT keys and run scripts/generate-jwt-keys.sh to create them."
        ) from e

    try:
        return jwk.JWK.from_pem(data)
    except (ValueError, JWException) as e:
        raise KeyConfigurationError(f"{path} is not a valid PEM key: {e}") from e


@lru_cache(maxsize=1)
def load_public_key():
    """Load the RSA public key for JWT signature verification.

    Cached: this used to re-read and re-parse the PEM on every single token
    decode, and the rate limiter's user key adds a second decode per request to
    the endpoints it guards. The key is mounted at startup and does not change
    at runtime, so one read is enough."""
    return _load_key('public_key.pem')


@lru_cache(maxsize=1)
def load_enc_private_key():
    """Load this service's EC private key, used to decrypt the JWE wrapper.

    Note this is the reverse of the signing pair: BackEnd holds the *public*
    verification key and the *private* decryption key, Web holds the other half of
    each. Cached for the same reason as load_public_key."""
    return _load_key('enc_private_key.pem')


def decode_jwt_token(token: str) -> str:
    """Decrypt and verify a session token, returning the user ID"""
    try:
        # A bare 3-segment JWS is refused on format. Tokens minted before the JWE
        # layer are still signature-valid and would otherwise be accepted forever;
        # this is what makes the cutover a real cutover. expected_type="JWE" below
        # would reject them too, but only via a bare TypeError and without the
        # "log in again" wording that makes the failure legible.
        if token.count('.') != 4:
            raise HTTPException(
                status_code=401,
                detail="Invalid token: expected an encrypted token, please log in again",
            )

        # Loaded outside the catch-all below, so a missing or malformed key file
        # raises KeyConfigurationError and is reported as the 500 it is, rather than
        # being swallowed and blamed on the token.
        enc_key = load_enc_private_key()
        verify_key = load_public_key()

        try:
            outer = jwt.JWT(key=enc_key, jwt=token, expected_type="JWE", algs=_JWE_ALGS)
            inner = jwt.JWT(key=verify_key, jwt=outer.claims, algs=_JWS_ALGS)
            payload = json.loads(inner.claims)
        except JWTExpired:
            # Raised by jwcrypto's own claim check on the inner token, so expiry
            # keeps its distinct message rather than reading as a malformed token.
            raise HTTPException(status_code=401, detail="Token has expired")
        except (JWException, TypeError, ValueError) as e:
            # Every input here is attacker-controlled and every failure means the
            # same thing, so all of them are a 401. jwcrypto funnels most of it into
            # JWException (InvalidJWEData wraps a tampered ciphertext or auth tag),
            # but not all: expected_type mismatch raises a plain TypeError, and a
            # decrypted payload that is not a JWS at all surfaces as ValueError.
            # Those two are why this clause is not just `except JWException` - left
            # out, they escape as a 500 and a flipped byte looks like a server fault.
            raise HTTPException(status_code=401, detail="Invalid token") from e

        if not isinstance(payload, dict):
            raise HTTPException(status_code=401, detail="Invalid token")

        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token: missing user_id")

        return user_id

    except KeyConfigurationError as e:
        # Deliberately not a 401. This used to be swallowed by a bare `except
        # Exception` into "Token verification failed", so a missing key mount looked
        # exactly like a bad token and sent everyone hunting the wrong problem.
        print(f"[ERROR] JWT key configuration: {e}")
        raise HTTPException(status_code=500, detail="Server authentication key is not configured")


def get_current_user_from_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """FastAPI dependency to extract user ID from JWT token"""
    token = credentials.credentials
    user_id = decode_jwt_token(token)
    return user_id


def get_user_from_header(authorization: Optional[str] = Header(None)) -> Optional[str]:
    """Extract user ID from Authorization header (Bearer token)"""
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        return None

    token = authorization[7:]  # Remove "Bearer " prefix
    try:
        user_id = decode_jwt_token(token)
        return user_id
    except HTTPException:
        return None
