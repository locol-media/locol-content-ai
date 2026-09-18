import os
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from jwcrypto import jwk, jwt

# The session token is a nested JWT: an RS256-signed JWS (this file's private key)
# wrapped in a JWE encrypted to BackEnd's EC public key.
#
# The signature is what makes the token unforgeable, and it has to stay. ECDH-ES is
# *anonymous* encryption - the sender needs only the recipient's public key, so
# anyone holding enc_public_key.pem could mint a JWE claiming any user_id. There is
# no second authorization check anywhere in BackEnd (the token is what selects the
# user's SQLite file), so a bare JWE would hand out every account. The JWE layer is
# here for confidentiality only: the token is handed to a browser in a URL fragment
# and stored in a JS-readable cookie, where a plain JWS payload is trivially
# base64-decoded by the end user.
#
# BackEnd/src/jwt_auth.py unwraps this and must agree on all three algorithms.
JWS_ALG = "RS256"
JWE_ALG = "ECDH-ES+A256KW"
JWE_ENC = "A256GCM"


def _keys_dir():
    return os.environ.get('LOCOL_JWT_KEYS_LOCATION', '../keys')


@lru_cache(maxsize=1)
def load_private_key():
    """Load the RSA private key for signing session tokens.

    Cached: this used to re-read and re-parse the PEM on every login, the same bug
    BackEnd's public-key loader already fixed. The key is mounted at startup and does
    not change at runtime."""
    key_path = os.path.join(_keys_dir(), 'private_key.pem')
    with open(key_path, 'rb') as key_file:
        return jwk.JWK.from_pem(key_file.read())


@lru_cache(maxsize=1)
def load_enc_public_key():
    """Load BackEnd's EC public key, used to encrypt the signed token to it.

    Note this is the reverse of the signing pair: Web holds the *private* signing key
    and the *public* encryption key, BackEnd holds the other half of each."""
    key_path = os.path.join(_keys_dir(), 'enc_public_key.pem')
    with open(key_path, 'rb') as key_file:
        return jwk.JWK.from_pem(key_file.read())


def create_jwt_token(user_id: str, expires_hours: int = 24) -> str:
    """Create a session token signed with the private key and encrypted to BackEnd"""
    now = datetime.now(timezone.utc)

    # Integer timestamps, not datetime objects. PyJWT used to convert datetimes
    # silently; jwcrypto does not, and a datetime here serializes to something no
    # verifier will accept as an expiry.
    claims = {
        "user_id": user_id,
        "exp": int((now + timedelta(hours=expires_hours)).timestamp()),
        "iat": int(now.timestamp()),
    }

    inner = jwt.JWT(header={"alg": JWS_ALG, "typ": "JWT"}, claims=claims)
    inner.make_signed_token(load_private_key())

    # cty: JWT marks the ciphertext as itself being a JWT - RFC 7519 section 5.2.
    outer = jwt.JWT(
        header={"alg": JWE_ALG, "enc": JWE_ENC, "typ": "JWT", "cty": "JWT"},
        claims=inner.serialize(),
    )
    outer.make_encrypted_token(load_enc_public_key())

    return outer.serialize()
