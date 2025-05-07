# backend/models/__init__.py

# This file makes the 'models' directory a Python package
# and is used to manage imports from this package.

# Import models here that you want to be directly available
# when someone imports the 'backend.models' package.

# Example: from .user import User
from .user import User # Import the User model

# Define __all__ if you want to explicitly control what's exported
# __all__ = ["User"]