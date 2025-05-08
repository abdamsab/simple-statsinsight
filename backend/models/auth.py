# backend/models/auth.py - CORRECTED CODE (Final based on user feedback)

# This file defines Pydantic models specifically for authentication
# requests and responses (e.g., registration input, login input/output).

# Import necessary Pydantic components and typing
from pydantic import (
    BaseModel,
    Field,
    EmailStr,
    validator,          # For Pydantic V1 validators
    field_validator,    # For Pydantic V2+ field validators
    ValidationInfo,     # For Pydantic V2+ validator info
)
from typing import Optional, Dict, Any # Import Dict, Any for TokenData payload
import re # Needed for password complexity regex example
import datetime # Needed if you include datetime in TokenData

# --- Request Model for User Registration ---
class UserRegisterRequest(BaseModel):
    """
    Pydantic model for validating incoming user registration data.
    """
    email: EmailStr = Field(..., description="User's email address (must be unique)") # EmailStr provides basic format validation
    username: str = Field(..., min_length=3, max_length=50, description="User's chosen username (must be unique)") # Add length constraints
    password: str = Field(..., min_length=8, description="User's password") # Add min length constraint
    password_confirm: str = Field(..., description="Confirm password")
    referral_code: Optional[str] = Field(default=None, description="Optional referral code")


    # --- Validator to check if password and password_confirm match ---
    # Using Pydantic V2+ field_validator as requested.
    # This validator runs after individual fields are validated.
    @field_validator('password_confirm') # Use field_validator for V2+
    def check_password_match(cls, v: str, info: ValidationInfo) -> str:
        """Ensures password and password_confirm fields match."""
        if 'password' in info.data and v != info.data['password']:
            raise ValueError('Passwords do not match')
        return v

    # --- Optional: Keep V1 style validator commented for reference if needed ---
    # @validator('password_confirm') # Using V1 style for compatibility
    # def passwords_match(cls, v, values, **kwargs):
    #     if 'password' in values and v != values['password']:
    #         raise ValueError('Passwords do not match')
    #     return v

    # --- Optional: Add more complex password validation (e.g., complexity requirements) ---
    # Uncommented as requested
    @validator('password') # Using V1 validator for complexity, adjust if needed for V2+ field_validator approach
    def password_complexity(cls, v):
        """Ensures password meets basic complexity requirements (digit, upper, lower)."""
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain at least one digit')
        if not any(char.isupper() for char in v):
             raise ValueError('Password must contain at least one uppercase letter')
        if not any(char.islower() for char in v):
             raise ValueError('Password must contain at least one lowercase letter')
        # Optional: Add check for special characters if desired
        # if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
        #    raise ValueError('Password must contain at least one special character')
        return v


# --- Request/Response Models for Login, Token, etc. ---
# Uncommented as requested

class UserLoginRequest(BaseModel):
    """
    Pydantic model for validating incoming user login credentials.
    """
    email_or_username: str = Field(..., description="User's email address or username")
    password: str = Field(..., description="User's password")

class Token(BaseModel):
    """
    Pydantic model for the JWT token response after successful login.
    """
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """
    Pydantic model for the data expected within the JWT token payload.
    Includes standard JWT claims and explicit custom claims.
    """
    # Standard JWT 'sub' claim: Subject of the token. We'll store the user's ID here.
    sub: str = Field(..., description="Standard JWT subject claim (user ID as string)")

    # Custom claim for explicit user ID, for clarity in application code.
    user_id: str = Field(..., description="Custom claim for explicit user ID (as string)") # Explicit user_id field

    # Standard JWT 'exp' claim: Expiration Time.
    exp: datetime = Field(..., description="Expiration time of the token (UTC)")

    # Custom claim: User's role, needed for RBAC.
    role: str = Field(..., description="User's role")

    # Optional: Add other standard or custom claims if you encode them (e.g., iat)
    # iat: datetime = Field(..., description="Issued at time (UTC)")

