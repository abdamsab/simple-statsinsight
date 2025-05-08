# backend/features/user/auth/service.py

# This file contains the core business logic for user authentication features,
# interacting with the database and handling security-related operations
# that are too complex for dependencies or security primitives alone.

import secrets # For generating secure tokens
from datetime import datetime, timedelta # For handling token expiration
from typing import Optional, Dict, Any, List # For type hinting
from passlib.context import CryptContext # For password hashing

# Import database helpers and getters
from ....db import mongo_client as database # Use your database alias
from ....db.mongo_client import ( # Explicitly import getter functions needed
    get_users_collection,
    get_email_tokens_collection,
    # Import other collections if needed by logic here
)

# Import models
from ....models.auth import ( # Ensure necessary models are imported
    UserCreate,
    UserResponse,
    TokenData,
    PasswordResetRequest, # Needed for type hinting in service functions
    PasswordReset # Needed for type hinting in service functions
)

# Import settings
from ....config.settings import settings


# Password hashing context (assuming this is defined in your security.py or needs definition here)
# If it's defined in security.py and you prefer to use that instance, you would import it.
# For this service file, defining it here or importing a shared instance is fine.
# Let's define it here for now, assuming it might be a standalone utility for this service.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# Helper function to hash passwords (can also be in security.py)
def hash_password(password: str) -> str:
    """Hashes a password using the configured context."""
    return pwd_context.hash(password)

