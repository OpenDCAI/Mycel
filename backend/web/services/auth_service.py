"""Authentication service — register, login, JWT."""

from __future__ import annotations

import logging
import time
import uuid

import bcrypt
import jwt

from storage.contracts import (
    AccountRow,
    ConversationMemberRow,
    ConversationRow,
    MemberRow,
    MemberType,
)
from storage.providers.sqlite.contact_repo import SQLiteContactRepo
from storage.providers.sqlite.conversation_repo import (
    SQLiteConversationMemberRepo,
    SQLiteConversationRepo,
)
from storage.providers.sqlite.member_repo import SQLiteAccountRepo, SQLiteMemberRepo

logger = logging.getLogger(__name__)

# @@@jwt-secret - hardcoded for MVP. Move to config/env before production.
JWT_SECRET = "leon-dev-secret-change-me"
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_SECONDS = 86400 * 7  # 7 days

# @@@template-path - shared Leon agent config directory for all users' default agent.
# Points to the existing __leon__ member dir, or falls back to None (no config_dir).
LEON_TEMPLATE_DIR = str(((__import__("pathlib").Path.home() / ".leon" / "members" / "__leon__")).resolve())


class AuthService:
    def __init__(
        self,
        members: SQLiteMemberRepo,
        accounts: SQLiteAccountRepo,
        contacts: SQLiteContactRepo,
        conversations: SQLiteConversationRepo,
        conv_members: SQLiteConversationMemberRepo,
    ) -> None:
        self._members = members
        self._accounts = accounts
        self._contacts = contacts
        self._conversations = conversations
        self._conv_members = conv_members

    def register(self, username: str, password: str) -> dict:
        """Register a new human user.

        Creates: human member, account, agent member (Leon), contact pair, conversation.
        Returns: {token, member, agent, conversation_id}
        """
        if self._accounts.get_by_username(username) is not None:
            raise ValueError(f"Username '{username}' already taken")

        now = time.time()

        # 1. Human member
        human_id = str(uuid.uuid4())
        self._members.create(MemberRow(
            id=human_id, name=username, type=MemberType.HUMAN, created_at=now,
        ))

        # 2. Account (bcrypt hash)
        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
        account_id = str(uuid.uuid4())
        self._accounts.create(AccountRow(
            id=account_id, member_id=human_id, username=username,
            password_hash=password_hash, created_at=now,
        ))

        # 3. Agent member (Leon from template)
        agent_id = str(uuid.uuid4())
        self._members.create(MemberRow(
            id=agent_id, name="Leon", type=MemberType.MYCEL_AGENT,
            description="Your AI assistant",
            config_dir=LEON_TEMPLATE_DIR,
            created_at=now,
        ))

        # 4. Contact pair (human ↔ agent)
        self._contacts.create_pair(human_id, agent_id, now)

        # 5. Conversation
        conv_id = str(uuid.uuid4())
        self._conversations.create(ConversationRow(
            id=conv_id, agent_member_id=agent_id,
            title="Chat with Leon", created_at=now,
        ))
        self._conv_members.add_member(conv_id, human_id, now)
        self._conv_members.add_member(conv_id, agent_id, now)

        # 6. JWT
        token = self._make_token(human_id)

        logger.info("Registered user '%s' (member=%s, agent=%s)", username, human_id[:8], agent_id[:8])

        return {
            "token": token,
            "member": {"id": human_id, "name": username, "type": "human"},
            "agent": {"id": agent_id, "name": "Leon", "type": "mycel_agent"},
            "conversation_id": conv_id,
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

        # Find the user's agent and conversation
        conv_ids = self._conv_members.list_conversations_for_member(member.id)
        conversation_id = conv_ids[0] if conv_ids else None

        # Find agent member (contact who is mycel_agent)
        contacts = self._contacts.list_by_owner(member.id)
        agent_info = None
        for c in contacts:
            agent_member = self._members.get_by_id(c.contact_id)
            if agent_member and agent_member.type == MemberType.MYCEL_AGENT:
                agent_info = {"id": agent_member.id, "name": agent_member.name, "type": "mycel_agent"}
                break

        token = self._make_token(member.id)

        return {
            "token": token,
            "member": {"id": member.id, "name": member.name, "type": member.type.value},
            "agent": agent_info,
            "conversation_id": conversation_id,
        }

    def verify_token(self, token: str) -> str:
        """Verify JWT and return member_id. Raises ValueError on failure."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload["member_id"]
        except jwt.ExpiredSignatureError:
            raise ValueError("Token expired")
        except jwt.InvalidTokenError:
            raise ValueError("Invalid token")

    def _make_token(self, member_id: str) -> str:
        return jwt.encode(
            {"member_id": member_id, "exp": time.time() + JWT_EXPIRE_SECONDS},
            JWT_SECRET,
            algorithm=JWT_ALGORITHM,
        )
