from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite+aiosqlite:///./rubika.db"

    user_bot_token: str = ""
    admin_bot_token: str = ""
    owner_bot_token: str = ""

    owner_id: str = ""
    owner_username: str = ""
    log_level: str = "INFO"

    # Operational Rubika user-bot sessions. On Railway this should point to a
    # mounted persistent Volume, for example /data/sessions.
    rubika_session_dir: str = "./sessions"
    list_account_sync_seconds: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
