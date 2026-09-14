import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import User, UserRole

_USERNAME_CACHE: dict[str, str] = {}


def remember_username(user_id: str, username: str) -> None:
    _USERNAME_CACHE[user_id] = username.lstrip("@").strip().lower()


def _normalize_username(username: str | None) -> str:
    return (username or "").lstrip("@").strip().lower()


class RoleService:
    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings

    async def get_or_create_user(
        self,
        *,
        rubika_user_id: str,
        username: str | None = None,
        display_name: str | None = None,
    ) -> User:
        username = _normalize_username(username or _USERNAME_CACHE.get(rubika_user_id)) or None
        user = await self.db.scalar(select(User).where(User.rubika_user_id == rubika_user_id))
        if user is None:
            user = User(
                rubika_user_id=rubika_user_id,
                username=username,
                display_name=display_name,
                roles_json=json.dumps([UserRole.USER.value]),
            )
            self.db.add(user)
        else:
            user.username = username or user.username
            user.display_name = display_name or user.display_name
        await self.db.flush()
        return user

    @staticmethod
    def roles(user: User) -> list[str]:
        try:
            roles = json.loads(user.roles_json or "[]")
        except (json.JSONDecodeError, TypeError):
            roles = []
        return [str(role) for role in roles] if isinstance(roles, list) else []

    def has(self, user: User, *allowed: UserRole) -> bool:
        """Authorize owner/admin by configured username and supervisors by role."""
        allowed_set = set(allowed)
        username = _normalize_username(user.username)

        if UserRole.OWNER in allowed_set and username == _normalize_username(self.settings.owner_username):
            return True
        if UserRole.ADMIN in allowed_set and username == _normalize_username(self.settings.admin_username):
            return True

        current = set(self.roles(user))
        if UserRole.SUPERVISOR in allowed_set and UserRole.SUPERVISOR.value in current:
            return True
        if UserRole.USER in allowed_set and UserRole.USER.value in current:
            return True
        return False
