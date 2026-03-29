"""WeChat connection service — ilink API client + connection lifecycle + background poll.

Uses the official WeChat ClawBot ilink API at ilinkai.weixin.qq.com.
Protocol: HTTP/JSON long-polling, modeled after Telegram Bot API.
Auth: Bearer token obtained via QR code scan.

@@@per-user — each human entity_id gets its own WeChatConnection.
entity_id is the social identity in Leon's network, not member_id (which is the template).
Polling auto-starts at backend boot via lifespan.py for all users with saved credentials.

@@@no-globals — WeChatConnectionRegistry lives on app.state, not module-level.
"""

import asyncio
import json
import logging
import os
import random
import struct
import time
from base64 import b64encode
from pathlib import Path
from typing import Awaitable, Callable, Literal

import httpx
from pydantic import BaseModel

from config.user_paths import user_home_path, user_home_read_candidates

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
BOT_TYPE = "3"
CHANNEL_VERSION = "0.1.0"
LONG_POLL_TIMEOUT_S = 35
SEND_TIMEOUT_S = 15

MSG_TYPE_USER = 1
MSG_TYPE_BOT = 2
MSG_ITEM_TEXT = 1
MSG_ITEM_VOICE = 3
MSG_STATE_FINISH = 2

CONNECTIONS_BASE = user_home_path("connections", "wechat")

RoutingType = Literal["thread", "chat"]

# @@@delivery-callback — injected at construction, avoids circular import of app
DeliveryFn = Callable[["WeChatConnection", "WeChatMessage"], Awaitable[None]]


# --- Pydantic models for API ---


class WeChatCredentials(BaseModel):
    token: str
    base_url: str = DEFAULT_BASE_URL
    account_id: str
    user_id: str = ""
    saved_at: str = ""


class RoutingConfig(BaseModel):
    type: RoutingType | None = None
    id: str | None = None
    label: str = ""


class QrPollRequest(BaseModel):
    qrcode: str


class RoutingSetRequest(BaseModel):
    type: RoutingType
    id: str
    label: str = ""


class WeChatMessage(BaseModel):
    from_user_id: str
    text: str
    context_token: str

    class Config:
        frozen = True


class WeChatAPIError(Exception):
    pass


class SessionExpiredError(WeChatAPIError):
    pass


# --- ilink protocol helpers ---


def _random_wechat_uin() -> str:
    val = struct.unpack(">I", os.urandom(4))[0]
    return b64encode(str(val).encode()).decode()


def _build_headers(token: str | None = None, body: str | None = None) -> dict[str, str]:
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "X-WECHAT-UIN": _random_wechat_uin(),
    }
    if body:
        headers["Content-Length"] = str(len(body.encode()))
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"
    return headers


def _extract_text(msg: dict) -> str:
    items = msg.get("item_list") or []
    for item in items:
        if item.get("type") == MSG_ITEM_TEXT:
            text = (item.get("text_item") or {}).get("text", "")
            ref = item.get("ref_msg")
            if ref and ref.get("title"):
                return f"[引用: {ref['title']}]\n{text}"
            return text
        if item.get("type") == MSG_ITEM_VOICE:
            return (item.get("voice_item") or {}).get("text", "")
    return ""


# --- Per-user persistence (keyed by entity_id) ---


def _user_dir(entity_id: str) -> Path:
    return CONNECTIONS_BASE / entity_id


def _user_dir_candidates(entity_id: str) -> tuple[Path, ...]:
    return tuple(path / entity_id for path in user_home_read_candidates("connections", "wechat"))


def _save_json(entity_id: str, filename: str, data: dict) -> None:
    d = _user_dir(entity_id)
    d.mkdir(parents=True, exist_ok=True)
    path = d / filename
    path.write_text(json.dumps(data, indent=2))
    if filename == "credentials.json":
        path.chmod(0o600)


