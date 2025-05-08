# backend/models/subscription_history.py

# This file defines the Pydantic model for individual Subscription History records
# stored in the 'subscription_history' collection.

import datetime
from typing import Optional, Annotated
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

# --- SubscriptionHistory Model ---
class SubscriptionHistory(BaseModel):
    """
    Represents a single past or current subscription record for a user
    in the MongoDB 'subscription_history' collection.
    """
    id: Optional[PyObjectId] = Field(alias="_id", default=None) # Unique ID for this history record

    user_id: PyObjectId = Field(...) # Reference to the user this history belongs to

    plan: str = Field(...) # The name of the subscription plan (e.g., "monthly", "trial", "annual")

    start_date: datetime.datetime = Field(...) # When this subscription period started

    end_date: datetime.datetime = Field(...) # When this subscription period ended or is scheduled to end

    status: str = Field(...) # Status of this history record (e.g., "active", "expired", "cancelled", "trialing")

    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow) # Timestamp when this history record was created

    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow) # Timestamp when this history record was last updated

    # Pydantic Model Configuration
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_schema_extra": { # Optional: Add example data for OpenAPI docs
            "example": {
                "_id": "65f2a5b1b3727d9c4a7e1a10",
                "user_id": "65f2a5b1b3727d9c4a7e1a0b", # Reference to the user's ID
                "plan": "monthly",
                "start_date": "2024-01-01T00:00:00.000Z",
                "end_date": "2024-02-01T00:00:00.000Z",
                "status": "expired",
                "created_at": "2024-01-01T00:00:00.000Z",
                "updated_at": "2024-02-01T00:00:00.000Z"
            }
        }
    }