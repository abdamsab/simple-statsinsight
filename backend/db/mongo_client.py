# backend/db/mongo_client.py

# This file handles MongoDB connection, disconnection,
# and provides simple data access functions.

import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError
import asyncio
from typing import Dict, Any, List, Optional
from bson import ObjectId # --- ADDED: Import ObjectId for working with document IDs
import traceback # --- ADDED: Import traceback for detailed error logging
# Import the Settings class definition for type hinting
from ..config.settings import Settings
# from dotenv import load_dotenv      # No longer need dotenv load here if api.main loads it via Pydantic Settings
from pymongo.collection import Collection # Import Collection for type hinting


# --- Global DB Client and Database reference ---
mongo_client: MongoClient | None = None
mongo_db = None # Reference to the specific database


# --- Collection References (Typed) ---
users_collection: Optional[Collection] = None
subscription_history_collection: Optional[Collection] = None
email_tokens_collection: Optional[Collection] = None
parameters_collection: Optional[Collection] = None
referral_events_collection: Optional[Collection] = None
competitions_collection: Optional[Collection] = None
predictions_collection: Optional[Collection] = None # Reference for the main match predictions collection - ADDED GLOBAL REFERENCE
advertising_collection: Optional[Collection] = None


# --- Connection Function (Modified to accept Settings object and use settings.DB_NAME) ---
# Accepts the settings object from main.py
async def connect_to_mongo(settings: Settings):
    """Connects to MongoDB using URI from Settings object and gets database using settings.DB_NAME."""
    # Ensure all collection globals are included in the global statement
    global mongo_client, mongo_db, users_collection, subscription_history_collection, email_tokens_collection, parameters_collection, referral_events_collection, competitions_collection, predictions_collection, advertising_collection # MODIFIED GLOBAL LIST
    if mongo_client is not None:
        print("MongoDB client already connected.")
        return

    # Access MONGODB_URI and DB_NAME from the passed Settings object
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
        # Use synchronous MongoClient and asyncio.to_thread for potentially blocking operations
        mongo_client = MongoClient(mongodb_uri, serverSelectionTimeoutMS=5000)
        # Use asyncio.to_thread for the blocking command
        await asyncio.to_thread(mongo_client.admin.command, 'ismaster')
        print("MongoDB connection successful.")

        # Get database using the DB_NAME from settings
        mongo_db = mongo_client.get_database(db_name) # <--- Use settings.DB_NAME

    except ConnectionFailure as e:
        print(f"FATAL ERROR: MongoDB connection failed: {e}")
        mongo_client = None
    except Exception as e:
        print(f"FATAL ERROR: An unexpected error occurred during MongoDB connection: {e}")
        mongo_client = None

    # --- Get Collection References ---
    # Replace with your actual collection names
    users_collection = mongo_db.get_collection("users")
    subscription_history_collection = mongo_db.get_collection("subscription_history")
    email_tokens_collection = mongo_db.get_collection("email_tokens")
    parameters_collection = mongo_db.get_collection("parameters")
    referral_events_collection = mongo_db.get_collection("referral_events")
    competitions_collection = mongo_db.get_collection("competitions")
    predictions_collection = mongo_db.get_collection("predictions") # Get the predictions collection - ADDED LINE
    advertising_collection = mongo_db.get_collection("advertising")

    print("MongoDB collections referenced successfully.")


# --- Disconnection Function ---
# This function doesn't need the Settings object, it just uses the global client.
# Added type hint and optional client parameter for clarity, though global is used
async def close_mongo_connection(client: MongoClient | None = None):
    """Closes the MongoDB client connection."""
    global mongo_client
    # Use the global client if no client is passed
    client_to_close = client if client is not None else mongo_client

    if client_to_close:
        print("Closing MongoDB connection.")
        # Use asyncio.to_thread for the blocking close operation
        await asyncio.to_thread(client_to_close.close) # Use client_to_close
        mongo_client = None # Ensure the global client is set to None after closing
        print("MongoDB connection closed.")
    else:
        print("No active MongoDB client to close.")