def _load_json(entity_id: str, filename: str) -> dict | None:
    for path in reversed(_user_dir_candidates(entity_id)):
        candidate = path / filename
        if not candidate.exists():
            continue
        try:
            return json.loads(candidate.read_text())
        except (json.JSONDecodeError, KeyError) as e:
            logger.error("Failed to load %s for %s: %s", filename, entity_id[:12], e)
    return None


def _delete_file(entity_id: str, filename: str) -> None:
    seen: set[Path] = set()
    for user_dir in _user_dir_candidates(entity_id):
        path = user_dir / filename
        if path in seen:
            continue
        seen.add(path)
        if path.exists():
            path.unlink()


# --- WeChatConnection (one per human entity) ---


class WeChatConnection:
    """A single user's WeChat connection. Keyed by entity_id."""

    def __init__(self, entity_id: str, delivery_fn: DeliveryFn | None = None) -> None:
        self.entity_id = entity_id
        self._delivery_fn = delivery_fn
        self._credentials: WeChatCredentials | None = None
        self._context_tokens: dict[str, str] = {}
        self._sync_buf: str = ""
        self._poll_task: asyncio.Task | None = None
        self._routing = RoutingConfig()
        # @@@no-proxy — trust_env=False prevents httpx from inheriting
        # http_proxy/all_proxy which causes bimodal latency on long-poll.
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(LONG_POLL_TIMEOUT_S + 5),
            trust_env=False,
        )

        # Load persisted state
        routing_data = _load_json(entity_id, "routing.json")
        if routing_data:
            try:
                self._routing = RoutingConfig(**routing_data)
            except Exception:
                pass

        ctx = _load_json(entity_id, "context_tokens.json")
        if ctx:
            self._context_tokens = ctx

        creds_data = _load_json(entity_id, "credentials.json")
        if creds_data:
            try:
                self._credentials = WeChatCredentials(**creds_data)
                logger.info("Loaded WeChat credentials for entity=%s", entity_id[:12])
            except Exception as e:
                logger.error("Invalid WeChat credentials for %s: %s", entity_id[:12], e)

    @property
    def connected(self) -> bool:
        return self._credentials is not None

    @property
    def polling(self) -> bool:
        return self._poll_task is not None and not self._poll_task.done()

    @property
    def routing(self) -> RoutingConfig:
        return self._routing

    def set_routing(self, config: RoutingConfig) -> None:
        self._routing = config
        _save_json(self.entity_id, "routing.json", config.model_dump())

    def get_state(self) -> dict:
        if not self._credentials:
            return {"connected": False, "routing": self._routing.model_dump()}
        return {
            "connected": True,
            "polling": self.polling,
            "account_id": self._credentials.account_id,
            "user_id": self._credentials.user_id,
            "contact_count": len(self._context_tokens),
            "contacts": self.list_contacts(),
            "routing": self._routing.model_dump(),
        }

    def list_contacts(self) -> list[dict[str, str]]:
        return [
            {"user_id": uid, "display_name": uid.split("@")[0] or uid}
            for uid in self._context_tokens
        ]

    # --- QR Login ---

    async def get_qr_code(self) -> dict:
        url = f"{DEFAULT_BASE_URL}/ilink/bot/get_bot_qrcode?bot_type={BOT_TYPE}"
        resp = await self._http.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return {"qrcode": data["qrcode"], "qrcode_img_url": data["qrcode_img_content"]}

    async def poll_qr_status(self, qrcode: str) -> dict:
        url = f"{DEFAULT_BASE_URL}/ilink/bot/get_qrcode_status?qrcode={qrcode}"
        try:
            resp = await self._http.get(
                url, headers={"iLink-App-ClientVersion": "1"},
                timeout=LONG_POLL_TIMEOUT_S + 5,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            return {"status": "wait"}

        status = data.get("status", "wait")
        if status == "confirmed":
            bot_token = data.get("bot_token")
            bot_id = data.get("ilink_bot_id")
            if not bot_token or not bot_id:
                return {"status": "error", "message": "Missing bot credentials in response"}
            creds = WeChatCredentials(
                token=bot_token,
                base_url=data.get("baseurl") or DEFAULT_BASE_URL,
                account_id=bot_id,
                user_id=data.get("ilink_user_id", ""),
                saved_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            )
            self._credentials = creds
            _save_json(self.entity_id, "credentials.json", creds.model_dump())
            logger.info("WeChat connected for entity=%s account=%s",
                        self.entity_id[:12], creds.account_id)
            self.start_polling()
            return {"status": "confirmed", "account_id": creds.account_id}
        return {"status": status}

    # --- Disconnect ---

    def disconnect(self) -> None:
        self.stop_polling()
        self._credentials = None
        self._context_tokens.clear()
        self._sync_buf = ""
        _delete_file(self.entity_id, "credentials.json")
        _delete_file(self.entity_id, "context_tokens.json")
        logger.info("WeChat disconnected for entity=%s", self.entity_id[:12])

    async def close(self) -> None:
        """Shutdown: stop polling + close HTTP client."""
        self.stop_polling()
        await self._http.aclose()

    # --- Polling ---

    def start_polling(self) -> None:
        if self.polling:
            return
        if not self._credentials:
            raise RuntimeError("Cannot start polling: not connected")
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("WeChat polling started for entity=%s", self.entity_id[:12])

    def stop_polling(self) -> None:
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            self._poll_task = None

    async def _deliver_message(self, msg: WeChatMessage) -> None:
        """Deliver via injected callback. No circular imports."""
        if not self._delivery_fn:
            logger.warning("No delivery function configured for entity=%s", self.entity_id[:12])
            return
        if not self._routing.type or not self._routing.id:
            logger.debug("WeChat message not delivered — no routing configured")
            return
        try:
            await self._delivery_fn(self, msg)
        except Exception:
            logger.exception("Failed to deliver WeChat message")

    async def _poll_loop(self) -> None:
        consecutive_failures = 0
        while True:
            try:
                messages = await self._get_updates()
                consecutive_failures = 0
                for msg in messages:
                    logger.info("WeChat[%s] from=%s: %s",
                                self.entity_id[:8], msg.from_user_id[:20], msg.text[:60])
                    asyncio.create_task(self._deliver_message(msg))
            except asyncio.CancelledError:
                return
            except SessionExpiredError:
                logger.error("WeChat session expired for entity=%s", self.entity_id[:12])
                self._credentials = None
                _delete_file(self.entity_id, "credentials.json")
                return
            except Exception:
                consecutive_failures += 1
                logger.exception("WeChat poll error #%d entity=%s", consecutive_failures, self.entity_id[:12])
                if consecutive_failures >= 3:
                    consecutive_failures = 0
                    await asyncio.sleep(30)
                else:
                    await asyncio.sleep(2)

    async def _get_updates(self) -> list[WeChatMessage]:
        if not self._credentials:
            raise RuntimeError("Not connected")
        body = json.dumps({
            "get_updates_buf": self._sync_buf,
            "base_info": {"channel_version": CHANNEL_VERSION},
        })
        headers = _build_headers(self._credentials.token, body)
        try:
            resp = await self._http.post(
                f"{self._credentials.base_url}/ilink/bot/getupdates",
                content=body, headers=headers,
                timeout=LONG_POLL_TIMEOUT_S + 5,
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.TimeoutException:
            return []

        if data.get("ret", 0) != 0 or data.get("errcode", 0) != 0:
            errcode = data.get("errcode", 0)
            errmsg = data.get("errmsg", "")
            if errcode == -14:
                raise SessionExpiredError("Session expired")
            raise WeChatAPIError(f"getUpdates: errcode={errcode} {errmsg}")

        if data.get("get_updates_buf"):
            self._sync_buf = data["get_updates_buf"]

        messages = []
        tokens_changed = False
        for msg in data.get("msgs") or []:
            if msg.get("message_type") != MSG_TYPE_USER:
                continue
            text = _extract_text(msg)
            if not text:
                continue
            sender = msg.get("from_user_id", "unknown")
            ctx_token = msg.get("context_token", "")
            if ctx_token:
                self._context_tokens[sender] = ctx_token
                tokens_changed = True
            messages.append(WeChatMessage(
                from_user_id=sender, text=text, context_token=ctx_token,
            ))
        if tokens_changed:
            await asyncio.to_thread(_save_json, self.entity_id, "context_tokens.json", self._context_tokens)
        return messages

    # --- Send ---

    async def send_message(self, to_user_id: str, text: str) -> str:
        if not self._credentials:
            raise RuntimeError("WeChat not connected")
        context_token = self._context_tokens.get(to_user_id)
        if not context_token:
            raise RuntimeError(
                f"No context_token for {to_user_id}. "
                "The user needs to message the bot first."
            )
        client_id = f"leon:{int(time.time())}-{random.randint(0, 0xFFFF):04x}"
        body = json.dumps({
            "msg": {
                "from_user_id": "",
                "to_user_id": to_user_id,
                "client_id": client_id,
                "message_type": MSG_TYPE_BOT,
                "message_state": MSG_STATE_FINISH,
                "item_list": [{"type": MSG_ITEM_TEXT, "text_item": {"text": text}}],
                "context_token": context_token,
            },
            "base_info": {"channel_version": CHANNEL_VERSION},
        })
        headers = _build_headers(self._credentials.token, body)
        resp = await self._http.post(
            f"{self._credentials.base_url}/ilink/bot/sendmessage",
            content=body, headers=headers, timeout=SEND_TIMEOUT_S,
        )
        resp.raise_for_status()
        return client_id


# --- WeChatConnectionRegistry (lives on app.state) ---


class WeChatConnectionRegistry:
    """Manages per-user WeChatConnections. Lives on app.state, not module-level."""

    def __init__(self, delivery_fn: DeliveryFn | None = None) -> None:
        self._connections: dict[str, WeChatConnection] = {}
        self._delivery_fn = delivery_fn

    def get(self, entity_id: str) -> WeChatConnection:
        if entity_id not in self._connections:
            self._connections[entity_id] = WeChatConnection(entity_id, self._delivery_fn)
        return self._connections[entity_id]

    def auto_start_all(self) -> None:
        """Resume polling for all users with saved credentials on disk."""
        if not CONNECTIONS_BASE.exists():
            return
        for user_dir in CONNECTIONS_BASE.iterdir():
            if user_dir.is_dir() and (user_dir / "credentials.json").exists():
                conn = self.get(user_dir.name)
                if conn.connected and not conn.polling:
                    conn.start_polling()

    def evict_duplicates(self, account_id: str, keep_entity_id: str) -> None:
        """@@@unique-wechat — one WeChat account → one Leon entity. Last one wins."""
        for eid, conn in list(self._connections.items()):
            if eid == keep_entity_id:
                continue
            if conn._credentials and conn._credentials.account_id == account_id:
                logger.info("Evicting WeChat: entity=%s (same account=%s)", eid[:12], account_id[:12])
                conn.disconnect()

        if CONNECTIONS_BASE.exists():
            for user_dir in CONNECTIONS_BASE.iterdir():
                if not user_dir.is_dir() or user_dir.name == keep_entity_id:
                    continue
                data = _load_json(user_dir.name, "credentials.json")
                if data and data.get("account_id") == account_id:
                    logger.info("Evicting persisted WeChat: entity=%s", user_dir.name[:12])
                    _delete_file(user_dir.name, "credentials.json")
                    _delete_file(user_dir.name, "context_tokens.json")

    async def shutdown(self) -> None:
        """Close all connections gracefully."""
        for conn in self._connections.values():
            await conn.close()
        self._connections.clear()
