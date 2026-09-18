import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


def _load_key() -> bytes:
    keys_dir = os.environ.get('LOCOL_DB_ENCRYPTION_KEY_LOCATION', '../keys')
    key_path = os.path.join(keys_dir, 'db_encryption.key')
    with open(key_path, 'rb') as key_file:
        return key_file.read().strip()


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    return Fernet(_load_key())


class UndecryptableValue(Exception):
    """A stored value could not be decrypted with the current key."""


def encrypt_value(value):
    """Encrypt a string value for storage. Falsy values pass through unchanged."""
    if not value:
        return value
    return _fernet().encrypt(value.encode()).decode()


def decrypt_value(value):
    """
    Decrypt a stored value. Falsy values pass through unchanged.

    Raises UndecryptableValue if the value doesn't decrypt under the current key.
    There is deliberately no fallback: a value that won't decrypt is never assumed
    to be a pre-encryption plaintext value, and is never written back. Guessing
    would make a wrong key indistinguishable from unencrypted data, which is how
    a replaced key silently destroyed the values it could no longer read.
    """
    if not value:
        return value
    try:
        return _fernet().decrypt(value.encode()).decode()
    except InvalidToken as e:
        raise UndecryptableValue("value does not decrypt under the current key") from e


def decrypt_or_none(value):
    """
    Decrypt a stored value, or return None if it isn't readable under the current key.

    For callers scanning stored keys for a marker prefix, where an unreadable value
    simply isn't a match. Like decrypt_value(), this never returns the raw stored
    value - an unreadable one is reported as absent, not passed off as plaintext.
    """
    if not value:
        return value
    try:
        return decrypt_value(value)
    except UndecryptableValue:
        return None
