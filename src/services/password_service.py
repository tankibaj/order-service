import bcrypt

# Dummy hash used for constant-time comparison when user is not found
# Pre-computed to avoid timing attacks on user enumeration
_DUMMY_HASH: bytes = bcrypt.hashpw(b"dummy-non-existent-user", bcrypt.gensalt(rounds=4))


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its bcrypt hash."""
    return bcrypt.checkpw(password.encode(), password_hash.encode())


def dummy_verify() -> None:
    """
    Run a dummy bcrypt check to maintain constant-time response
    when the user does not exist (anti-enumeration).
    """
    bcrypt.checkpw(b"dummy-password", _DUMMY_HASH)
