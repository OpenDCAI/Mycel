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
    EntityRepo,
    EntityRow,
    MemberRepo,
    MemberRow,
    MemberType,
    ThreadRepo,
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
        entities: EntityRepo,
        threads: ThreadRepo,
    ) -> None:
        self._members = members
        self._accounts = accounts
        self._entities = entities
        self._threads = threads

    def register(self, username: str, password: str) -> dict:
        """Register a new human user.

        Creates: human member, account, human entity, agent member, agent entity, thread.
        No contact, no chat (owner↔own agent = bare chat).
        Returns: {token, member, agent, entity_id}
        """
        if self._accounts.get_by_username(username) is not None:
            raise ValueError(f"Username '{username}' already taken")

        now = time.time()

        # @@@non-atomic-register - steps 1-7 are not atomic. Acceptable for dev.
        # Wrap in DB transaction when migrating to Supabase.
        # 1. Human member
        human_member_id = generate_member_id()
        self._members.create(MemberRow(
            id=human_member_id, name=username, type=MemberType.HUMAN, created_at=now,
        ))

        # 2. Account (bcrypt hash)
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        account_id = str(uuid.uuid4())
        self._accounts.create(AccountRow(
            id=account_id, member_id=human_member_id, username=username,
            password_hash=password_hash, created_at=now,
        ))

        # 3. Human entity (entity_id = {member_id}-{seq}, hyphen separator per decision #24)
        human_seq = self._members.increment_entity_seq(human_member_id)
        human_entity_id = f"{human_member_id}-{human_seq}"
        self._entities.create(EntityRow(
            id=human_entity_id, type="human", member_id=human_member_id,
            name=username, thread_id=None, created_at=now,
        ))

        # 4. Create two initial agent members: Toad and Morel
        from backend.web.services.member_service import MEMBERS_DIR, _write_agent_md, _write_json
        from pathlib import Path

        # @@@initial-agents - Toad (lightweight assistant) + Morel (senior analyst)
        initial_agents = [
            {"name": f"Toad of {username}", "description": "Curious and energetic assistant", "avatar": "toad.jpeg"},
            {"name": f"Morel of {username}", "description": "Thoughtful senior analyst", "avatar": "morel.jpeg"},
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
                owner_id=human_member_id,
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

            # 5. Agent entity + thread
            agent_seq = self._members.increment_entity_seq(agent_member_id)
            agent_entity_id = f"{agent_member_id}-{agent_seq}"
            sandbox_type = "local"

            self._threads.create(
                thread_id=agent_entity_id,
                member_id=agent_member_id,
                sandbox_type=sandbox_type,
                created_at=now,
            )

            entity_name = f"{agent_def['name']}-{agent_seq} ({sandbox_type})"
            self._entities.create(EntityRow(
                id=agent_entity_id, type="agent", member_id=agent_member_id,
                name=entity_name, thread_id=agent_entity_id,
                created_at=now,
            ))

            if i == 0:
                first_agent_info = {
                    "id": agent_member_id, "name": agent_def["name"],
                    "type": "mycel_agent", "avatar": None,
                }

            logger.info("Created agent '%s' (member=%s) for user '%s'",
                        agent_def["name"], agent_member_id[:8], username)

        # JWT — carries both member_id and entity_id
        token = self._make_token(human_member_id, human_entity_id)

        logger.info("Registered user '%s' (member=%s)", username, human_member_id[:8])

        return {
            "token": token,
            "member": {"id": human_member_id, "name": username, "type": "human", "avatar": None},
            "agent": first_agent_info,
            "entity_id": human_entity_id,
        }

    def login(self, username: str, password: str) -> dict:
        """Login and return JWT + member info."""
        account = self._accounts.get_by_username(username)
        if account is None or account.password_hash is None:
            raise ValueError("Invalid username or password")

        if not bcrypt.checkpw(password.encode(), account.password_hash.encode()):
            raise ValueError("Invalid username or password")

        member = self._members.get_by_id(account.member_id)
        if member is None:
            raise ValueError("Account has no associated member")

        # Find the user's agent
        owned_agents = self._members.list_by_owner(member.id)
        agent_info = None
        if owned_agents:
            a = owned_agents[0]
            agent_info = {"id": a.id, "name": a.name, "type": a.type.value, "avatar": a.avatar}

        # Look up human entity
        entities = self._entities.get_by_member_id(member.id)
        human_entity = next((e for e in entities if e.type == "human"), None)

        token = self._make_token(member.id, human_entity.id if human_entity else None)

        return {
            "token": token,
            "member": {"id": member.id, "name": member.name, "type": member.type.value, "avatar": member.avatar},
            "agent": agent_info,
            "entity_id": human_entity.id if human_entity else None,
        }

    def verify_token(self, token: str) -> dict:
        """Verify JWT and return payload dict with member_id + entity_id. Raises ValueError on failure."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return {"member_id": payload["member_id"], "entity_id": payload.get("entity_id")}
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")

    def _make_token(self, member_id: str, entity_id: str | None = None) -> str:
        payload = {"member_id": member_id, "exp": time.time() + JWT_EXPIRE_SECONDS}
        if entity_id:
            payload["entity_id"] = entity_id
        return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
