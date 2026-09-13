import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings
from .models import User, UserRole


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
        user = await self.db.scalar(select(User).where(User.rubika_user_id == rubika_user_id))
        if user is None:
            roles = [UserRole.USER.value]
            if rubika_user_id == self.settings.owner_id:
                roles = [UserRole.USER.value, UserRole.OWNER.value]
            user = User(
                rubika_user_id=rubika_user_id,
                username=username,
                display_name=display_name,
                roles_json=json.dumps(roles),
            )
            self.db.add(user)
        else:
            user.username = username or user.username
            user.display_name = display_name or user.display_name
            if rubika_user_id == self.settings.owner_id:
                roles = self.roles(user)
                if UserRole.OWNER.value not in roles:
                    roles.append(UserRole.OWNER.value)
                    user.roles_json = json.dumps(roles)
        await self.db.flush()
        return user

    @staticmethod
    def roles(user: User) -> list[str]:
        try:
            roles = json.loads(user.roles_json or "[]")
        except json.JSONDecodeError:
            roles = []
        return roles

    def has(self, user: User, *allowed: UserRole) -> bool:
        current = set(self.roles(user))
        return any(role.value in current for role in allowed)
