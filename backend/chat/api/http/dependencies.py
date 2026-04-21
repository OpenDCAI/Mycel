"""Chat HTTP dependency helpers."""

from backend.identity.auth.user_resolution import get_current_user_id as resolve_current_user_id
from backend.runtime_bootstrap.request_app import get_app as resolve_app

get_current_user_id = resolve_current_user_id
get_app = resolve_app
