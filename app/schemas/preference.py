from pydantic import BaseModel, Field

from app.models.enums import Channel


class ChannelPreference(BaseModel):
    channel: Channel
    enabled: bool


class PreferencesUpdateRequest(BaseModel):
    preferences: list[ChannelPreference] = Field(..., min_length=1)


class PreferencesResponse(BaseModel):
    user_id: str
    preferences: dict[Channel, bool]
