from sqlalchemy.orm import Session

from app.models.enums import Channel
from app.repositories.preference_repository import PreferenceRepository


class PreferenceService:
    def __init__(self, db: Session):
        self.db = db
        self.preference_repo = PreferenceRepository(db)

    def get_preferences(self, user_id: str) -> dict[Channel, bool]:
        return self.preference_repo.get_all_for_user(user_id)

    def set_preferences(self, user_id: str, preferences: dict[Channel, bool]) -> dict[Channel, bool]:
        for channel, enabled in preferences.items():
            self.preference_repo.upsert(user_id, channel, enabled)
        return self.preference_repo.get_all_for_user(user_id)
