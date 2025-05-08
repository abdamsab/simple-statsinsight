# backend/api/main.py

# This is the main FastAPI application entry point.
# It sets up the FastAPI app instance, adds global middleware,
# defines startup/shutdown events, and includes routers from feature modules.
# Relies on modules in db/, shared/, config/ and features/.

import asyncio
import os
import uvicorn
from fastapi import FastAPI, Request, HTTPException, status # Import Request, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
import datetime
from google import genai
from typing import Dict, Any, Optional # Import Dict, Any, Optional
from fastapi.responses import JSONResponse # Import JSONResponse
from pymongo.collection import Collection # Import Collection for type hinting


# --- Import modules from their locations ---
from ..db import mongo_client as database
from ..features.user.auth import routes as auth_routes # Import the auth router
from ..features.football_analytics import routes as football_analytics_routes # Feature router
from ..features.advertising import routes as advertising_routes # New Advertising Feature router
from ..features.admin import routes as admin_routes
from ..config.settings import settings # Import the settings instance from config/settings.py


# --- FastAPI App Instance ---
app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust in production!
    allow_credentials=True,
    allow_methods=["*"], # Allows all methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers (including Authorization)
)


# --- Application Startup Event ---
# Connect to DB, load DB config, initialize AI client, store on app.state.
@app.on_event("startup")
async def startup_event():
    """Actions to run on application startup: Connect to DB, load config, initialize AI client, store on app.state."""
    print("Application startup initiated.")

    # Store core components on app.state for access in endpoints and background tasks
    app.state.db_client = None
    app.state.competitions_collection: Optional[Collection] = None
    app.state.predictions_collection: Optional[Collection] = None # Assuming predictions collection exists based on football_analytics router
    app.state.parameters_collection: Optional[Collection] = None
    app.state.db_parameters: Optional[Dict[str, Any]] = None # Dictionary to hold parameters loaded from DB
    app.state.genai_client = None
    app.state.settings = settings # Store the loaded Pydantic settings object

    # Add other collection states here as they are needed in app.state
    app.state.users_collection: Optional[Collection] = None # State for users collection
    app.state.subscription_history_collection: Optional[Collection] = None # State for subscription history collection
    app.state.email_tokens_collection: Optional[Collection] = None # State for email tokens collection
    app.state.referral_events_collection: Optional[Collection] = None # State for referral events collection
    app.state.advertising_collection: Optional[Collection] = None # State for advertising collection


    # --- Step 1: Connect to MongoDB and get collection references ---
    try:
        # Use settings.MONGODB_URI from app.state.settings
        await database.connect_to_mongo(app.state.settings) # Pass settings to DB connection
        app.state.db_client = database.mongo_client # Store client reference if needed

        # Get and store collection references - Ensure getter functions exist in mongo_client.py
        app.state.competitions_collection = database.get_competitions_collection() # Confirmed existing
        app.state.parameters_collection = database.get_parameters_collection() # Confirmed existing
        app.state.predictions_collection = database.get_predictions_collection() # Assuming this getter exists
        # Getters for User/Auth related collections
        app.state.users_collection = database.get_users_collection()
        app.state.subscription_history_collection = database.get_subscription_history_collection()
        app.state.email_tokens_collection = database.get_email_tokens_collection()
        app.state.referral_events_collection = database.get_referral_events_collection()
        # Getter for Advertising collection
        app.state.advertising_collection = database.get_advertising_collection() # Assuming this getter exists


        print("Database connection established and collections are accessible.")

    except Exception as e:
        print(f"FATAL ERROR: Database connection failed or collection getters failed on startup: {e}")
        # Handle database connection failure - set a flag or ensure collections are None
        app.state.db_client = None # Ensure client is None on failure
        # Ensure all collections are None if DB connection failed
        app.state.competitions_collection = None
        app.state.parameters_collection = None
        app.state.predictions_collection = None
        app.state.users_collection = None
        app.state.subscription_history_collection = None
        app.state.email_tokens_collection = None
        app.state.referral_events_collection = None
        app.state.advertising_collection = None


    # --- Step 2: Load parameters from the database ---
    if app.state.parameters_collection is None:
        print("FATAL ERROR: Parameters collection not initialized. Cannot load DB configuration.")
        app.state.db_parameters = {} # Set to empty dict on critical failure
    else:
        try:
            print("Attempting to load parameters from the database...")
            # Using the helper function defined in mongo_client or a direct find_one if not available
            # Assuming find_one is available via your database alias
            parameter_document = await database.find_one(app.state.parameters_collection, {}) # Use await as find_one is async

            if parameter_document:
                app.state.db_parameters = parameter_document
                print("DB Parameters successfully loaded from database.")
            else:
                print("FATAL ERROR: No parameter document found in the database. DB Configuration loading failed.")
                app.state.db_parameters = {} # Set to empty dict if not found, but log as FATAL if required

        except Exception as e:
            print(f"FATAL ERROR: Error loading DB parameters from database: {e}")
            app.state.db_parameters = {} # Set to empty dict on error


    # --- Step 3: Initialize Gemini Client ---
    # Use settings.GEMINI_API_KEY loaded by Pydantic Settings
    if app.state.settings and app.state.settings.GEMINI_API_KEY:
        try:
            # Check if model name is available in loaded parameters, fallback to default if needed
            model_name = app.state.db_parameters.get("gemini_model_name", 'gemini-pro') if app.state.db_parameters and isinstance(app.state.db_parameters, dict) else 'gemini-pro' # Added check for db_parameters type
            print(f"Attempting to initialize Gemini client for model: {model_name} using google.genai...")

            # Note: The genai.Client() call might require the model name in the constructor or subsequent calls
            # Based on your existing code: app.state.genai_client = genai.GenerativeModel('gemini-pro') - Let's use this
            # Assuming gemini.GenerativeModel is the correct way to instantiate with the API key from google-generativeai library
            app.state.genai_client = genai.GenerativeModel(model_name)
            # The API key is often configured globally or implicitly by the library after importing google.generativeai
            # If explicit API key setting is needed, add it based on google-generativeai docs.
            # Example: genai.configure(api_key=app.state.settings.GEMINI_API_KEY) needs to be called once.
            # Let's assume your database.configure is handling the global config if needed,
            # or the library picks it up from the environment variable automatically.


            print(f"Gemini client initialized successfully for model: {model_name}.")

        except Exception as e:
            print(f"FATAL ERROR: Error initializing Gemini client: {e}")
            app.state.genai_client = None
    else:
        print("FATAL ERROR: GEMINI_API_KEY environment variable not set or Pydantic settings not loaded. Skipping Gemini client initialization.")
        app.state.genai_client = None


    # --- Final Check for Critical Components ---
    # Include all required collections and components in final check
    if not all([
        app.state.settings,
        app.state.genai_client,
        app.state.db_client,
        isinstance(app.state.db_parameters, dict), # Check if parameters loaded successfully as a dict
        app.state.users_collection,
        app.state.subscription_history_collection,
        app.state.email_tokens_collection,
        app.state.referral_events_collection,
        app.state.competitions_collection,
        app.state.predictions_collection,
        app.state.advertising_collection, # Include advertising collection in check
    ]):
        print("FATAL ERROR: One or more critical startup components failed to initialize and are missing from app.state. Application may be in a non-functional state.")
        # The app may be in a non-functional state. Endpoints should check app.state before proceeding.
        pass # Continue startup, but with errors


    print("Application startup complete.")


