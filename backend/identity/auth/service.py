from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

import jwt

from backend.identity.avatar.files import process_and_save_avatar
from backend.identity.contact_bootstrap import ensure_owner_agent_contact
from backend.sandboxes.recipe_bootstrap import seed_default_recipes
from config.agent_config_types import AgentConfig
from storage.contracts import InviteCodeRepo, UserRepo, UserRow, UserType
from storage.providers.supabase import _query as q

logger = logging.getLogger(__name__)

SUPABASE_JWT_ALGORITHM = "HS256"


class ExternalUserAlreadyExistsError(ValueError):
    pass


class AuthService:
    def __init__(
        self,
        users: UserRepo,
        agent_configs=None,
        supabase_client=None,
        supabase_auth_client=None,
        supabase_auth_client_factory: Callable[[], object] | None = None,
        invite_codes: InviteCodeRepo | None = None,
        contact_repo=None,
        recipe_repo=None,
    ) -> None:
        self._users = users
        self._agent_configs = agent_configs
        self._sb = supabase_client  # storage/service-role client
        self._sb_auth = supabase_auth_client  # end-user auth client
        self._sb_auth_factory = supabase_auth_client_factory
        self._invite_codes = invite_codes
        self._contact_repo = contact_repo
        self._recipe_repo = recipe_repo

    def send_otp(self, email: str, password: str, invite_code: str) -> None:
        auth_client = self._auth_api(self._require_auth_client())
        if self._sb is None:
            raise RuntimeError("Supabase client required.")
        if self._invite_codes is None or not self._invite_codes.is_valid(invite_code):
            raise ValueError("邀请码无效或已过期")
        from supabase_auth.errors import AuthApiError

        try:
            auth_client.sign_up({"email": email, "password": password})
        except AuthApiError as e:
            msg = e.message or ""
            if "already registered" in msg or "already exists" in msg:
                raise ValueError("该邮箱已注册，请直接登录") from e
            raise ValueError("发送验证码失败，请稍后重试") from e

    def verify_register_otp(self, email: str, token: str) -> dict:
        auth_client = self._auth_api(self._require_auth_client())
        if self._sb is None:
            raise RuntimeError("Supabase client required.")
        from supabase_auth.errors import AuthApiError

        try:
            resp = auth_client.verify_otp({"email": email, "token": token, "type": "signup"})
        except AuthApiError as e:
            raise ValueError(f"验证码错误: {e.message}") from e
        if resp.user is None or resp.session is None:
            raise ValueError("验证码无效或已过期")
        return {"temp_token": resp.session.access_token}

    def complete_register(self, temp_token: str, invite_code: str) -> dict:
        if self._sb is None:
            raise RuntimeError("Supabase client required.")

        jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
        if not jwt_secret:
            raise RuntimeError("SUPABASE_JWT_SECRET not set.")
        try:
            payload = jwt.decode(temp_token, jwt_secret, algorithms=[SUPABASE_JWT_ALGORITHM], options={"verify_aud": False})
        except jwt.InvalidTokenError as e:
            raise ValueError("会话已过期，请重新验证邮箱") from e
        auth_user_id = payload["sub"]

        if self._invite_codes is None or not self._invite_codes.is_valid(invite_code):
            raise ValueError("邀请码无效或已过期")

        email_from_payload = payload.get("email", "")
        existing = self._users.get_by_id(auth_user_id)
        if existing is None:
            mycel_id = q.schema_rpc(self._sb, "identity", "next_mycel_id", {}, "auth service").execute().data
            now = time.time()
            display_name = email_from_payload.split("@")[0]

            self._users.create(
                UserRow(
                    id=auth_user_id,
                    type=UserType.HUMAN,
                    display_name=display_name,
                    email=email_from_payload,
                    mycel_id=mycel_id,
                    created_at=now,
                )
            )

            first_agent_info = self._create_initial_agents(auth_user_id, now)
            self._seed_default_recipes(auth_user_id)
        else:
            display_name = existing.display_name
            mycel_id = existing.mycel_id
            self._seed_default_recipes(auth_user_id)
            owned_agents = self._users.list_by_owner_user_id(auth_user_id)
            first_agent_info = None
            if owned_agents:
                agent = owned_agents[0]
                first_agent_info = {"id": agent.id, "name": agent.display_name, "type": agent.type.value, "avatar": agent.avatar}

        if self._invite_codes is not None:
            self._invite_codes.use(invite_code, auth_user_id)

        logger.info("Registered user %s (mycel_id=%s)", email_from_payload, mycel_id)
        return {
            "token": temp_token,
            "user": {"id": auth_user_id, "name": display_name, "mycel_id": mycel_id, "email": email_from_payload, "avatar": None},
            "agent": first_agent_info,
        }

    def login(self, identifier: str, password: str) -> dict:
        auth_client = self._auth_api(self._require_auth_client())

        email = self._resolve_email(identifier)

        from supabase_auth.errors import AuthApiError

        try:
            resp = auth_client.sign_in_with_password({"email": email, "password": password})
        except AuthApiError:
            raise ValueError("邮箱或密码错误")
        if resp.user is None or resp.session is None:
            raise ValueError("邮箱或密码错误")

        auth_user_id = str(resp.user.id)
        token = resp.session.access_token

        user = self._users.get_by_id(auth_user_id)
        if user is None:
            raise ValueError("账号数据异常，请联系支持")
        if self._recipe_repo is not None:
            self._seed_default_recipes(auth_user_id)

        owned_agents = self._users.list_by_owner_user_id(auth_user_id)
        agent_info = None
        if owned_agents:
            a = owned_agents[0]
            agent_info = {"id": a.id, "name": a.display_name, "type": a.type.value, "avatar": a.avatar}

        logger.info("Login: %s (mycel_id=%s)", email, user.mycel_id)
        return {
            "token": token,
            "user": {
                "id": auth_user_id,
                "name": user.display_name,
                "mycel_id": user.mycel_id,
                "email": user.email,
                "avatar": user.avatar,
            },
            "agent": agent_info,
        }

    def verify_token(self, token: str) -> dict:
        jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
        if not jwt_secret:
            raise RuntimeError("SUPABASE_JWT_SECRET env var required for token verification.")
        try:
            payload = jwt.decode(
                token,
                jwt_secret,
                algorithms=[SUPABASE_JWT_ALGORITHM],
                leeway=60,
                options={"verify_aud": False},
            )
            return {"user_id": payload["sub"]}
        except jwt.ExpiredSignatureError:
            raise ValueError("Token 已过期，请重新登录")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Token 无效: {e}")

    def create_external_user_token(self, user_id: str, display_name: str, *, created_by_user_id: str) -> dict:
        external_user_id = user_id.strip()
        external_display_name = display_name.strip()
        if not external_user_id:
            raise ValueError("external user_id is required")
        if not external_display_name:
            raise ValueError("external display_name is required")
        if self._users.get_by_id(external_user_id) is not None:
            raise ExternalUserAlreadyExistsError(f"external user already exists: {external_user_id}")

        jwt_secret = os.getenv("SUPABASE_JWT_SECRET")
        if not jwt_secret:
            raise RuntimeError("SUPABASE_JWT_SECRET env var required for external user token creation.")

        now = time.time()
        self._users.create(
            UserRow(
                id=external_user_id,
                type=UserType.EXTERNAL,
                display_name=external_display_name,
                created_at=now,
            )
        )
        token = jwt.encode(
            {
                "sub": external_user_id,
                "iat": int(now),
                "mycel_user_type": "external",
                "created_by_user_id": created_by_user_id,
            },
            jwt_secret,
            algorithm=SUPABASE_JWT_ALGORITHM,
        )
        return {
            "token": token,
            "user": {"id": external_user_id, "name": external_display_name, "type": "external"},
        }

    def _resolve_email(self, identifier: str) -> str:
        if identifier.strip().lstrip("0123456789") == "" and identifier.strip().isdigit():
            user = self._users.get_by_mycel_id(int(identifier.strip()))
            if user is None or user.email is None:
                raise ValueError("用户不存在")
            return user.email
        return identifier.strip()

    def _require_auth_client(self):
        if self._sb_auth_factory is not None:
            return self._sb_auth_factory()
        if self._sb_auth is None:
            raise RuntimeError("Supabase auth client required. Configure SUPABASE_ANON_KEY for auth runtime.")
        return self._sb_auth

    def _auth_api(self, auth_client):
        return getattr(auth_client, "auth", auth_client)

    def _seed_default_recipes(self, owner_user_id: str) -> None:
        if self._recipe_repo is None:
            raise RuntimeError("Recipe repo required for initial sandbox recipe creation during schema cutover.")
        seed_default_recipes(owner_user_id, recipe_repo=self._recipe_repo)

    def _create_initial_agents(self, owner_user_id: str, now: float) -> dict | None:
        if self._agent_configs is None:
            raise RuntimeError("Agent config repo required for initial agent creation during schema cutover.")
        from pathlib import Path

        from storage.utils import generate_agent_config_id, generate_agent_user_id

        initial_agents = [
            {"name": "Toad", "description": "Curious and energetic assistant", "avatar": "toad.jpeg"},
            {"name": "Morel", "description": "Thoughtful senior analyst", "avatar": "morel.jpeg"},
        ]
        assets_dir = Path(__file__).resolve().parents[3] / "assets"
        first_agent_info = None

        for i, agent_def in enumerate(initial_agents):
            agent_id = generate_agent_user_id()
            agent_config_id = generate_agent_config_id()
            self._users.create(
                UserRow(
                    id=agent_id,
                    type=UserType.AGENT,
                    display_name=agent_def["name"],
                    owner_user_id=owner_user_id,
                    agent_config_id=agent_config_id,
                    created_at=now,
                )
            )
            self._agent_configs.save_agent_config(
                AgentConfig(
                    id=agent_config_id,
                    agent_user_id=agent_id,
                    owner_user_id=owner_user_id,
                    name=agent_def["name"],
                    description=agent_def["description"],
                    status="active",
                    version="1.0.0",
                )
            )
            src_avatar = assets_dir / agent_def["avatar"]
            if not src_avatar.exists():
                raise RuntimeError(f"Default agent avatar missing: {src_avatar}")
            avatar_path = process_and_save_avatar(src_avatar, agent_id)
            # @@@file-backed-avatar-shell - current web avatar truth is the served
            # file surface, not a path string stored in users.avatar.
            ensure_owner_agent_contact(self._contact_repo, owner_user_id, agent_id, now=now)
            if i == 0:
                first_agent_info = {"id": agent_id, "name": agent_def["name"], "type": "agent", "avatar": avatar_path}

        return first_agent_info
