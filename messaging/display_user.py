from __future__ import annotations

from protocols.identity_read import DisplayUserLookup


def resolve_messaging_display_user(*, user_lookup: DisplayUserLookup, social_user_id: str):
    return user_lookup.get_by_id(social_user_id)