# --- Getter functions for collections ---
# Provides access to specific collections. Returns None if DB not connected.
def get_competitions_collection() -> Optional[Collection]: # Added type hint for return
    """Returns the competitions collection."""
    global mongo_db
    if mongo_db is not None:
        return mongo_db.get_collection("competitions")
    return None

def get_parameters_collection() -> Optional[Collection]: # Added type hint for return
    """Returns the parameters collection."""
    global mongo_db
    if mongo_db is not None:
        return mongo_db.get_collection("parameters")
    return None

# --- ADDED: Getter function for the predictions collection ---
def get_predictions_collection() -> Optional[Collection]: # ADDED GETTER FUNCTION
    """Returns the predictions collection."""
    global mongo_db
    if mongo_db is not None:
        return mongo_db.get_collection("predictions")
    return None


# --- Collection Getter: Advertising (New) ---
def get_advertising_collection() -> Optional[Collection]: # Added type hint for return
    """Returns the advertising collection."""
    global mongo_db
    if mongo_db is not None:
        return mongo_db.get_collection("advertising")
    return None



# --- New: Getter for Users Collection ---
def get_users_collection() -> Optional[Collection]: # Added type hint for return
    """Gets the MongoDB 'users' collection."""
    global mongo_db
    if mongo_db:
        return mongo_db.get_collection("users")
    else:
        print("Error: MongoDB database not initialized. Cannot get 'users' collection.")
        return None



# --- Getter for Email Tokens Collection ---
def get_email_tokens_collection() -> Optional[Collection]: # Added type hint for return
    """Gets the MongoDB 'email_tokens' collection."""
    global mongo_db
    if mongo_db:
        return mongo_db.get_collection("email_tokens")
    else:
        print("Error: MongoDB database not initialized. Cannot get 'email_tokens' collection.")
        return None

# --- Getter for Subscription History Collection ---
def get_subscription_history_collection() -> Optional[Collection]: # Added type hint for return
    """Gets the MongoDB 'subscription_history' collection."""
    global mongo_db
    if mongo_db:
        return mongo_db.get_collection("subscription_history")
    else:
        print("Error: MongoDB database not initialized. Cannot get 'subscription_history' collection.")
        return None


# --- New: Getter for Referral Events Collection ---
def get_referral_events_collection() -> Optional[Collection]: # Added type hint for return
    """Gets the MongoDB 'referral_events' collection."""
    global mongo_db
    if mongo_db:
        return mongo_db.get_collection("referral_events")
    else:
        print("Error: MongoDB database not initialized. Cannot get 'referral_events' collection.")
        return None



# Add getter functions for other future collections

# --- Data Access Functions (CRUD) ---
# These functions interact with collections obtained from the getters, no direct Settings needed here.
async def find_one(collection: Collection | None, query: Dict[str, Any]) -> Optional[Dict[str, Any]]: # Added type hint for return
    """Finds a single document in a collection."""
    if collection is None:
        print("Error: Collection not available for find_one operation.")
        return None
    try:
        # Use asyncio.to_thread for the blocking find_one operation
        document = await asyncio.to_thread(collection.find_one, query)
        return document
    except PyMongoError as e:
        print(f"MongoDB Error during find_one: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during find_one: {e}")
        # Include traceback for unexpected errors
        print(traceback.format_exc())
        return None


async def find_many(collection: Collection | None, query: Dict[str, Any], options: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]: # Added type hint for return
    """Finds multiple documents in a collection."""
    if collection is None:
        print("Error: Collection not available for find_many operation.")
        return []

    limit = options.get("limit", 0) if options else 0
    sort = options.get("sort", None) if options else None
    projection = options.get("projection", None) if options else None
    skip = options.get("skip", 0) if options else 0

    try:
        # Build the cursor object - these calls themselves are usually fast
        cursor = collection.find(query, projection)
        if sort:
            cursor = cursor.sort(sort)
        if skip > 0:
            cursor = cursor.skip(skip)
        if limit > 0:
             cursor = cursor.limit(limit)

        # Use asyncio.to_thread for the blocking cursor iteration (converting to list)
        documents = await asyncio.to_thread(list, cursor) # Converting the cursor to a list fetches all results
        return documents
    except PyMongoError as e:
        print(f"MongoDB Error during find_many: {e}")
        return []
    except Exception as e:
        print(f"An unexpected error occurred during find_many: {e}")
        # Include traceback for unexpected errors
        print(traceback.format_exc())
        return []


