# backend/models/user.py 

# This file defines the Pydantic model for the User document
# based on the technical design document's schema for the 'users' collection,
# with subscription and token fields moved to separate collections as per the final design.
# Referral linkage fields remain on the User model.

import datetime
from typing import Optional, List, Dict, Any, Annotated
from pydantic import BaseModel, Field
from pydantic_core import core_schema

from bson import ObjectId

# --- Custom Type for handling MongoDB ObjectId ---
# This allows Pydantic to validate an ObjectId or a string that can be
# converted to an ObjectId, and ensures it's represented as a string when exported (e.g., to JSON).
PyObjectId = Annotated[
    ObjectId,
    core_schema.
    no_info_plain_validator_function(str)
]



# --- User Model ---
class User(BaseModel):
    """
    Represents a user document in the MongoDB 'users' collection.
    Does NOT contain subscription or token fields, which are in separate collections.
    Includes core user info and referral linkage fields.
    """
    id: Optional[PyObjectId] = Field(alias="_id", default=None)

    email: str = Field(..., unique=True, index=True)
    password_hash: str = Field(...)
    username: str = Field(..., unique=True, index=True)
    role: str = Field(..., index=True, default='free') # e.g., "admin", "free", "premium" - Kept on User as access level
    registration_date: datetime.datetime = Field(default_factory=datetime.datetime.utcnow) # Auto-set on creation
    last_login: Optional[datetime.datetime] = Field(default=None)
    email_confirmed: bool = Field(default=False)
    favorite_teams: List[str] = Field(default_factory=list)
    favorite_leagues: List[str] = Field(default_factory=list)
    notification_preferences: Dict[str, Any] = Field(default_factory=dict)
    prediction_history: List[Dict[str, Any]] = Field(default_factory=list) # This remains as per design
    referral_code: Optional[str] = Field(default=None, unique=True, index=True)
    referred_by: Optional[PyObjectId] = Field(alias="referred_by", default=None, index=True)
    referral_rewards_earned: float = Field(default=0.0) # Kept on User as cached total

    # Pydantic Model Configuration
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_schema_extra": { # Optional: Add example data for OpenAPI docs
            "example": {
                "_id": "65f2a5b1b3727d9c4a7e1a0b", # Example ObjectId string
                "email": "user@example.com",
                "password_hash": "hashedpasswordstring...",
                "username": "example_user",
                "role": "free", # Status and plan are in subscription_history
                "registration_date": "2023-01-01T10:00:00.000Z",
                "last_login": "2023-10-27T15:30:00.000Z",
                "email_confirmed": True,
                "favorite_teams": ["Arsenal", "Barcelona"],
                "favorite_leagues": ["Premier League", "La Liga"],
                "notification_preferences": {"alerts_on_favorites": True, "newsletter_opt_in": False},
                "prediction_history": [
                     {"match_id": "65f2a5b1b3727d9c4a7e1a0c", "access_timestamp": "2023-10-27T16:00:00.000Z"}
                ],
                "referral_code": "USER123ABC",
                "referred_by": None, # Or "65f2a5b1b3727d9c4a7e1a0d" for a referring user's ID
                "referral_rewards_earned": 0.0
            }
        }
    }