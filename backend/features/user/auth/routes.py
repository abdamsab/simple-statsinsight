# backend/features/user/auth/routes.py - UPDATED CODE (Includes /protected_test endpoint)

# This file defines FastAPI API endpoints specific to user authentication (registration, login, etc.).

from fastapi import APIRouter, HTTPException, status, Depends, Request # Import Request and Depends
from pymongo.collection import Collection
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone # For managing time
import secrets # For generating token strings
import traceback # Import traceback for detailed error logging
from bson import ObjectId # Import ObjectId to handle MongoDB IDs

# Import database module and getters from Step 3.1
from ....db import mongo_client as database
from ....db.mongo_client import ( # Explicitly import getter functions
    get_users_collection,
    get_subscription_history_collection,
    get_email_tokens_collection,
    get_parameters_collection,
    get_referral_events_collection,
)

# Import Pydantic models from Step 3.1 (data models)
from ....models.user import User
from ....models.subscription_history import SubscriptionHistory
from ....models.email_token import EmailToken
from ....models.referral_event import ReferralEvent

# Import Pydantic models for request/response from this step (3.3/3.4)
from ....models.auth import (
    UserRegisterRequest, # For validating registration input
    UserLoginRequest,    # For validating login input
    Token,               # For login response (JWT token)
    TokenData            # For defining JWT payload structure
)


# Import security utilities from Step 3.2
from .security import (
    hash_password,
    verify_password,
    create_access_token,
    verify_token, # Make sure verify_token is imported
)

# Import dependencies from Step 3.5
from .dependencies import get_current_user # Import the dependency function

# Import settings
from ....config.settings import settings


# --- Define API Router for this feature ---
router = APIRouter(
    prefix="/api/auth",             # Use the /api/auth prefix
    tags=["auth"]                   # Optional: Add tags for OpenAPI documentation
)

# --- Helper function to get collections (handles None case) ---
def get_collection_or_raise_503(collection_getter) -> Collection:
    """Calls a collection getter function and raises 503 if the collection is None."""
    collection = collection_getter()
    if collection is None:
        print(f"Error: Database collection not accessible via {collection_getter.__name__}.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is not available."
        )
    return collection


