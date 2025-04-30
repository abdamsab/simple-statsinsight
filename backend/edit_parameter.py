import asyncio
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure, PyMongoError
from dotenv import load_dotenv 
from backend import prompt


load_dotenv()

# --- MongoDB URI Loading ---
MONGODB_URI = os.environ.get("MONGODB_URI")


mongo_client: MongoClient = None 
db = None

parameters_collection = None


# This code block attempts to connect to MongoDB and get collection references

if MONGODB_URI:
    try:
        print("Attempting to connect to MongoDB...")
        # Connect to MongoDB (this call is synchronous)
        mongo_client = MongoClient(MONGODB_URI)
        # The ismaster command is cheap and does not require auth.
        # Use a non-async equivalent or wrapper if intended to be truly async
        mongo_client.admin.command('ismaster') # Synchronous check
        print("MongoDB connection successful.")

        # Get database and collection references (synchronous)
        DB_NAME = "statsinsight" # Your database name
        # Define collection name as constants for easy access
        PARAMETERS_COLLECTION_NAME = "parameters"

        db = mongo_client[DB_NAME]
        parameters_collection = db[PARAMETERS_COLLECTION_NAME]

        print(f"Using MongoDB database: {DB_NAME}")
        print(f"Using MongoDB collection: {parameters_collection.name}")

    except ConnectionFailure as e:
        print(f"FATAL ERROR: Could not connect to MongoDB: {e}")
        # Ensure clients/collections are None on failure
        mongo_client = None
        db = None
        parameters_collection = None
    except Exception as e:
         print(f"An unexpected error occurred during MongoDB connection: {e}")
         # Ensure clients/collections are None on failure
         mongo_client = None
         db = None
         parameters_collection = None
else:
    print("FATAL ERROR: MONGODB_URI environment variable not set. Cannot connect to MongoDB.")


# --- Define Parameter Values ---
# These are the configurable values to be stored in the database parameter object.
# Prompt strings are sourced from prompt.py.

# Fixture URL to scrape from
DEFAULT_FIXTURE_URL = "https://www.soccerstats.com/matches.asp?matchday=2&daym=tomorrow&matchdayn=104" # Or update to your preferred default/current

# Rate limit values (example values - check actual limits if needed)
GEMINI_RPM = 30
GEMINI_TPM = 1000000 # Tokens per minute
GEMINI_RPD = 1500 # Requests per day

# The number of predicted events to request from the AI
NUMBER_OF_PREDICTED_EVENTS = 9 # Default or desired value


# --- Construct the Parameter Document ---
# This dictionary holds all the parameters to be inserted.
parameter_document = {
    "fixture_url": DEFAULT_FIXTURE_URL,
    # Get prompt templates from prompt.py:
    "predict_initial_prompt": prompt.INITIAL_PREDICTION_PROMPT,
    "predict_final_prompt": prompt.FINAL_PREDICTION_INSTRUCTION,
    "post-match_initial_prompt": prompt.POST_MATCH_INITIAL_PROMPT, # Currently None
    "post-match_final_prompt": prompt.POST_MATCH_FINAL_PROMPT,   # Currently None
    # Include the new number of predicted events
    "number_of_predicted_events": NUMBER_OF_PREDICTED_EVENTS,
    # Include the rate limits
    "rpm": GEMINI_RPM,
    "tpm": GEMINI_TPM,
    "rpd": GEMINI_RPD
}


# --- Function to Update Parameters in Database ---
async def update_parameters_in_db():
    """
    Deletes existing parameter document(s) and inserts a new one
    with values from prompt.py and local constants.
    """
    print("\n--- Running Parameter Update Script ---")

    # Check if MongoDB connection and collection are initialized
    global mongo_client, db, parameters_collection
    if mongo_client is None or db is None or parameters_collection is None:
        print("MongoDB client or parameters collection not fully initialized. Cannot update parameters.")
        print("Please ensure MONGODB_URI is set in your .env file and MongoDB is running.")
        return

    # --- Step 1: Delete existing parameter documents ---
    print(f"Attempting to delete existing documents from '{parameters_collection.name}' collection...")
    try:
        # Delete all documents in the collection.
        delete_result = await asyncio.to_thread(parameters_collection.delete_many, {})
        print(f"Successfully deleted {delete_result.deleted_count} existing parameter document(s).")
    except PyMongoError as e:
        print(f"MongoDB Error during delete_many: {e}")
        print("Parameter update failed at deletion step.")
        return
    except Exception as e:
        print(f"Unexpected error during delete_many: {e}")
        print("Parameter update failed at deletion step.")
        return


    # --- Step 2: Insert the new parameter document ---
    print(f"\nAttempting to insert the new parameter document into '{parameters_collection.name}' collection...")
    try:
        insert_result = await asyncio.to_thread(parameters_collection.insert_one, parameter_document)
        print(f"Successfully inserted new parameter document with ID: {insert_result.inserted_id}")
    except PyMongoError as e:
        print(f"MongoDB Error during insert_one: {e}")
        print("Parameter update failed at insertion step.")
        return
    except Exception as e:
        print(f"Unexpected error during insert_one: {e}")
        print("Parameter update failed at insertion step.")
        return

    print("\n--- Parameter Update Script Complete ---")


# --- Main Execution Block for the Script ---
if __name__ == "__main__":
    # This block runs the update function when you execute this script directly.

    async def run_script():
         # Allow the top-level initialization block (MongoDB connection) to run.
         # Add a small delay to ensure it's had a chance to complete before we check.
         await asyncio.sleep(0.1)

         # --- Run the parameter update logic ---
         await update_parameters_in_db()

         # Close the connection after the script finishes
         global mongo_client
         if mongo_client:
              mongo_client.close() # Synchronous close
              print("\nMongoDB connection closed.")


    # Use asyncio.run to start the async execution for the script
    asyncio.run(run_script())