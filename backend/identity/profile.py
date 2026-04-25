from typing import Any

from storage.contracts import UserRow


def _initials_from_name(name: str) -> str:
    stripped = name.strip()
    if not stripped:
        return "U"
    compact = "".join(part[:1] for part in stripped.split() if part)
    if len(compact) >= 2:
        return compact[:2].upper()
    return stripped[:2].upper()


def get_profile(user: UserRow | None = None) -> dict[str, Any]:
    if user is None:
        raise ValueError("user is required")
    return {
        "name": user.display_name or "用户",
        "initials": _initials_from_name(user.display_name or ""),
        "email": user.email or "",
    }


def update_profile(*, user_repo: Any, user_id: str, name: str | None = None, email: str | None = None) -> dict[str, Any]:
    if name is None and email is None:
        return get_profile(user_repo.get_by_id(user_id))
    if name is not None and email is not None:
        user_repo.update(user_id, display_name=name, email=email)
    elif name is not None:
        user_repo.update(user_id, display_name=name)
    else:
        user_repo.update(user_id, email=email)
    return get_profile(user_repo.get_by_id(user_id))
