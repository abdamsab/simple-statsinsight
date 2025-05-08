# backend/models/__init__.py - MODIFIED CODE

# This file makes the 'models' directory a Python package
# and is used to manage imports from this package.

# Import models here that you want to be directly available
# when someone imports the 'backend.models' package.

from .user import User
from .email_token import EmailToken
from .subscription_history import SubscriptionHistory
from .referral_event import ReferralEvent               # Import the ReferralEvent model

# Define __all__ if you want to explicitly control what's exported
__all__ = [
    "User",
    "EmailToken",
    "SubscriptionHistory",
    "ReferralEvent" # Add ReferralEvent to export
]