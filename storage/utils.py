"""Storage utility functions."""

import secrets
import string

_ID_ALPHABET = string.ascii_letters + string.digits


def generate_member_id() -> str:
    """Generate member ID: m_{12 random alphanumeric chars}."""
    return "m_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))
