import os
import asyncio
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, WriteConcernError, BulkWriteError, PyMongoError
from dotenv import load_dotenv 


load_dotenv()


# --- MongoDB Configuration ---
MONGODB_URI = os.environ.get("MONGODB_URI") # Get URI from environment variable
DB_NAME = "statsinsight" # Database name

PREDICTIONS_COLLECTION_NAME = "predictions"
COMPETITIONS_COLLECTION_NAME = "competitions"
PARAMETERS_COLLECTION_NAME = "parameters"

# --- MongoDB Client and Database Instances ---
# These will be initialized when connect_to_mongo() is called
mongo_client: MongoClient = None 
db = None
predictions_collection = None
competitions_collection = None
parameters_collection = None


async def connect_to_mongo():
    """Establishes connection to MongoDB on application startup."""
    
    global mongo_client, db, predictions_collection, competitions_collection, parameters_collection

    if not MONGODB_URI:
        print("FATAL ERROR: MONGODB_URI environment variable not set. Cannot connect to MongoDB.")
        return

    try:
        print("Attempting to connect to MongoDB...")
        # Connect to MongoDB (this call is synchronous)
        mongo_client = MongoClient(MONGODB_URI)
        # The ismaster command is cheap and does not require auth.
        # Use a non-async equivalent or wrapper if connect_to_mongo is intended to be truly async
        # For simplicity with synchronous pymongo, we can keep this check but acknowledge it's blocking
        mongo_client.admin.command('ismaster') # Synchronous check
        print("MongoDB connection successful.")

        # Get database and collection references (synchronous)
        db = mongo_client[DB_NAME]
        predictions_collection = db[PREDICTIONS_COLLECTION_NAME]
        competitions_collection = db[COMPETITIONS_COLLECTION_NAME]
        parameters_collection = db[PARAMETERS_COLLECTION_NAME]

        print(f"Using MongoDB database: {DB_NAME}")
        print(f"Using MongoDB collection: {predictions_collection.name}")
        print(f"Using MongoDB collection: {competitions_collection.name}")
        print(f"Using MongoDB collection: {parameters_collection.name}")

    except ConnectionFailure as e:
        print(f"FATAL ERROR: Could not connect to MongoDB: {e}")
        # Ensure clients/collections are None on failure
        mongo_client = None
        db = None
        predictions_collection = None
        competitions_collection = None
        parameters_collection = None
    except Exception as e:
         print(f"An unexpected error occurred during MongoDB connection: {e}")
         # Ensure clients/collections are None on failure
         mongo_client = None
         db = None
         predictions_collection = None
         competitions_collection = None
         parameters_collection = None


async def close_mongo_connection():
    """Closes MongoDB connection on application shutdown."""
    # Use async def for consistency, though pymongo's close is synchronous
    global mongo_client
    if mongo_client:
        mongo_client.close() # Synchronous close
        print("MongoDB connection closed.")


# --- Functions to get collection references ---
# These allow other modules to access the initialized collections
def get_predictions_collection():
    """Returns the predictions collection object."""
    if predictions_collection is None: # Use explicit None check
        print("Warning: Predictions collection not initialized.")
    return predictions_collection

def get_competitions_collection():
    """Returns the competitions collection object."""
    if competitions_collection is None: # Use explicit None check
        print("Warning: Competitions collection not initialized.")
    return competitions_collection

def get_parameters_collection():
    """Returns the parameters collection object."""
    if parameters_collection is None: # Use explicit None check
        print("Warning: Parameters collection not initialized.")
    return parameters_collection

# --- Generic CRUD Functions (Asynchronous Wrappers) ---
# These functions provide a consistent interface for DB operations.
# They accept the collection object as an argument.

async def insert_one(collection, document):
    """Inserts a single document into the specified collection."""
    if collection is None:
        print("Error: Collection not initialized for insert_one.")
        return None
    try:
        # pymongo's insert_one is synchronous, so we yield control using await asyncio.to_thread
        # to prevent blocking the async event loop.
        result = await asyncio.to_thread(collection.insert_one, document)
        # print(f"Inserted document with ID: {result.inserted_id}") # Optional logging
        return result.inserted_id # Return the ID of the inserted document
    except OperationFailure as e:
        print(f"MongoDB Operation Error during insert_one: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during insert_one: {e}")
        return None

