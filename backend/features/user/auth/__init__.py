# backend/features/user/auth/__init__.py - MODIFIED CODE

# This file makes the 'auth' directory a Python package.
# We will import the security functions and dependencies here for easier access.

# Import the functions from security.py
from .security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_token,
)

# --- New: Import dependencies from dependencies.py ---
from .dependencies import (
    oauth2_scheme,        # The OAuth2PasswordBearer instance
    get_current_user,     # The main JWT verification dependency
    # get_current_active_user, # Optional: If you added the second dependency
)

# Define __all__ if you want to explicitly control what's exported
__all__ = [
    "hash_password",
    "verify_password",
    "create_access_token",
    "verify_token",
    # "TokenData" # Add if needed for export

    # --- New: Export dependencies ---
    "oauth2_scheme",
    "get_current_user",
    # "get_current_active_user", # Optional
]