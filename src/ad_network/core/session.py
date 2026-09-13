import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import BotSession


class SessionState:
    def __init__(self, db: AsyncSession, user_id: str, bot_name: str):
        self.db = db
        self.user_id = user_id
        self.bot_name = bot_name

    async def load(self) -> BotSession:
        row = await self.db.scalar(
            select(BotSession).where(
                BotSession.rubika_user_id == self.user_id,
                BotSession.bot_name == self.bot_name,
            )
        )
        if row is None:
            row = BotSession(rubika_user_id=self.user_id, bot_name=self.bot_name)
            self.db.add(row)
            await self.db.flush()
        return row

    async def set(self, state: str, data: dict | None = None) -> BotSession:
        row = await self.load()
        row.state = state
        row.data_json = json.dumps(data or {}, ensure_ascii=False)
        await self.db.flush()
        return row

    @staticmethod
    def data(row: BotSession) -> dict:
        try:
            return json.loads(row.data_json or "{}")
        except json.JSONDecodeError:
            return {}
