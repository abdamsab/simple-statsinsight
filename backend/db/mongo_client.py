# backend/db/mongo_client.py

# This file handles MongoDB connection, disconnection,
# and provides simple data access functions.

import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError
import asyncio
from typing import Dict, Any, List, Optional
# Import the Settings class definition for type hinting
from ..config.settings import Settings
# from dotenv import load_dotenv     # No longer need dotenv load here if api.main loads it via Pydantic Settings   

# --- Global DB Client and Database reference ---
mongo_client: MongoClient | None = None
mongo_db = None # Reference to the specific database


# --- Connection Function (Modified to accept Settings object and use settings.DB_NAME) ---
async def connect_to_mongo(settings: Settings):
    """Connects to MongoDB using URI from Settings object and gets database using settings.DB_NAME."""
    global mongo_client, mongo_db
    if mongo_client is not None:
        print("MongoDB client already connected.")
        return

    # Access MONGODB_URI from the passed Settings object
    mongodb_uri = settings.MONGODB_URI
    db_name = settings.DB_NAME # <--- Get DB_NAME from settings

    if not mongodb_uri:
        print("FATAL ERROR: MONGODB_URI is not set in Pydantic Settings.")
        mongo_client = None
        return
    if not db_name: # <--- Check if DB_NAME is set
        print("FATAL ERROR: DB_NAME is not set in Pydantic Settings.")
        mongo_client = None
        return

    try:
        print("Attempting to connect to MongoDB...")
        mongo_client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        mongo_client.admin.command('ismaster')
        print("MongoDB connection successful.")

        # Get database using the DB_NAME from settings
        mongo_db = mongo_client.get_database(db_name) # <--- Use settings.DB_NAME

    except ConnectionFailure as e:
        print(f"FATAL ERROR: MongoDB connection failed: {e}")
        mongo_client = None
    except Exception as e:
        print(f"FATAL ERROR: An unexpected error occurred during MongoDB connection: {e}")
        mongo_client = None


# --- Disconnection Function ---
# This function doesn't need the Settings object, it just uses the global client.
async def close_mongo_connection():
    """Closes the MongoDB client connection."""
    global mongo_client
    if mongo_client:
        print("Closing MongoDB connection.")
        mongo_client.close()
        mongo_client = None
        print("MongoDB connection closed.")
    else:
        print("No active MongoDB client to close.")


# --- Getter functions for collections ---
# Provides access to specific collections. Returns None if DB not connected.
def get_competitions_collection():
    """Returns the competitions collection."""
    global mongo_db
    # Corrected: Use explicit comparison with None
    if mongo_db is not None:
        # Replace 'competitions' with your actual competitions collection name if different
        return mongo_db.get_collection("competitions")
    return None

def get_parameters_collection():
    """Returns the parameters collection."""
    global mongo_db
    # Corrected: Use explicit comparison with None
    if mongo_db is not None:
        # Replace 'parameters' with your actual parameters collection name if different
        return mongo_db.get_collection("parameters")
    return None

def get_predictions_collection():
    """Returns the predictions collection."""
    global mongo_db
    # Corrected: Use explicit comparison with None
    if mongo_db is not None:
        # Replace 'predictions' with your actual predictions collection name if different
        return mongo_db.get_collection("predictions")
    return None


# Add getter functions for other future collections


# --- Data Access Functions ---
# These functions interact with collections obtained from the getters, no direct Settings needed here.
async def find_one(collection, query: Dict[str, Any]):
    """Finds a single document in a collection."""
    if collection is None:
        print("Error: Collection not available for find_one operation.")
        return None
    try:
        document = await asyncio.to_thread(collection.find_one, query)
        return document
    except PyMongoError as e:
        print(f"MongoDB Error during find_one: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during find_one: {e}")
        return None


async def find_many(collection, query: Dict[str, Any], options: Optional[Dict[str, Any]] = None):
    """Finds multiple documents in a collection."""
    if collection is None:
        print("Error: Collection not available for find_many operation.")
        return []

    limit = options.get("limit", 0) if options else 0
    sort = options.get("sort", None) if options else None
    projection = options.get("projection", None) if options else None
    skip = options.get("skip", 0) if options else 0

    try:
        cursor = collection.find(query, projection)
        if sort:
            cursor = cursor.sort(sort)
        if skip > 0:
            cursor = cursor.skip(skip)
        if limit > 0:
             cursor = cursor.limit(limit)

        documents = await asyncio.to_thread(list, cursor)
        return documents
    except PyMongoError as e:
        print(f"MongoDB Error during find_many: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during find_many: {e}")
        return []


async def insert_one(collection, document: Dict[str, Any]):
    """Inserts a single document into a collection."""
    if collection is None:
        print("Error: Collection not available for insert_one operation.")
        return None
    try:
        result = await asyncio.to_thread(collection.insert_one, document)
        return result.inserted_id
    except PyMongoError as e:
        if e.code == 11000:
             print(f"MongoDB Duplicate Key Error during insert_one: {e}")
        else:
             print(f"MongoDB Error during insert_one: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during insert_one: {e}")
        return None