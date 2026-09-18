"""Shared fixtures for the BackEnd test suite.

Both services' auth modules are imported here: BackEnd/src is the code under test,
and Web/src supplies the minting half of the token round-trip, so the tests exercise
the real issuer rather than a reimplementation of it. pyproject.toml's
[tool.pytest.ini_options] pythonpath puts both on sys.path.
"""

import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa


@pytest.fixture(scope="session")
def jwt_keys(tmp_path_factory):
    """Write a throwaway RSA pair and EC pair, and point the loaders at them.

    Deliberately not scripts/generate-jwt-keys.sh: that writes into the repo's real
    keys/ directory, and --force there would log out every live session. Generating
    here also means the suite needs no OpenSSL and no prior setup step.
    """
    keys_dir = tmp_path_factory.mktemp("keys")

    signing_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (keys_dir / "private_key.pem").write_bytes(signing_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    (keys_dir / "public_key.pem").write_bytes(signing_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))

    enc_key = ec.generate_private_key(ec.SECP256R1())
    (keys_dir / "enc_private_key.pem").write_bytes(enc_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    (keys_dir / "enc_public_key.pem").write_bytes(enc_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ))

    previous = os.environ.get("LOCOL_JWT_KEYS_LOCATION")
    os.environ["LOCOL_JWT_KEYS_LOCATION"] = str(keys_dir)

    # Every loader is @lru_cache'd, so any that already ran - directly or via an
    # import side effect - is holding a key from the real keys/ directory or an
    # earlier tmp dir. Without this the env var above has no effect and the tests
    # would pass against the wrong keys, which is exactly the failure that would be
    # hardest to notice.
    _clear_key_caches()
    yield keys_dir

    if previous is None:
        os.environ.pop("LOCOL_JWT_KEYS_LOCATION", None)
    else:
        os.environ["LOCOL_JWT_KEYS_LOCATION"] = previous
    _clear_key_caches()


def _clear_key_caches():
    import jwt_auth
    import jwt_utils

    jwt_auth.load_public_key.cache_clear()
    jwt_auth.load_enc_private_key.cache_clear()
    jwt_utils.load_private_key.cache_clear()
    jwt_utils.load_enc_public_key.cache_clear()