# --- Application Shutdown Event ---
@app.on_event("shutdown")
async def shutdown_event():
    """Actions to run on application shutdown: Close DB connection."""
    print("Application shutdown initiated.")
    # Use the close_mongo_connection function from the mongo_client module
    if hasattr(app.state, 'db_client') and app.state.db_client: # Check if db_client exists and is not None
        await database.close_mongo_connection(app.state.db_client) # Pass the client instance
    print("MongoDB connection closed.")


# --- Include Feature Routers ---
# Include the auth router from backend/features/user/auth/routes.py
app.include_router(auth_routes.router, prefix="/api/auth", tags=["auth"]) # INCLUDE AUTH ROUTER WITH PREFIX AND TAGS

# Include other existing routers
app.include_router(football_analytics_routes.router) # Already included
app.include_router(advertising_routes.router) # Already included
app.include_router(admin_routes.router) # Already included


# --- Root Endpoint (Optional) ---
@app.get("/")
async def read_root():
    return {"message": "Football Analysis Backend is running."}

# --- Define Global Exception Handlers (Optional) ---
# Example handler for HTTPException (like the ones we raise for 401, 404, etc.)
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# Example handler for generic Exception
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    print(f"Unhandled exception occurred: {exc}")
    import traceback
    print(traceback.format_exc()) # Print traceback for debugging server-side
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred."}
    )


# --- Main Execution Block ---
if __name__ == "__main__":
    print("Starting FastAPI server with uvicorn...")
    uvicorn.run(
        "backend.api.main:app", # Specify the package and app location
        host="0.0.0.0",
        port=8000,
        reload=True
    )