"""Authentication service — Supabase Auth backed register, login, JWT verify."""

from __future__ import annotations

import logging
import os
import time

import jwt

from storage.contracts import AccountRepo, EntityRepo, EntityRow, InviteCodeRepo, MemberRepo, MemberRow, MemberType

logger = logging.getLogger(__name__)

SUPABASE_JWT_ALGORITHM = "HS256"


class AuthService:
    def __init__(
        self,
        members: MemberRepo,
        accounts: AccountRepo,
        entities: EntityRepo,
        supabase_client=None,
        invite_codes: InviteCodeRepo | None = None,
    ) -> None:
        self._members = members
        self._accounts = accounts
        self._entities = entities
        self._sb = supabase_client  # None in sqlite-only mode
        self._invite_codes = invite_codes

    # ------------------------------------------------------------------
    # Registration flow (standard Supabase signUp)
    # Step 1: send_otp(email, password) → signUp creates user, GoTrue sends OTP
    # Step 2: verify_register_otp(...)  → verifyOtp(type:signup), returns temp_token
    # Step 3: complete_register(...)    → validate invite, create member records
    # ------------------------------------------------------------------

    def send_otp(self, email: str, password: str, invite_code: str) -> None:
        """Validate invite code, create user via signUp (sends confirmation OTP to email)."""
        if self._sb is None:
            raise RuntimeError("Supabase client required.")
        if self._invite_codes is None or not self._invite_codes.is_valid(invite_code):
            raise ValueError("邀请码无效或已过期")
        from supabase_auth.errors import AuthApiError

        try:
            self._sb.auth.sign_up({"email": email, "password": password})
        except AuthApiError as e:
            msg = e.message or ""
            if "already registered" in msg or "already exists" in msg:
                raise ValueError("该邮箱已注册，请直接登录") from e
            raise ValueError("发送验证码失败，请稍后重试") from e

    def verify_register_otp(self, email: str, token: str) -> dict:
        """Verify signup OTP. Returns temp_token to be used in complete_register."""
        if self._sb is None:
            raise RuntimeError("Supabase client required.")
        from supabase_auth.errors import AuthApiError

        try:
            resp = self._sb.auth.verify_otp({"email": email, "token": token, "type": "signup"})
        except AuthApiError as e:
            raise ValueError(f"验证码错误: {e.message}") from e
        if resp.user is None or resp.session is None:
            raise ValueError("验证码无效或已过期")
        return {"temp_token": resp.session.access_token}

    def complete_register(self, temp_token: str, invite_code: str) -> dict:
        """Complete registration: validate invite code, create member records."""
        if self._sb is None:
            raise RuntimeError("Supabase client required.")

        # 1. Decode temp_token to get user_id
        jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
        if not jwt_secret:
            raise RuntimeError("SUPABASE_JWT_SECRET not set.")
        try:
            payload = jwt.decode(temp_token, jwt_secret, algorithms=[SUPABASE_JWT_ALGORITHM], options={"verify_aud": False})
        except jwt.InvalidTokenError as e:
            raise ValueError("会话已过期，请重新验证邮箱") from e
        auth_user_id = payload["sub"]

        # 2. Validate invite code (re-check; repo handles expired/used)
        if self._invite_codes is None or not self._invite_codes.is_valid(invite_code):
            raise ValueError("邀请码无效或已过期")

        # 3. Create member records (idempotent guard)
        email_from_payload = payload.get("email", "")
        existing = self._members.get_by_id(auth_user_id)
        if existing is None:
            mycel_id = self._sb.rpc("next_mycel_id").execute().data
            now = time.time()
            display_name = email_from_payload.split("@")[0]

            # Create member row
            self._members.create(
                MemberRow(
                    id=auth_user_id,
                    name=display_name,
                    type=MemberType.HUMAN,
                    email=email_from_payload,
                    mycel_id=mycel_id,
                    created_at=now,
                )
            )

            # Human entity
            entity_id = f"{auth_user_id}-1"
            self._entities.create(
                EntityRow(
                    id=entity_id,
                    type="human",
                    member_id=auth_user_id,
                    name=display_name,
                    thread_id=None,
                    created_at=now,
                )
            )

            # Initial agents
            first_agent_info = self._create_initial_agents(auth_user_id, now)
        else:
            entity_id = f"{auth_user_id}-1"
            display_name = existing.name
            mycel_id = existing.mycel_id
            owned_agents = self._members.list_by_owner_user_id(auth_user_id)
            first_agent_info = (
                {"id": owned_agents[0].id, "name": owned_agents[0].name, "type": "mycel_agent", "avatar": None} if owned_agents else None
            )

        # 4. Mark invite code used (atomic via repo)
        if self._invite_codes is not None:
            self._invite_codes.use(invite_code, auth_user_id)

        logger.info("Registered user %s (mycel_id=%s)", email_from_payload, mycel_id)
        return {
            "token": temp_token,
            "user": {"id": auth_user_id, "name": display_name, "mycel_id": mycel_id, "email": email_from_payload, "avatar": None},
            "agent": first_agent_info,
            "entity_id": entity_id,
        }

    def login(self, identifier: str, password: str) -> dict:
        """Login with email or mycel_id + password."""
        if self._sb is None:
            raise RuntimeError("Supabase client required for login. Set LEON_STORAGE_STRATEGY=supabase.")

        # Resolve email
        email = self._resolve_email(identifier)

        from supabase_auth.errors import AuthApiError

        # Sign in via Supabase
        try:
            resp = self._sb.auth.sign_in_with_password({"email": email, "password": password})
        except AuthApiError:
            raise ValueError("邮箱或密码错误")
        if resp.user is None or resp.session is None:
            raise ValueError("邮箱或密码错误")

        auth_user_id = str(resp.user.id)
        token = resp.session.access_token

        # Load member info
        member = self._members.get_by_id(auth_user_id)
        if member is None:
            raise ValueError("账号数据异常，请联系支持")

        # Load entities + agents
        entities = self._entities.get_by_member_id(auth_user_id)
        human_entity = next((e for e in entities if e.type == "human"), None)
        owned_agents = self._members.list_by_owner_user_id(auth_user_id)
        agent_info = None
        if owned_agents:
            a = owned_agents[0]
            agent_info = {"id": a.id, "name": a.name, "type": a.type.value, "avatar": a.avatar}

        logger.info("Login: %s (mycel_id=%s)", email, member.mycel_id)
        return {
            "token": token,
            "user": {
                "id": auth_user_id,
                "name": member.name,
                "mycel_id": member.mycel_id,
                "email": member.email,
                "avatar": member.avatar,
            },
            "agent": agent_info,
            "entity_id": human_entity.id if human_entity else None,
        }

    def verify_token(self, token: str) -> dict:
        """Verify Supabase JWT. Returns {user_id, entity_id}."""
        jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
        if not jwt_secret:
            raise RuntimeError("SUPABASE_JWT_SECRET env var required for token verification.")
        try:
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=[SUPABASE_JWT_ALGORITHM],
                options={"verify_aud": False},
            )
            return {"user_id": payload["sub"], "entity_id": payload.get("entity_id")}
        except jwt.ExpiredSignatureError:
            raise ValueError("Token 已过期，请重新登录")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Token 无效: {e}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_email(self, identifier: str) -> str:
        """Turn mycel_id (numeric string) or email into email address."""
        if identifier.strip().lstrip("0123456789") == "" and identifier.strip().isdigit():
            member = self._members.get_by_mycel_id(int(identifier.strip()))
            if member is None or member.email is None:
                raise ValueError("用户不存在")
            return member.email
        return identifier.strip()

    def _create_initial_agents(self, owner_user_id: str, now: float) -> dict | None:
        """Create Toad and Morel agents for a new user. Returns first agent info."""
        from pathlib import Path

        from backend.web.services.member_service import MEMBERS_DIR, _write_agent_md, _write_json
        from storage.providers.sqlite.member_repo import generate_member_id

        initial_agents = [
            {"name": "Toad", "description": "Curious and energetic assistant", "avatar": "toad.jpeg"},
            {"name": "Morel", "description": "Thoughtful senior analyst", "avatar": "morel.jpeg"},
        ]
        assets_dir = Path(__file__).resolve().parents[3] / "assets"
        first_agent_info = None

        for i, agent_def in enumerate(initial_agents):
            agent_id = generate_member_id()
            agent_dir = MEMBERS_DIR / agent_id
            agent_dir.mkdir(parents=True, exist_ok=True)
            _write_agent_md(agent_dir / "agent.md", name=agent_def["name"], description=agent_def["description"])
            _write_json(
                agent_dir / "meta.json",
                {"status": "active", "version": "1.0.0", "created_at": int(now * 1000), "updated_at": int(now * 1000)},
            )
            self._members.create(
                MemberRow(
                    id=agent_id,
                    name=agent_def["name"],
                    type=MemberType.MYCEL_AGENT,
                    description=agent_def["description"],
                    config_dir=str(agent_dir),
                    owner_user_id=owner_user_id,
                    created_at=now,
                )
            )
            src_avatar = assets_dir / agent_def["avatar"]
            if src_avatar.exists():
                try:
                    from backend.web.routers.entities import process_and_save_avatar

                    avatar_path = process_and_save_avatar(src_avatar, agent_id)
                    self._members.update(agent_id, avatar=avatar_path, updated_at=now)
                except Exception as e:
                    logger.warning("Avatar copy failed for %s: %s", agent_def["name"], e)
            if i == 0:
                first_agent_info = {"id": agent_id, "name": agent_def["name"], "type": "mycel_agent", "avatar": None}

        return first_agent_info