# --- Endpoint to Handle User Registration (/api/auth/register) ---
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(request_data: UserRegisterRequest):
    """
    Registers a new user, sets up trial, generates email confirmation token,
    and handles optional referral code.
    """
    print(f"Registration request received for email: {request_data.email}")

    users_collection = get_collection_or_raise_503(get_users_collection)
    subscription_history_collection = get_collection_or_raise_503(get_subscription_history_collection)
    email_tokens_collection = get_collection_or_raise_503(get_email_tokens_collection)
    parameters_collection = get_collection_or_raise_503(get_parameters_collection)
    referral_events_collection = get_collection_or_raise_503(get_referral_events_collection)

    if request_data.password != request_data.password_confirm:
        print("Password and password confirmation do not match.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password and password confirmation do not match."
        )

    try:
        existing_user = await database.find_one(users_collection, {
            "$or": [
                {"email": request_data.email},
                {"username": request_data.username}
            ]
        })

        if existing_user:
            print(f"User already exists with email {request_data.email} or username {request_data.username}.")
            if existing_user.get("email") == request_data.email:
                 detail_message = "User with this email already exists."
            else:
                 detail_message = "User with this username already exists."

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=detail_message
            )

    except Exception as e:
        print(f"Error checking for existing user: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during user check: {e}"
        )

    hashed_password = hash_password(request_data.password)
    print("Password hashed successfully.")

    referred_by_user_id = None
    initial_referral_event_id = None
    referrer_user_doc = None

    if request_data.referral_code:
        print(f"Referral code provided: {request_data.referral_code}")
        try:
            referrer_user_doc = await database.find_one(users_collection, {'referral_code': request_data.referral_code})

            if referrer_user_doc:
                referred_by_user_id = referrer_user_doc.get("_id")
                print(f"Referrer found with ID: {referred_by_user_id}")

                initial_referral_event_data = ReferralEvent(
                    referrer_user_id=referred_by_user_id,
                    event_type='referred_registered',
                    issued_at=datetime.utcnow(),
                    status='pending',
                    notes=f"User {request_data.username} registered using referral code {request_data.referral_code}. Pending subscription for reward."
                ).model_dump(by_alias=True, exclude_none=True)

                insert_result = await database.insert_one(referral_events_collection, initial_referral_event_data)
                if insert_result:
                    initial_referral_event_id = insert_result
                    print(f"Initial referral event logged with ID: {initial_referral_event_id}")
                else:
                    print("Warning: Failed to log initial referral event.")

            else:
                print(f"Warning: Referral code {request_data.referral_code} not found.")

        except Exception as e:
            print(f"Error handling referral code {request_data.referral_code}: {e}")
            traceback.print_exc()
            referred_by_user_id = None

    user_data = {
        "email": request_data.email,
        "password_hash": hashed_password,
        "username": request_data.username,
        "role": "free",
        "registration_date": datetime.utcnow(),
        "last_login": None,
        "email_confirmed": False,
        "favorite_teams": [],
        "favorite_leagues": [],
        "notification_preferences": {},
        "prediction_history": [],
        "referral_code": secrets.token_hex(8).upper(),
        "referred_by": referred_by_user_id,
        "referral_rewards_earned": 0.0,
    }

    try:
        new_user_document = User(**user_data).model_dump(by_alias=True, exclude_none=True)
        print("New user document data prepared.")

    except Exception as e:
         print(f"Error creating User Pydantic model: {e}")
         traceback.print_exc()
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred preparing user data: {e}"
         )

    try:
        insert_result = await database.insert_one(users_collection, new_user_document)

        if not insert_result:
            print("Error inserting new user into database.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user account."
            )

        new_user_id = insert_result

        print(f"New user inserted successfully with ID: {new_user_id}")

    except Exception as e:
         print(f"Error inserting new user: {e}")
         traceback.print_exc()
         raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred inserting user: {e}"
         )

    if initial_referral_event_id and new_user_id:
        try:
            update_success = await database.update_one_by_id(
                referral_events_collection,
                str(initial_referral_event_id),
                {"referred_user_id": new_user_id}
            )
            if update_success:
                 print(f"Updated initial referral event {initial_referral_event_id} with referred_user_id {new_user_id}.")
            else:
                 print(f"Warning: Failed to update initial referral event {initial_referral_event_id} with referred_user_id {new_user_id}.")

        except Exception as e:
             print(f"Error updating initial referral event {initial_referral_event_id}: {e}")
             traceback.print_exc()

    initial_user_role = "free"
    try:
        parameters_collection = get_collection_or_raise_503(get_parameters_collection)
        parameters_doc = await database.find_one(parameters_collection, {})

        new_user_trial_days = settings.DEFAULT_NEW_USER_TRIAL_DAYS

        if parameters_doc and 'new_user_trial_days' in parameters_doc and isinstance(parameters_doc['new_user_trial_days'], int) and parameters_doc['new_user_trial_days'] > 0:
             new_user_trial_days = parameters_doc['new_user_trial_days']
             print(f"Fetched new_user_trial_days from parameters: {new_user_trial_days}")
        else:
             if settings.DEFAULT_NEW_USER_TRIAL_DAYS > 0:
                  new_user_trial_days = settings.DEFAULT_NEW_USER_TRIAL_DAYS
                  print(f"Warning: 'new_user_trial_days' not found or invalid in parameters. Using default from settings: {new_user_trial_days}")
             else:
                  new_user_trial_days = 0
                  print("Info: No trial period granted as configured via parameters or settings.")

        if new_user_trial_days > 0:
            trial_start_date = datetime.utcnow()
            trial_end_date = trial_start_date + timedelta(days=new_user_trial_days)

            trial_history_data = {
                "user_id": new_user_id,
                "plan": "trial",
                "start_date": trial_start_date,
                "end_date": trial_end_date,
                "status": "trialing",
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }

            try:
                trial_history_document = SubscriptionHistory(**trial_history_data).model_dump(by_alias=True, exclude_none=True)
                print("Trial history document data prepared.")
            except Exception as e:
                 print(f"Error creating SubscriptionHistory Pydantic model: {e}")
                 traceback.print_exc()

            insert_result = await database.insert_one(subscription_history_collection, trial_history_document)

            if not insert_result:
                 print("Warning: Failed to insert trial subscription history.")
            else:
                 print(f"Trial subscription history inserted for user {new_user_id} ending on {trial_end_date}.")
                 initial_user_role = "trialing"
                 print(f"Setting initial role to 'trialing' for user {new_user_id}.")

                 update_role_success = await database.update_one_by_id(
                     users_collection,
                     str(new_user_id),
                     {"role": initial_user_role}
                 )
                 if update_role_success:
                     print(f"User role updated to '{initial_user_role}' in database.")
                 else:
                     print(f"Error: Failed to update user role to '{initial_user_role}' in database after trial setup.")

    except Exception as e:
         print(f"Error during trial period setup or role update for user {new_user_id}: {e}")
         traceback.print_exc()

    try:
        token_string = secrets.token_urlsafe(32)
        email_token_expire_hours = settings.EMAIL_CONFIRM_TOKEN_EXPIRE_HOURS
        token_created_at = datetime.utcnow()
        token_expires_at = token_created_at + timedelta(hours=email_token_expire_hours)

        email_token_data = {
            "user_id": new_user_id,
            "token": token_string,
            "type": "email_confirmation",
            "created_at": token_created_at,
            "expires_at": token_expires_at,
            "used": False,
        }

        try:
            email_token_document = EmailToken(**email_token_data).model_dump(by_alias=True, exclude_none=True)
            print("Email token document data prepared.")
        except Exception as e:
             print(f"Error creating EmailToken Pydantic model: {e}")
             traceback.print_exc()

        insert_result = await database.insert_one(email_tokens_collection, email_token_document)

        if not insert_result:
            print("Warning: Failed to insert email confirmation token.")

        print(f"Email confirmation token generated and saved for user {new_user_id}.")

    except Exception as e:
         print(f"Error generating/saving email confirmation token for user {new_user_id}: {e}")
         traceback.print_exc()

    return {"message": "User registered successfully. Please confirm your email address.", "user_id": str(new_user_id), "initial_role": initial_user_role}