async def insert_one(collection: Collection | None, document: Dict[str, Any]) -> Optional[ObjectId]: # Added type hint for return
    """Inserts a single document into a collection."""
    if collection is None:
        print("Error: Collection not available for insert_one operation.")
        return None
    try:
        # Use asyncio.to_thread for the blocking insert_one operation
        result = await asyncio.to_thread(collection.insert_one, document)
        # Check if the insertion was acknowledged
        if result.acknowledged:
             # print(f"Successfully inserted document with ID: {result.inserted_id}") # Optional success print
             return result.inserted_id # Return the ObjectId of the inserted document
        else:
             print(f"Warning: Insert operation not acknowledged for document in collection '{collection.name}'.")
             # Log details of the document that failed to be acknowledged
             # print(f"Document data (first 200 chars): {str(document)[:200]}...") # Optional debug print
             return None # Return None if insertion was not acknowledged

    except PyMongoError as e:
        # Specific error handling for duplicate key errors
        if e.code == 11000:
             print(f"MongoDB Duplicate Key Error during insert_one: {e}")
        else:
             print(f"MongoDB Error during insert_one: {e}")
        return None # Return None on insertion failure due to DB error
    except Exception as e:
        print(f"An unexpected error occurred during insert_one: {e}")
        # Include details of the document that failed to insert
        # print(f"Document data (first 200 chars): {str(document)[:200]}...") # Optional debug print
        # Include traceback for unexpected errors
        print(traceback.format_exc())
        return None # Return None on unexpected insertion failure

# --- ADDED: Function to update a document by ObjectId string ---
async def update_one_by_id(collection: Collection | None, doc_id: str, update_data: Dict[str, Any]) -> bool:
    """
    Updates a single document in the specified collection by its MongoDB ObjectId string.
    Args:
        collection: The PyMongo collection object.
        doc_id: The string representation of the document's ObjectId.
        update_data: A dictionary containing the fields and values to update.
                     Uses MongoDB's $set operator.
    Returns:
        True if the update was successful (matched and modified a document or matched with no modification), False otherwise.
    """
    if collection is None:
        print(f"Error: Collection not available for update_one_by_id operation for doc_id: {doc_id}.")
        return False

    if not isinstance(doc_id, str):
        print(f"Error: update_one_by_id received non-string doc_id: {doc_id} ({type(doc_id)})")
        return False

    try:
        # Convert the string doc_id to ObjectId
        object_id = ObjectId(doc_id)
    except Exception as e:
        print(f"Error: Invalid ObjectId string provided to update_one_by_id: {doc_id} - {e}")
        # Include traceback for ObjectId conversion error
        print(traceback.format_exc())
        return False # Indicate failure due to invalid ID

    try:
        # Use $set to update specific fields - ensures only specified fields are modified
        # Use asyncio.to_thread for the blocking update_one operation
        result = await asyncio.to_thread(collection.update_one, {"_id": object_id}, {"$set": update_data})

        # Check if a document was matched and modified
        if result.matched_count == 1 and result.modified_count >= 0: # >=0 because data might be the same
             # print(f"Successfully updated document with ID: {doc_id}. Matched: {result.matched_count}, Modified: {result.modified_count}") # Optional success print
             return True # Consider it successful if matched, even if data was identical
        else:
             # Log a warning if the document wasn't found or wasn't modified when expected.
             print(f"Warning: Update operation by ID {doc_id} did not match or modify as expected. Matched: {result.matched_count}, Modified: {result.modified_count}")
             return False # Indicate failure if not matched or not modified as expected

    except PyMongoError as e:
        print(f"MongoDB Error during update_one_by_id operation for document ID {doc_id}: {e}")
        return False # Indicate failure on DB error
    except Exception as e:
        print(f"An unexpected error occurred during update_one_by_id operation for document ID {doc_id}: {e}")
        # Include traceback for unexpected errors
        print(traceback.format_exc())
        return False # Indicate failure on unexpected exception

# --- End of update_one_by_id ---