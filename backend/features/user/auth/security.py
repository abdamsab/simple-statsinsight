# backend/features/user/auth/security.py

# This file contains core security utilities for password hashing and JWT token management.

import os # Needed potentially if not using settings for secret key directly (but we will use settings)
from datetime import datetime, timedelta, timezone # For managing token expiry
from typing import Optional, Dict, Any

# Import password hashing library
from passlib.context import CryptContext

# Import JWT library
from jose import jwt, JWTError

# Import settings to get SECRET_KEY and ALGORITHM
from ....config.settings import settings # Adjust import depth if needed

# --- Password Hashing Setup ---
# Configure passlib to use bcrypt for password hashing.
# 'deprecated="auto"' allows passlib to handle verification of older hash types if needed in the future.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- Password Hashing Functions ---
def hash_password(password: str) -> str:
    """Hashes a plain text password using bcrypt."""
    # Passlib handles salting automatically with bcrypt
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain text password against a bcrypt hash."""
    # Passlib handles salt extraction and verification automatically
    return pwd_context.verify(plain_password, hashed_password)

# --- JWT Token Setup ---
# Get SECRET_KEY and ALGORITHM from settings
# IMPORTANT: Ensure settings.SECRET_KEY and settings.ALGORITHM are loaded correctly
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM
# ACCESS_TOKEN_EXPIRE_MINUTES can also come from settings if you want it configurable
# ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES # Example

# --- JWT Token Functions ---
def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Creates a new JWT access token.
    Args:
        data: The payload data to encode in the token (e.g., {"sub": user_email, "user_id": user_db_id}).
        expires_delta: Optional timedelta for token expiration. If None, a default expiration is used.
    Returns:
        An encoded JWT string.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Default expiration (e.g., 30 minutes) - should be configurable via settings
        # Using a placeholder value here, ideally get this from settings
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES) # Assuming ACCESS_TOKEN_EXPIRE_MINUTES is in settings


    to_encode.update({"exp": expire}) # Add expiration claim to the payload

    # Encode the payload into a JWT using the SECRET_KEY and ALGORITHM
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return encoded_jwt


def verify_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies a JWT token and returns the payload if valid.
    Args:
        token: The JWT string received from the client.
    Returns:
        The decoded payload dictionary if the token is valid and not expired, otherwise None.
    """
    try:
        # Decode and verify the token using the SECRET_KEY and ALGORITHM
        # The 'algorithms' list must match the algorithm used for encoding
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        # Optional: You can add checks here for specific claims like 'sub' or 'user_id'
        # if needed before returning the payload.
        # For example, ensure 'sub' claim exists:
        # username: str = payload.get("sub")
        # if username is None:
        #     return None # Token invalid or missing subject claim

        return payload

    except JWTError:
        # Catch JWT errors (invalid signature, expired token, etc.)
        # print(f"JWT verification failed: {e}") # Optional logging
        return None # Return None if token is invalid or expired

    except Exception as e:
        # Catch any other unexpected errors during processing
        # print(f"An unexpected error occurred during token verification: {e}") # Optional logging
        return None


# --- You might want a Pydantic model for the token payload later ---
# from pydantic import BaseModel
# class TokenData(BaseModel):
#     email: str | None = None # Or user ID, whatever identifies the user
#     # Add other claims you expect in the token payload (e.g., role, user_id)
#     user_id: Optional[str] = None # Example for user ID
#     role: Optional[str] = None # Example for role