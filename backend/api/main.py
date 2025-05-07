# backend/api/main.py

# This is the main FastAPI application entry point.
# It sets up the FastAPI app instance, adds global middleware,
# defines startup/shutdown events, and includes routers from feature modules.
# Relies on modules in db/, shared/, config/ and features/.

import asyncio
import os
import uvicorn
from fastapi import FastAPI, Request # Import Request
from fastapi.middleware.cors import CORSMiddleware
import datetime
from google import genai
from typing import Dict, Any # Import Dict, Any

# --- Import modules from their locations ---
from ..db import mongo_client as database
from ..features.football_analytics import routes as football_analytics_routes # Feature router
from ..features.advertising import routes as advertising_routes # New Advertising Feature router
from ..config.settings import settings # Import the settings instance from config/settings.py


# --- FastAPI App Instance ---
# We instantiate settings here so it's available for DB connection in startup
# settings_instance = settings            # Access the imported settings instance

app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Application Startup Event ---
# Connect to DB, load DB config, initialize AI client, store on app.state.
@app.on_event("startup")
async def startup_event():
    """Actions to run on application startup: Connect to DB, load config, initialize AI client, store on app.state."""
    print("Application startup initiated.")

    # Store core components on app.state for access in endpoints and background tasks
    app.state.db_client = None
    app.state.competitions_collection = None
    app.state.predictions_collection = None
    app.state.parameters_collection = None
    app.state.db_parameters = None # Dictionary to hold parameters loaded from DB
    app.state.genai_client = None
    app.state.settings = settings # Store the loaded Pydantic settings object


    # --- Step 1: Connect to MongoDB and get collection references ---
    # Use settings.MONGODB_URI
    await database.connect_to_mongo(app.state.settings) # Pass settings to DB connection
    app.state.db_client = database.mongo_client # Store client reference if needed
    app.state.competitions_collection = database.get_competitions_collection()
    app.state.parameters_collection = database.get_parameters_collection()
    app.state.predictions_collection = database.get_predictions_collection()


    # --- Step 2: Load parameters from the database ---
    if app.state.parameters_collection is None:
        print("FATAL ERROR: Parameters collection not initialized. Cannot load DB configuration.")
        app.state.db_parameters = None
    else:
        try:
            print("Attempting to load parameters from the database...")
            parameter_document = await database.find_one(app.state.parameters_collection, {})

            if parameter_document:
                app.state.db_parameters = parameter_document
                print("DB Parameters successfully loaded from database.")
            else:
                print("FATAL ERROR: No parameter document found in the database. DB Configuration loading failed.")
                app.state.db_parameters = None
        except Exception as e:
            print(f"FATAL ERROR: Error loading DB parameters from database: {e}")
            app.state.db_parameters = None


    # --- Step 3: Initialize Gemini Client ---
    # Use settings.GEMINI_API_KEY loaded by Pydantic Settings
    if app.state.settings and app.state.settings.GEMINI_API_KEY:
        try:
            # Get model name from DB parameters if available, otherwise use a default or error
            model_name_for_print = app.state.db_parameters.get("model", "Unknown Model") if app.state.db_parameters else "Unknown Model (DB params not loaded)"
            print(f"Attempting to initialize Gemini client for model: {model_name_for_print} using google.genai...")

            app.state.genai_client = genai.Client(api_key=app.state.settings.GEMINI_API_KEY)
            print(f"Gemini client initialized successfully.")

        except Exception as e:
            print(f"FATAL ERROR: Error initializing Gemini client: {e}")
            app.state.genai_client = None
    else:
         print("FATAL ERROR: GEMINI_API_KEY environment variable not set or Pydantic settings not loaded. Skipping Gemini client initialization.")
         app.state.genai_client = None


    # --- Check if critical components are initialized on app.state ---
    if app.state.settings is None or app.state.genai_client is None or app.state.db_client is None or app.state.db_parameters is None:
         print("FATAL ERROR: One or more critical startup components failed to initialize and are missing from app.state.")
         # The app may be in a non-functional state. Endpoints should check app.state before proceeding.
         pass # Continue startup, but with errors


    print("Application startup complete.")


# --- Application Shutdown Event ---
# Close DB connection.
@app.on_event("shutdown")
async def shutdown_event():
    """Actions to run on application shutdown: Close DB connection."""
    print("Application shutdown initiated.")
    # Use the close_mongo_connection function from the mongo_client module
    await database.close_mongo_connection() # No need to pass app.state here
    print("MongoDB connection closed.")


# --- Include Feature Routers ---
app.include_router(football_analytics_routes.router)
app.include_router(advertising_routes.router)

# --- Root Endpoint (Optional) ---
@app.get("/")
async def read_root():
    return {"message": "Football Analysis Backend is running."}


# --- Main Execution Block ---
if __name__ == "__main__":
    print("Starting FastAPI server with uvicorn...")
    uvicorn.run(
        "backend.api.main:app", # Specify the package and app location
        host="0.0.0.0",
        port=8000,
        reload=True
    )