"""Authentication service — register, login, JWT."""

from __future__ import annotations

import logging
import time
import uuid

import bcrypt
import jwt

from storage.contracts import (
    AccountRepo,
    AccountRow,
    MemberRepo,
    MemberRow,
    MemberType,
)
from storage.providers.sqlite.member_repo import generate_member_id

logger = logging.getLogger(__name__)

# @@@jwt-secret - hardcoded for MVP. Move to config/env before production.
JWT_SECRET = "leon-dev-secret-change-me"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = 86400 * 7  # 7 days


class AuthService:
    def __init__(
        self,
        members: MemberRepo,
        accounts: AccountRepo,
    ) -> None:
        self._members = members
        self._accounts = accounts

    def register(self, username: str, password: str) -> dict:
        """Register a new human user.

        Returns: {token, user, agent}
        Creates: human member, account, agent members.
        """
        if self._accounts.get_by_username(username) is not None:
            raise ValueError(f"Username '{username}' already taken")

        now = time.time()

        # @@@non-atomic-register - steps 1-7 are not atomic. Acceptable for dev.
        # Wrap in DB transaction when migrating to Supabase.
        # 1. Human member
        user_id = generate_member_id()
        self._members.create(MemberRow(
            id=user_id, name=username, type=MemberType.HUMAN, created_at=now,
        ))

        # 2. Account (bcrypt hash)
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        account_id = str(uuid.uuid4())
        self._accounts.create(AccountRow(
            id=account_id, user_id=user_id, username=username,
            password_hash=password_hash, created_at=now,
        ))

        # 3. Create two initial agent members: Toad and Morel
        from backend.web.services.member_service import MEMBERS_DIR, _write_agent_md, _write_json
        from pathlib import Path

        # @@@initial-agent-names - keep template names plain; owner disambiguation belongs in discovery UI metadata.
        initial_agents = [
            {"name": "Toad", "description": "Curious and energetic assistant", "avatar": "toad.jpeg"},
            {"name": "Morel", "description": "Thoughtful senior analyst", "avatar": "morel.jpeg"},
        ]

        assets_dir = Path(__file__).resolve().parents[3] / "assets"

        first_agent_info = None
        for i, agent_def in enumerate(initial_agents):
            agent_member_id = generate_member_id()
            agent_dir = MEMBERS_DIR / agent_member_id
            agent_dir.mkdir(parents=True, exist_ok=True)
            _write_agent_md(agent_dir / "agent.md", name=agent_def["name"],
                            description=agent_def["description"])
            _write_json(agent_dir / "meta.json", {
                "status": "active", "version": "1.0.0",
                "created_at": int(now * 1000), "updated_at": int(now * 1000),
            })
            self._members.create(MemberRow(
                id=agent_member_id, name=agent_def["name"], type=MemberType.MYCEL_AGENT,
                description=agent_def["description"],
                config_dir=str(agent_dir),
                owner_user_id=user_id,
                created_at=now,
            ))

            # @@@avatar-same-pipeline — reuse shared PIL pipeline from entities.py
            src_avatar = assets_dir / agent_def["avatar"]
            if src_avatar.exists():
                try:
                    from backend.web.routers.entities import process_and_save_avatar
                    avatar_path = process_and_save_avatar(src_avatar, agent_member_id)
                    self._members.update(agent_member_id, avatar=avatar_path, updated_at=now)
                except Exception as e:
                    logger.warning("Failed to process default avatar for %s: %s", agent_def["name"], e)

            if i == 0:
                first_agent_info = {
                    "id": agent_member_id, "name": agent_def["name"],
                    "type": "mycel_agent", "avatar": None,
                }

            logger.info("Created agent '%s' (member=%s) for user '%s'",
                        agent_def["name"], agent_member_id[:8], username)

        token = self._make_token(user_id)

        logger.info("Registered user '%s' (user=%s)", username, user_id[:8])

        return {
            "token": token,
            "user": {"id": user_id, "name": username, "type": "human", "avatar": None},
            "agent": first_agent_info,
        }

    def login(self, username: str, password: str) -> dict:
        """Login and return JWT + member info."""
        account = self._accounts.get_by_username(username)
        if account is None or account.password_hash is None:
            raise ValueError("Invalid username or password")

        if not bcrypt.checkpw(password.encode(), account.password_hash.encode()):
            raise ValueError("Invalid username or password")

        user = self._members.get_by_id(account.user_id)
        if user is None:
            raise ValueError("Account has no associated user")

        # Find the user's agent
        owned_agents = self._members.list_by_owner_user_id(user.id)
        agent_info = None
        if owned_agents:
            a = owned_agents[0]
            agent_info = {"id": a.id, "name": a.name, "type": a.type.value, "avatar": a.avatar}

        token = self._make_token(user.id)

        return {
            "token": token,
            "user": {"id": user.id, "name": user.name, "type": user.type.value, "avatar": user.avatar},
            "agent": agent_info,
        }

    def verify_token(self, token: str) -> dict:
        """Verify JWT and return payload dict with user_id. Raises ValueError on failure."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return {"user_id": payload["user_id"]}
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")

    def _make_token(self, user_id: str) -> str:
        payload = {"user_id": user_id, "exp": time.time() + JWT_EXPIRE_SECONDS}
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
