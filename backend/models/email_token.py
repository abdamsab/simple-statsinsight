# backend/models/email_token.py - NEW FILE

# This file defines the Pydantic model for the Email Token document
# stored in the MongoDB 'email_tokens' collection.

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

# --- EmailToken Model ---
class EmailToken(BaseModel):
    """
    Represents an email confirmation or password reset token document
    in the MongoDB 'email_tokens' collection.
    """
    id: Optional[PyObjectId] = Field(alias="_id", default=None) # Unique ID for the token document

    user_id: PyObjectId = Field(...) # Reference to the user this token belongs to

    token: str = Field(..., unique=True, index=True) # The token string itself (unique and indexed)

    # Type of token: 'email_confirmation' or 'password_reset'
    type: str = Field(..., index=True)

    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow) # Timestamp when the token was created

    expires_at: datetime.datetime = Field(...) # Timestamp when the token expires

    used: bool = Field(default=False) # Flag indicating if the token has been used

    # Pydantic Model Configuration
    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "json_schema_extra": { # Optional: Add example data for OpenAPI docs
            "example": {
                "_id": "65f2a5b1b3727d9c4a7e1a0f",
                "user_id": "65f2a5b1b3727d9c4a7e1a0b", # Reference to a user's ID
                "token": "a_unique_long_token_string_here",
                "type": "email_confirmation",
                "created_at": "2024-10-27T10:00:00.000Z",
                "expires_at": "2024-10-27T11:00:00.000Z", # Expires 1 hour after creation
                "used": False
            }
        }
    }