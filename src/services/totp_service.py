import pyotp


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """
    Verify a TOTP code against the given secret.

    valid_window=1 allows one time-step tolerance (±30 seconds).
    """
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=valid_window)


def generate_totp(secret: str) -> str:
    """Generate the current TOTP code for the given secret (for testing)."""
    return pyotp.TOTP(secret).now()
