"""Storage utility functions."""

import secrets
import string

_ID_ALPHABET = string.ascii_letters + string.digits


def generate_agent_user_id() -> str:
    """Generate agent user ID: m_{12 random alphanumeric chars}."""
    return "m_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))


def generate_agent_config_id() -> str:
    """Generate agent config ID: cfg_{12 random alphanumeric chars}."""
    return "cfg_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))