async def insert_many(collection, documents):
    """Inserts multiple documents into the specified collection."""
    if collection is None:
        print("Error: Collection not initialized for insert_many.")
        return None
    if not isinstance(documents, list) or not documents:
        print("Error: insert_many requires a non-empty list of documents.")
        return []
    try:
        result = await asyncio.to_thread(collection.insert_many, documents)
        # print(f"Inserted documents with IDs: {result.inserted_ids}") # Optional logging
        return result.inserted_ids # Return list of IDs
    except BulkWriteError as bwe:
        print(f"MongoDB Bulk Write Error during insert_many: {bwe.details}")
        return []
    except OperationFailure as e:
        print(f"MongoDB Operation Error during insert_many: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error during insert_many: {e}")
        return []

async def find_one(collection, query, options=None):
    """Retrieves a single document from the specified collection."""
    if collection is None:
        print("Error: Collection not initialized for find_one.")
        return None
    try:
        # query is a dictionary, options is optional
        result = await asyncio.to_thread(collection.find_one, query, **(options or {}))
        return result # Returns the document (dict) or None if not found
    except OperationFailure as e:
        print(f"MongoDB Operation Error during find_one: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during find_one: {e}")
        return None

async def find_many(collection, query, options=None):
    """Retrieves multiple documents from the specified collection."""
    if collection is None:
        print("Error: Collection not initialized for find_many.")
        return []
    try:
        # find() returns a cursor, need to convert it to a list (synchronous)
        cursor = await asyncio.to_thread(collection.find, query, **(options or {}))
        documents = await asyncio.to_thread(list, cursor) # Fetch all documents from the cursor
        return documents # Returns a list of documents
    except OperationFailure as e:
        print(f"MongoDB Operation Error during find_many: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error during find_many: {e}")
        return []

async def update_one(collection, query, update, options=None):
    """Updates a single document in the specified collection."""
    if collection is None:
        print("Error: Collection not initialized for update_one.")
        return None
    try:
        # query is dict, update is dict using operators like $set, $inc etc.
        result = await asyncio.to_thread(collection.update_one, query, update, **(options or {}))
        # Returns UpdateResult object
        # print(f"Matched {result.matched_count} document(s), modified {result.modified_count} document(s).") # Optional logging
        return result.modified_count # Return count of modified documents
    except OperationFailure as e:
        print(f"MongoDB Operation Error during update_one: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during update_one: {e}")
        return None

async def update_many(collection, query, update, options=None):
    """Updates multiple documents in the specified collection."""
    if collection is None:
        print("Error: Collection not initialized for update_many.")
        return None
    try:
        result = await asyncio.to_thread(collection.update_many, query, update, **(options or {}))
        # Returns UpdateResult object
        # print(f"Matched {result.matched_count} document(s), modified {result.modified_count} document(s).") # Optional logging
        return result.modified_count # Return count of modified documents
    except OperationFailure as e:
        print(f"MongoDB Operation Error during update_many: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during update_many: {e}")
        return None

async def delete_one(collection, query, options=None):
    """Deletes a single document from the specified collection."""
    if collection is None:
        print("Error: Collection not initialized for delete_one.")
        return None
    try:
        result = await asyncio.to_thread(collection.delete_one, query, **(options or {}))
        # Returns DeleteResult object
        # print(f"Deleted {result.deleted_count} document(s).") # Optional logging
        return result.deleted_count # Return count of deleted documents
    except OperationFailure as e:
        print(f"MongoDB Operation Error during delete_one: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during delete_one: {e}")
        return None

async def delete_many(collection, query, options=None):
    """Deletes multiple documents from the specified collection."""
    if collection is None:
        print("Error: Collection not initialized for delete_many.")
        return None
    try:
        result = await asyncio.to_thread(collection.delete_many, query, **(options or {}))
        # Returns DeleteResult object
        # print(f"Deleted {result.deleted_count} document(s).") # Optional logging
        return result.deleted_count # Return count of deleted documents
    except OperationFailure as e:
        print(f"MongoDB Operation Error during delete_many: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during delete_many: {e}")
        return None