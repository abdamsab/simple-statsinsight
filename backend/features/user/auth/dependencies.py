# backend/features/user/auth/dependencies.py - NEW FILE

# This file contains FastAPI dependency functions for authentication and authorization.

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from typing import Optional # Keep Optional import if needed elsewhere, though not strictly for TokenData fields now
import traceback 

# Import security utilities
from .security import verify_token # Import the token verification function

# Import the TokenData model
from ....models.auth import TokenData # Import the Pydantic model for the token payload


# --- OAuth2PasswordBearer setup ---
# This class provides a "dependency" that will look for the Authorization: Bearer header
# and extract the token. It also integrates with the OpenAPI docs (/docs).
# The tokenUrl parameter is used by the docs to indicate where to get a token.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login") # Point this to your login endpoint


# --- Dependency to get the current user from the JWT token ---
# This function will be used as a dependency in path operations that require authentication.
async def get_current_user(token: str = Depends(oauth2_scheme)) -> TokenData:
    """
    FastAPI dependency to get the current user from the JWT token in the Authorization header.

    Args:
        token: The JWT token string extracted by OAuth2PasswordBearer.

    Returns:
        A TokenData object containing the validated token payload.

    Raises:
        HTTPException: If the token is invalid, expired, or the payload is incorrect.
    """
    # print(f"Attempting to verify token: {token[:10]}...") # Optional: Log start of verification

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"}, # Standard header for Bearer auth challenges
    )

    # Verify the token using the utility function from security.py
    payload = verify_token(token) # Call the synchronous verify_token utility

    if payload is None:
        print("Token verification failed (invalid signature or expired).")
        raise credentials_exception # Raise exception if token is invalid or expired

    # Validate the payload against the TokenData model
    try:
        # TokenData expects fields like 'sub', 'user_id', 'role', 'exp'
        # Pydantic handles parsing and validation here.
        token_data = TokenData(**payload)
        # print(f"Token payload validated for user_id: {token_data.user_id}") # Optional: Log success

        # Optional: Add more checks here if needed (e.g., user is active in DB)
        # Although typically getting the user from the DB based on token_data.user_id
        # happens in a *subsequent* dependency if you need the full user document,
        # this dependency just validates the token and payload structure.

    except Exception as e:
        print(f"Error validating token payload against TokenData model: {e}")
        traceback.print_exc() # Print traceback for debugging payload issues
        raise credentials_exception # Raise exception if payload doesn't match TokenData model

    # If verification and validation succeed, return the TokenData object
    return token_data

# --- Optional: Dependency to get the full user document from the database ---
# You might need this in endpoints to get more user details than just in the token.
# This dependency *depends* on get_current_user first.
# async def get_current_active_user(current_token_data: TokenData = Depends(get_current_user)):
#     users_collection = get_collection_or_raise_503(get_users_collection) # Need db getter here
#     user_id = current_token_data.user_id
#     if user_id is None:
#         raise HTTPException(status_code=400, detail="Token does not contain user ID") # Should be caught by TokenData model validation
#     # Assuming database.find_one_by_id exists and is async
#     user_document = await database.find_one_by_id(users_collection, user_id)
#     if user_document is None:
#         # User might have been deleted after token was issued
#         raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
#     # Optional: Check if user is active or disabled
#     # if user_document.get("disabled", False):
#     #    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
#     # Assuming User model can parse the DB document including ObjectId
#     return User(**user_document) # Return the full User model

# Note: get_current_active_user is a common pattern, but let's stick to the core token verification (get_current_user) for this step as planned.