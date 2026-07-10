from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.enums import Channel
from app.models.preference import UserPreference

DEFAULT_ENABLED_CHANNELS = {Channel.EMAIL: True, Channel.SMS: True, Channel.PUSH: True}


class PreferenceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_for_user(self, user_id: str) -> dict[Channel, bool]:
        stmt = select(UserPreference).where(UserPreference.user_id == user_id)
        rows = self.db.execute(stmt).scalars().all()
        prefs = dict(DEFAULT_ENABLED_CHANNELS)
        for row in rows:
            prefs[Channel(row.channel)] = row.enabled
        return prefs

    def is_channel_enabled(self, user_id: str, channel: Channel) -> bool:
        row = self.db.get(UserPreference, {"user_id": user_id, "channel": channel})
        if row is None:
            return DEFAULT_ENABLED_CHANNELS.get(channel, True)
        return row.enabled

    def upsert(self, user_id: str, channel: Channel, enabled: bool) -> UserPreference:
        stmt = (
            pg_insert(UserPreference)
            .values(user_id=user_id, channel=channel.value, enabled=enabled)
            .on_conflict_do_update(
                index_elements=["user_id", "channel"],
                set_={"enabled": enabled},
            )
        )
        self.db.execute(stmt)
        self.db.flush()
        return self.db.get(UserPreference, {"user_id": user_id, "channel": channel})
