"""
Argon2 password hashing — replaces PBKDF2 from the old system.

Argon2id is memory-hard, GPU-resistant, and recommended for defense applications.
The salt is embedded in the hash string, so no separate salt column is needed.
"""
from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

# Configure with defense-grade parameters
_hasher = PasswordHasher(
    time_cost=3,       # 3 iterations
    memory_cost=65536,  # 64 MB
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    """Hash a password using argon2id. Returns the full hash string (includes salt)."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against an argon2id hash. Returns True if valid."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Check if a hash needs to be rehashed (e.g., after parameter changes)."""
    return _hasher.check_needs_rehash(password_hash)
