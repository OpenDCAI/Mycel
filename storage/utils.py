import secrets
import string

_ID_ALPHABET = string.ascii_letters + string.digits


def generate_agent_user_id() -> str:
    return "m_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))


def generate_agent_config_id() -> str:
    return "cfg_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))


def generate_skill_id() -> str:
    return "skill_" + "".join(secrets.choice(_ID_ALPHABET) for _ in range(12))
