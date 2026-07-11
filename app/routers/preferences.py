from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.dependencies import require_api_key
from app.schemas.preference import PreferencesResponse, PreferencesUpdateRequest
from app.services.preference_service import PreferenceService

router = APIRouter(tags=["preferences"], dependencies=[Depends(require_api_key)])


@router.get("/users/{user_id}/preferences", response_model=PreferencesResponse)
def get_preferences(user_id: str, db: Session = Depends(get_db)):
    service = PreferenceService(db)
    preferences = service.get_preferences(user_id)
    return PreferencesResponse(user_id=user_id, preferences=preferences)


@router.post("/users/{user_id}/preferences", response_model=PreferencesResponse)
def set_preferences(user_id: str, request: PreferencesUpdateRequest, db: Session = Depends(get_db)):
    service = PreferenceService(db)
    preferences_map = {item.channel: item.enabled for item in request.preferences}
    updated = service.set_preferences(user_id, preferences_map)
    db.commit()
    return PreferencesResponse(user_id=user_id, preferences=updated)
