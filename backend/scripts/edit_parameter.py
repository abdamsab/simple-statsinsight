# backend/scripts/edit_parameter.py

# This script is used to update the parameter document in MongoDB.
# It loads parameters from local constants and the associated prompts/schemas files,
# and uses the shared database connection logic.

import asyncio # Needed for running async code
# No longer need os, pymongo, dotenv imports here - handled by shared modules

# --- Import modules from their locations ---
# Import shared database client functions
from ..db import mongo_client as database # Adjusted import path (up one level, then into db)
# Import shared settings
from ..config.settings import settings # Adjusted import path (up one level, then into config)
# Import prompts and schemas from within the same scripts folder
from . import prompts # Relative import within the same scripts package
from . import schemas # Relative import within the same scripts package

# --- Define Parameter Values ---
# These are the configurable values to be stored in the database parameter object.
# Prompt strings and schemas are sourced from prompts.py and schemas.py within this package.

# Fixture URL to scrape from
# Using default values here, could potentially read from script arguments or another config source if needed.
TODAY_FIXTURE_URL = "https://www.soccerstats.com/matches.asp?matchday=1&matchdayn=104" # Or update to your preferred default/current
TOMORROW_FIXTURE_URL = "https://www.soccerstats.com/matches.asp?matchday=2&daym=tomorrow&matchdayn=1"
FETCH_TODAY = True
CHUNK_SIZE_CHARS = 100000 # Character chunk size for sending markdown to AI

# AI Generation Parameters (example values - check actual limits/recommendations)
# Use constants here, or load from a script-specific config if you have complex defaults
MODEL = "gemini-2.0-flash" # Default model name
MAX_OUTPUT_TOKENS = 8192 # Max tokens for AI output
GEMINI_RPM = 30 # Requests per minute rate limit
GEMINI_TPM = 1000000 # Tokens per minute rate limit (less critical for wait_for_rate_limit)
GEMINI_RPD = 1500 # Requests per day rate limit
TEMPERATURE = 0.0 # AI temperature setting
TOP_P = 0.9 # AI top_p setting
# The number of predicted events to request from the AI
NUMBER_OF_PREDICTED_EVENTS = 10 # Default or desired value
# Delay between processing matches (in seconds)
DELAY_BETWEEN_MATCHES = 15


# --- Construct the Parameter Document ---
# This dictionary holds all the parameters to be inserted.
# It includes values from local constants and imports from prompts.py and schemas.py.
parameter_document = {
    "today_fixture_url": TODAY_FIXTURE_URL,
    "tomorrow_fixture_url": TOMORROW_FIXTURE_URL,
    "fetch_today": FETCH_TODAY,
    # Get prompt templates from the imported prompts module:
    "predict_initial_prompt": prompts.PREDICT_INITIAL_PROMPT,
    "predict_final_prompt": prompts.PREDICT_FINAL_INSTRUCTION,
    # Assuming these exist in prompts.py (they were None in your code, keep None if not used)
    "post-match_initial_prompt": getattr(prompts, "POST_MATCH_INITIAL_PROMPT", None),
    "post-match_final_prompt": getattr(prompts, "POST_MATCH_FINAL_INSTRUCTION", None),
    # Include the number of predicted events
    "number_of_predicted_events": NUMBER_OF_PREDICTED_EVENTS,
    # Get schemas from the imported schemas module:
    "match_prediction_schema": schemas.MATCH_PREDICTION_SCHEMA,
    # Assuming this exists in schemas.py (it was None in your code, keep None if not used)
    "post_match_analysis_schema": getattr(schemas, "POST_MATCH_ANALYSIS_SCHEMA", None),
    "chunk_size_chars": CHUNK_SIZE_CHARS,
    "model": MODEL,
    # Include the rate limits and other AI generation parameters
    "max_output_tokens": MAX_OUTPUT_TOKENS,
    "temperature": TEMPERATURE, # Use the defined constant
    "top_p": TOP_P, # Use the defined constant
    "rpm": GEMINI_RPM,
    "tpm": GEMINI_TPM,
    "rpd": GEMINI_RPD,
    "delay_between_matches": DELAY_BETWEEN_MATCHES # Include delay param
}


# --- Function to Update Parameters in Database ---
async def update_parameters_in_db():
    """
    Deletes existing parameter document(s) and inserts a new one
    using the shared database client.
    """
    print("\n--- Running Parameter Update Script ---")

    # --- Step 1: Connect to MongoDB ---
    # Use the shared async connection function from backend.db.mongo_client
    print("Attempting to connect to MongoDB using shared client...")
    # Pass the loaded settings object to the connection function
    await database.connect_to_mongo(settings)


    # --- Step 2: Get the parameters collection ---
    # Use the shared getter function
    parameters_collection = database.get_parameters_collection()

    if parameters_collection is None:
        print("FATAL ERROR: Parameters collection not initialized. Cannot update parameters.")
        print("Please ensure MONGODB_URI and DB_NAME are set in your .env file and MongoDB is running.")
        # No need to explicitly close connection here, startup connection logic will handle failures.
        return

    print(f"Using MongoDB collection: {parameters_collection.name}")


    # --- Step 3: Delete existing parameter documents ---
    print(f"\nAttempting to delete existing documents from '{parameters_collection.name}' collection...")
    try:
        # Delete all documents in the collection using asyncio.to_thread for synchronous operation
        delete_result = await asyncio.to_thread(parameters_collection.delete_many, {})
        print(f"Successfully deleted {delete_result.deleted_count} existing parameter document(s).")
    except Exception as e: # Catching general Exception for simplicity, can add more specific PyMongoError
        print(f"Error during delete_many: {e}")
        print("Parameter update failed at deletion step.")
        return


    # --- Step 4: Insert the new parameter document ---
    print(f"\nAttempting to insert the new parameter document into '{parameters_collection.name}' collection...")
    try:
        # Insert the document using the shared async insert_one
        insert_id = await database.insert_one(parameters_collection, parameter_document)
        if insert_id:
            print(f"Successfully inserted new parameter document with ID: {insert_id}")
        else:
            print("Warning: Insert operation succeeded but did not return an ID.")
    except Exception as e: # Catching general Exception for simplicity, can add more specific PyMongoError
        print(f"Error during insert_one: {e}")
        print("Parameter update failed at insertion step.")
        return

    print("\n--- Parameter Update Script Complete ---")


# --- Main Execution Block for the Script ---
if __name__ == "__main__":
    # Use asyncio.run to execute the main async function
    try:
        asyncio.run(update_parameters_in_db())
    except KeyboardInterrupt:
        print("\nScript interrupted by user.")
    except Exception as e:
        print(f"\nAn unexpected error occurred during script execution: {e}")
    finally:
        # Close the connection after the script finishes or on interruption/error
        # Use shared async close function
        asyncio.run(database.close_mongo_connection())