# Messaging Chat Access Shell Design

## Goal

Remove the repeated router-local chat lookup and membership gate in `backend/web/routers/messaging.py` without changing any chat contract.

## Scope

In scope:

- `GET /api/chats/{chat_id}`
- `DELETE /api/chats/{chat_id}`

Out of scope:

- `GET /api/chats/{chat_id}/messages`
- message send/retract/delete-for-self
- SSE event auth
- messaging service implementation

## Existing Problem

`get_chat` and `delete_chat` repeat the same opening shell:

1. `chat_repo.get_by_id(chat_id)`
2. `404 "Chat not found"` if absent
3. `_messaging(app).is_chat_member(chat_id, user_id)`
4. `403 "Not a participant of this chat"` if forbidden

That is a clean router-local seam. The two routes diverge only after the access shell:

- `get_chat` reads members and shapes a response body
- `delete_chat` deletes the chat and returns `{"status": "deleted"}`

## Design

Keep the change inside `backend/web/routers/messaging.py`.

Add one helper:

```python
def _get_accessible_chat_or_404(app: Any, chat_id: str, user_id: str) -> Any:
    ...
```

The helper must:

- read the chat from `chat_repo`
- raise `HTTPException(404, "Chat not found")` when missing
- enforce `_messaging(app).is_chat_member(chat_id, user_id)`
- raise `HTTPException(403, "Not a participant of this chat")` when forbidden
- return the chat object on success

Only `get_chat` and `delete_chat` should delegate to this helper.

## Testing

Add focused tests in `tests/Integration/test_messaging_router.py` that pin:

- helper returns the chat object when it exists and the user is a member
- helper raises `404` for missing chat
- helper raises `403` for non-member access
- `get_chat` uses the helper instead of its own chat lookup
- `delete_chat` uses the helper instead of its own chat lookup

Those tests must stay on the router shell. They must not drift into message listing, SSE, or messaging-service internals.

## Stopline

Do not:

- change `list_messages` to use this helper
- change `get_chat` response shaping
- change delete semantics
- touch SSE auth or token verification
- move the helper into a shared utility module
