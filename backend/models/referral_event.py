# backend/models/referral_event.py 

# This file defines the Pydantic model for individual Referral Event records
# stored in the 'referral_events' collection.

import datetime
from typing import Optional, Annotated, Dict, Any
from pydantic import BaseModel, Field
from pydantic_core import core_schema

from bson import ObjectId

# --- Custom Type for handling MongoDB ObjectId ---
# Allows Pydantic to validate ObjectId or string and serialize to string.
PyObjectId = Annotated[
    ObjectId,
    core_schema.
    no_info_plain_validator_function(str)
]

# --- ReferralEvent Model ---
class ReferralEvent(BaseModel):
    """
    Represents a logged event related to the referral program that might trigger a reward.
    Stored in the MongoDB 'referral_events' collection.
    """
    id: Optional[PyObjectId] = Field(alias="_id", default=None) # Unique ID for this event record

    # The user who referred (the one who should potentially get a reward)
    referrer_user_id: PyObjectId = Field(...)

    # The user who was referred and performed the action (e.g., subscribed)
    referred_user_id: PyObjectId = Field(...)

    # Type of event that occurred (e.g., "referred_registered", "referred_subscribed")
    event_type: str = Field(...)

    # Optional reference to the resource that triggered the event (e.g., the SubscriptionHistory ID)
    triggering_resource_id: Optional[PyObjectId] = Field(default=None)

    # Timestamp when this event record was created/logged
    issued_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)

    # Status of the event/reward processing (e.g., "pending_reward", "reward_issued", "reward_failed", "cancelled")
    status: str = Field(..., default="pending_reward") # Default to pending processing

    # Details of the reward associated with this event (if status is 'reward_issued')
    # This can store details like the reward type ("premium_days"), value (e.g., 30),
    # and maybe the plan type that triggered it (e.g., "monthly").
    reward_details: Optional[Dict[str, Any]] = Field(default=None)

    # Any relevant notes (e.g., reason for cancellation)
    notes: Optional[str] = Field(default=None)


    # Pydantic Model Configuration
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_schema_extra": { # Optional: Add example data for OpenAPI docs
            "example": {
                "_id": "65f2a5b1b3727d9c4a7e1a11",
                "referrer_user_id": "65f2a5b1b3727d9c4a7e1a0d", # User who referred
                "referred_user_id": "65f2a5b1b3727d9c4a7e1a0b", # User who was referred and subscribed
                "event_type": "referred_subscribed",
                "triggering_resource_id": "65f2a5b1b3727d9c4a7e1a10", # ID of the SubscriptionHistory record
                "issued_at": "2024-10-27T10:00:00.000Z",
                "status": "reward_issued",
                "reward_details": { "type": "premium_days", "value": 30, "plan_type": "monthly" },
                "notes": None
            }
        }
    }