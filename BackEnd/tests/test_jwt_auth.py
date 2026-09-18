"""Tests for the nested session token: RS256 JWS wrapped in an ECDH-ES+A256KW JWE.

The first automated coverage this auth path has had. The two tests that matter most
are test_user_id_is_not_readable_from_token (the reason the JWE layer exists) and
test_algorithm_substitution_is_rejected / test_bare_jws_is_rejected (the two ways an
attacker gets to choose the format).
"""

import base64
import json

import jwt_auth
import jwt_utils
import pytest
from fastapi import HTTPException
from jwcrypto import jwe, jwk, jwt as jwcrypto_jwt
from jwcrypto.common import json_encode

pytestmark = pytest.mark.usefixtures("jwt_keys")

USER_ID = "3f6a1c48-0b7e-4d92-9a55-7c1e2b8d40af"


def _segments(token):
    return token.split(".")


def _b64_decode_loose(segment):
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def test_round_trip_recovers_user_id():
    token = jwt_utils.create_jwt_token(USER_ID)
    assert jwt_auth.decode_jwt_token(token) == USER_ID


def test_token_is_a_five_segment_jwe_naming_the_expected_algorithms():
    token = jwt_utils.create_jwt_token(USER_ID)

    segments = _segments(token)
    assert len(segments) == 5

    header = json.loads(_b64_decode_loose(segments[0]))
    assert header["alg"] == "ECDH-ES+A256KW"
    assert header["enc"] == "A256GCM"
    assert header["cty"] == "JWT"
    # A fresh ephemeral key per token is what keeps ECDH-ES semantically secure.
    assert header["epk"]["crv"] == "P-256"


def test_ephemeral_key_differs_between_tokens():
    # A fresh ephemeral key per token is a requirement of ECDH-ES, not an
    # implementation detail - reusing one across tokens would reuse the derived
    # content key. Cheap to assert, catastrophic to get wrong.
    first = json.loads(_b64_decode_loose(_segments(jwt_utils.create_jwt_token(USER_ID))[0]))
    second = json.loads(_b64_decode_loose(_segments(jwt_utils.create_jwt_token(USER_ID))[0]))
    assert first["epk"]["x"] != second["epk"]["x"]


def test_user_id_is_not_readable_from_token():
    """The point of the whole change: the browser holds this token in a cookie."""
    token = jwt_utils.create_jwt_token(USER_ID)

    assert USER_ID not in token
    for segment in _segments(token):
        try:
            decoded = _b64_decode_loose(segment)
        except Exception:
            continue
        assert USER_ID.encode() not in decoded


def test_tampered_ciphertext_is_rejected():
    segments = _segments(jwt_utils.create_jwt_token(USER_ID))
    ciphertext = segments[3]
    flipped = ("B" if ciphertext[0] != "B" else "C") + ciphertext[1:]
    tampered = ".".join(segments[:3] + [flipped] + segments[4:])

    with pytest.raises(HTTPException) as exc:
        jwt_auth.decode_jwt_token(tampered)
    assert exc.value.status_code == 401


def test_tampered_auth_tag_is_rejected():
    segments = _segments(jwt_utils.create_jwt_token(USER_ID))
    tag = segments[4]
    segments[4] = ("B" if tag[0] != "B" else "C") + tag[1:]

    with pytest.raises(HTTPException) as exc:
        jwt_auth.decode_jwt_token(".".join(segments))
    assert exc.value.status_code == 401


def test_expired_token_is_rejected():
    token = jwt_utils.create_jwt_token(USER_ID, expires_hours=-1)

    with pytest.raises(HTTPException) as exc:
        jwt_auth.decode_jwt_token(token)
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def _sign(claims, key=None):
    """Mint a bare inner JWS, the way the real issuer does."""
    token = jwcrypto_jwt.JWT(
        header={"alg": "RS256", "typ": "JWT"},
        claims=claims,
    )
    token.make_signed_token(key or jwt_utils.load_private_key())
    return token.serialize()


def _wrap(plaintext):
    """Encrypt arbitrary plaintext to the real EC public key, as an attacker could."""
    token = jwcrypto_jwt.JWT(
        header={"alg": "ECDH-ES+A256KW", "enc": "A256GCM", "typ": "JWT", "cty": "JWT"},
        claims=plaintext,
    )
    token.make_encrypted_token(jwt_utils.load_enc_public_key())
    return token.serialize()


def test_bare_jws_is_rejected():
    """A pre-cutover token stays signature-valid forever, so format must be checked."""
    with pytest.raises(HTTPException) as exc:
        jwt_auth.decode_jwt_token(_sign({"user_id": USER_ID}))
    assert exc.value.status_code == 401
    assert "log in again" in exc.value.detail


def test_algorithm_substitution_is_rejected():
    """A JWE minted with "dir" must not be accepted just because it decrypts.

    Built with jwcrypto's own permissive default allowlist on the minting side, so
    the token really is a well-formed "dir" JWE and the only thing refusing it is the
    verifier's explicit algs list. That is the property under test.
    """
    forged = jwe.JWE(
        _sign({"user_id": USER_ID}).encode("ascii"),
        json_encode({"alg": "dir", "enc": "A256GCM", "typ": "JWT", "cty": "JWT"}),
    )
    forged.add_recipient(jwk.JWK(kty="oct", k=base64.urlsafe_b64encode(b"\x00" * 32).decode().rstrip("=")))

    with pytest.raises(HTTPException) as exc:
        jwt_auth.decode_jwt_token(forged.serialize(compact=True))
    assert exc.value.status_code == 401


def test_token_signed_by_a_different_key_is_rejected():
    """Decrypting proves nothing about the sender - only the signature does."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    attacker = jwk.JWK.from_pem(
        rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

    with pytest.raises(HTTPException) as exc:
        jwt_auth.decode_jwt_token(_wrap(_sign({"user_id": USER_ID}, key=attacker)))
    assert exc.value.status_code == 401


def test_missing_user_id_claim_is_rejected():
    with pytest.raises(HTTPException) as exc:
        jwt_auth.decode_jwt_token(_wrap(_sign({"sub": USER_ID})))
    assert exc.value.status_code == 401
    assert "user_id" in exc.value.detail


def test_encrypted_payload_that_is_not_a_jws_is_rejected():
    """A correctly-encrypted envelope around junk must still 401, not 500.

    This is the path where jwcrypto raises something outside JWException - a plain
    TypeError or ValueError - which is exactly how a tampered token used to escape as
    a server error. Guards the catch clause in decode_jwt_token.
    """
    for junk in ['not a jws at all', '{"user_id": "smuggled"}', 'a.b', '']:
        with pytest.raises(HTTPException) as exc:
            jwt_auth.decode_jwt_token(_wrap(junk))
        assert exc.value.status_code == 401, f"junk payload {junk!r} did not 401"


def test_garbage_is_rejected():
    for bad in ["", "not-a-token", "a.b.c.d.e", "x" * 200]:
        with pytest.raises(HTTPException) as exc:
            jwt_auth.decode_jwt_token(bad)
        assert exc.value.status_code == 401


def test_get_user_from_header_accepts_bearer_and_rejects_the_rest():
    token = jwt_utils.create_jwt_token(USER_ID)

    assert jwt_auth.get_user_from_header(f"Bearer {token}") == USER_ID
    assert jwt_auth.get_user_from_header(None) is None
    assert jwt_auth.get_user_from_header(token) is None          # no scheme
    assert jwt_auth.get_user_from_header("Basic abc") is None
    assert jwt_auth.get_user_from_header("Bearer nonsense") is None