# Helper function to verify passwords (can also be in security.py)
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plain password against a hashed one."""
    return pwd_context.verify(plain_password, hashed_password)


# --- ADDED: Functions for Email Confirmation ---

async def generate_email_confirmation_token(user_id: str) -> Optional[str]:
    """Generates a unique email confirmation token and stores it in the database."""
    email_tokens_collection = get_email_tokens_collection()
    if email_tokens_collection is None:
        print("Error: Email tokens collection not available to generate confirmation token.")
        return None

    # Generate a secure, URL-safe token
    token = secrets.token_urlsafe(32) # Generates a random 32-byte URL-safe string

    # Define token expiration time using settings
    expiration_time = datetime.utcnow() + timedelta(minutes=settings.EMAIL_CONFIRMATION_TOKEN_EXPIRE_MINUTES)

    token_document = {
        "user_id": user_id,
        "token": token,
        "type": "email_confirmation", # Mark the type of token
        "expires_at": expiration_time,
        "created_at": datetime.utcnow(),
        "used": False # Track if the token has been used
    }

    try:
        # Insert the token document into the email_tokens collection
        inserted_id = await database.insert_one(email_tokens_collection, token_document)
        if inserted_id:
            print(f"Generated and stored email confirmation token for user {user_id}")
            return token
        else:
            print(f"Failed to store email confirmation token for user {user_id}")
            return None
    except Exception as e:
        print(f"Error storing email confirmation token for user {user_id}: {e}")
        return None

async def validate_email_confirmation_token(token: str) -> Optional[str]:
    """
    Validates an email confirmation token. If valid, confirms the user's email
    and returns the user_id.
    """
    email_tokens_collection = get_email_tokens_collection()
    users_collection = get_users_collection()

    if email_tokens_collection is None or users_collection is None:
        print("Error: Collections not available to validate email confirmation token.")
        return None

    try:
        # Find the token document
        token_document = await database.find_one(
            email_tokens_collection,
            {"token": token, "type": "email_confirmation", "used": False} # Find unused token of correct type
        )

        if token_document is None:
            print(f"Email confirmation token not found or already used: {token}")
            return None # Token not found or already used

        # Check if the token has expired
        if token_document.get("expires_at") and datetime.utcnow() > token_document["expires_at"]:
            print(f"Email confirmation token has expired: {token}")
            # Optional: Mark as used or remove expired token
            # await database.update_one_by_id(email_tokens_collection, str(token_document["_id"]), {"used": True})
            return None # Token expired

        # If token is valid, get the user ID (it's stored as str)
        user_id = token_document.get("user_id")
        if user_id is None:
            print(f"Error: Email confirmation token {token} is missing user_id.")
            return None # Token document is invalid

        # Update the user's email_confirmed status
        user_updated = await database.update_one_by_id(
            users_collection,
            user_id, # User ID is stored as str in token document
            {"email_confirmed": True}
        )

        if user_updated:
            # Mark the token as used
            # The _id of the token document itself might be ObjectId, convert to str
            token_doc_id = str(token_document.get("_id"))
            await database.update_one_by_id(email_tokens_collection, token_doc_id, {"used": True})
            print(f"Email confirmed for user {user_id} with token {token}")
            return user_id # Return user ID on successful confirmation
        else:
            print(f"Failed to update user {user_id}'s email_confirmed status with token {token}.")
            return None # Failed to update user


    except Exception as e:
        print(f"Error validating email confirmation token {token}: {e}")
        return None

# --- ADDED: Functions for Password Reset ---

async def generate_password_reset_token(email: str) -> Optional[str]:
    """
    Generates a password reset token for the user associated with the email
    and stores it in the database. Returns the token string.
    """
    users_collection = get_users_collection()
    email_tokens_collection = get_email_tokens_collection()

    if users_collection is None or email_tokens_collection is None:
        print("Error: Collections not available to generate password reset token.")
        return None

    try:
        # Find the user by email
        user_document = await database.find_one(users_collection, {"email": email})

        if user_document is None:
            print(f"Password reset requested for non-existent email: {email}")
            # Security consideration: Do NOT reveal if the user exists or not.
            # Return None but frontend should show generic message.
            return None

        user_id = str(user_document.get("_id")) # Get user's ObjectId as string

        # Invalidate any existing password reset tokens for this user (optional but good practice)
        # update_many is synchronous in your mongo_client, wrap it in asyncio.to_thread
        await asyncio.to_thread(
            email_tokens_collection.update_many,
            {"user_id": user_id, "type": "password_reset", "used": False},
            {"$set": {"used": True, "invalidated_at": datetime.utcnow()}}
        )
        print(f"Invalidated old password reset tokens for user {user_id}")


        # Generate a secure, URL-safe token
        token = secrets.token_urlsafe(32)

        # Define token expiration time using settings
        expiration_time = datetime.utcnow() + timedelta(minutes=settings.PASSWORD_RESET_TOKEN_EXPIRE_MINUTES)

        token_document = {
            "user_id": user_id,
            "token": token,
            "type": "password_reset", # Mark the type of token
            "expires_at": expiration_time,
            "created_at": datetime.utcnow(),
            "used": False
        }

        # Insert the new token document
        inserted_id = await database.insert_one(email_tokens_collection, token_document)

        if inserted_id:
            print(f"Generated and stored password reset token for user {user_id}")
            # Important: The actual email sending logic is NOT here.
            # You would typically call a separate function or service to send the email
            # containing the link with this token.
            # Example: send_password_reset_email(email, token)
            # For now, we'll just return the token string, assuming the caller handles email sending.
            return token
        else:
            print(f"Failed to store password reset token for user {user_id}")
            return None


    except Exception as e:
        print(f"Error generating password reset token for email {email}: {e}")
        return None


async def reset_user_password(token: str, new_password: str) -> Optional[str]:
    """
    Validates a password reset token, resets the user's password if valid,
    and returns the user_id on success.
    """
    email_tokens_collection = get_email_tokens_collection()
    users_collection = get_users_collection()

    if email_tokens_collection is None or users_collection is None:
        print("Error: Collections not available to reset password.")
        return None

    try:
        # Find the password reset token document
        token_document = await database.find_one(
            email_tokens_collection,
            {"token": token, "type": "password_reset", "used": False} # Find unused token of correct type
        )

        if token_document is None:
            print(f"Password reset token not found, incorrect type, or already used: {token}")
            return None # Token not found, wrong type, or already used

        # Check if the token has expired
        if token_document.get("expires_at") and datetime.utcnow() > token_document["expires_at"]:
            print(f"Password reset token has expired: {token}")
            # Optional: Mark as used or remove expired token
            # await database.update_one_by_id(email_tokens_collection, str(token_document["_id"]), {"used": True})
            return None # Token expired

        # If token is valid, get the user ID (it's stored as str)
        user_id = token_document.get("user_id")
        if user_id is None:
            print(f"Error: Password reset token {token} is missing user_id.")
            return None # Token document is invalid


        # Hash the new password using the helper function (which uses pwd_context)
        hashed_password = hash_password(new_password) # Use the helper function

        # Update the user's password in the users collection
        user_updated = await database.update_one_by_id(
            users_collection,
            user_id,
            {"hashed_password": hashed_password}
        )

        if user_updated:
            # Mark the password reset token as used
            # The _id of the token document itself might be ObjectId, convert to str
            token_doc_id = str(token_document.get("_id"))
            await database.update_one_by_id(email_tokens_collection, token_doc_id, {"used": True})
             # Optional: Invalidate any *other* unused password reset tokens for this user after one is used
            # update_many is synchronous, wrap in asyncio.to_thread
            await asyncio.to_thread(
                email_tokens_collection.update_many,
                {"user_id": user_id, "type": "password_reset", "used": False},
                {"$set": {"used": True, "invalidated_at": datetime.utcnow()}}
            )

            print(f"Password reset successful for user {user_id} with token {token}")
            return user_id # Return user ID on successful password reset
        else:
            print(f"Failed to update user {user_id}'s password with token {token}.")
            return None # Failed to update user


    except Exception as e:
        print(f"Error resetting password with token {token}: {e}")
        return None