# --- Endpoint to Handle User Login (/api/auth/login) ---
@router.post("/login", response_model=Token)
async def login_for_access_token(request_data: UserLoginRequest):
    """
    Authenticates a user using email/username and password, returns a JWT access token.
    Checks and updates user role based on subscription status upon successful login.
    """
    print(f"Login request received for user: {request_data.email_or_username}")

    users_collection = get_collection_or_raise_503(get_users_collection)
    subscription_history_collection = get_collection_or_raise_503(get_subscription_history_collection)

    user_document = None
    try:
        user_document = await database.find_one(users_collection, {
            "$or": [
                {"email": request_data.email_or_username},
                {"username": request_data.email_or_username}
            ]
        })

        if not user_document:
            print(f"Login failed: User not found for {request_data.email_or_username}.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        stored_password_hash = user_document.get("password_hash")
        if not stored_password_hash or not verify_password(request_data.password, stored_password_hash):
            print(f"Login failed: Incorrect password for user {user_document.get('username')}.")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        print(f"Authentication successful for user: {user_document.get('username')}")

    except HTTPException:
         raise
    except Exception as e:
        print(f"An error occurred during user authentication process: {e}")
        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during authentication process: {e}"
        )

    user_id_str = str(user_document.get("_id"))
    current_role = user_document.get("role", "free")
    effective_role_for_token = current_role

    try:
        latest_subscription = await database.find_one(
            subscription_history_collection,
            {"user_id": ObjectId(user_id_str)},
            sort=[("start_date", -1), ("created_at", -1)]
        )

        print(f"Checking subscription status for user {user_id_str}. Current role in DB: {current_role}.")

        roles_implying_active_sub = ["paid", "trialing"]

        if current_role in roles_implying_active_sub:
             if latest_subscription:
                  print(f"Latest subscription found: Plan '{latest_subscription.get('plan')}', Status '{latest_subscription.get('status')}', Ends '{latest_subscription.get('end_date')}'")
                  if latest_subscription.get("end_date") and latest_subscription.get("end_date") < datetime.utcnow():
                       print(f"Latest subscription for user {user_id_str} expired on {latest_subscription.get('end_date')}.")
                       effective_role_for_token = "free"
                       print(f"Downgrading user role to 'free' for token.")

                       if current_role != "free":
                            print(f"Updating user {user_id_str} role in database from '{current_role}' to 'free'.")
                            update_role_success = await database.update_one_by_id(
                                users_collection,
                                user_id_str,
                                {"role": "free"}
                            )
                            if update_role_success:
                                 print("Database role update successful.")
                            else:
                                 print("Warning: Failed to update user role in database to 'free'.")
                       else:
                            print("User role is already 'free' in DB, no update needed.")

                  else:
                       print(f"Latest subscription for user {user_id_str} is still active.")
                       effective_role_for_token = current_role

             else:
                  print(f"Warning: User {user_id_str} has role '{current_role}' but no subscription history found. Defaulting role to 'free' for token.")
                  effective_role_for_token = "free"
                  if current_role != "free":
                       print(f"Updating user {user_id_str} role in database from '{current_role}' to 'free' due to missing history.")
                       await database.update_one_by_id(
                            users_collection,
                            user_id_str,
                            {"role": "free"}
                       )
                  else:
                       print("User role is already 'free' in DB, no update needed.")

        elif current_role == "admin":
             print("User has 'admin' role. Subscription status check skipped.")
             effective_role_for_token = "admin"

        else:
             print(f"User has role '{current_role}'. No subscription check needed.")
             effective_role_for_token = current_role

    except Exception as e:
        print(f"Error during subscription status check for user {user_id_str}: {e}")
        traceback.print_exc()
        print("Error occurred during subscription check, defaulting user role to 'free' for token.")
        effective_role_for_token = "free"

    try:
        update_success = await database.update_one_by_id(
            users_collection,
            user_id_str,
            {"last_login": datetime.utcnow()}
        )
        if update_success:
            print(f"Updated last_login for user {user_id_str}.")
        else:
            print(f"Warning: Failed to update last_login for user {user_id_str}.")

    except Exception as e:
        print(f"Error updating last_login for user {user_id_str}: {e}")
        traceback.print_exc()

    token_payload_data = {
        "sub": user_id_str,
        "user_id": user_id_str,
        "role": effective_role_for_token,
    }
    print(f"Creating token with payload: {token_payload_data}")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    access_token = create_access_token(
        data=token_payload_data,
        expires_delta=access_token_expires
    )

    print(f"JWT access token created for user {user_document.get('username')} with role '{effective_role_for_token}'.")

    return Token(access_token=access_token, token_type="bearer")


# --- New Endpoint to Demonstrate Token Verification and Basic RBAC (/api/auth/protected_test) ---
@router.get("/protected_test")
async def protected_test_route(current_user: TokenData = Depends(get_current_user)):
    """
    Example protected endpoint accessible only with a valid JWT.
    Demonstrates accessing authenticated user data (role, id) from the token.
    Includes a basic RBAC check for 'admin' role.
    """
    print(f"Access granted to protected_test_route for user ID: {current_user.user_id}, Role: {current_user.role}")

    response_data = {
        "message": "Successfully accessed protected resource!",
        "user_id": current_user.user_id,
        "user_role": current_user.role,
        "token_expires_at": current_user.exp # Show token expiry from payload
    }

    # Basic RBAC Demonstration: Special message for admins
    if current_user.role == "admin":
        response_data["admin_message"] = "Welcome, Administrator! You have special access."
        print("User has 'admin' role, including admin message.")
    elif current_user.role == "paid":
        response_data["access_level"] = "Paid User Access"
        print("User has 'paid' role.")
    else: # role is 'free' or 'trialing'
         response_data["access_level"] = "Free/Trial Access"
         print("User has 'free' or 'trialing' role.")
         # Note: More granular RBAC for 'free' vs 'trialing' will be implemented later


    # You can add more complex RBAC checks here based on role
    # Example: if current_user.role not in ["admin", "paid"]:
    #    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return response_data

# --- End of protected_test_route endpoint ---

# --- Add other authentication related endpoints below (e.g., logout, email confirmation, password reset) ---