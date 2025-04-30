
import asyncio
import os
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure
from dotenv import load_dotenv 
from backend import prompt

initial_predict_template = prompt.INITIAL_PREDICTION_PROMPT
final_preddict_template = prompt.FINAL_PREDICTION_INSTRUCTION

initial_analysis_template = prompt.POST_MATCH_INITIAL_PROMPT
final_analysis_template = prompt.POST_MATCH_FINAL_PROMPT
    
load_dotenv()

# --- MongoDB URI Loading ---
MONGODB_URI = os.environ.get("MONGODB_URI")

# --- Initialize MongoDB Client and Collections ---
mongo_client = None
db = None
predictions_collection = None
competitions_collection = None
parameters_collection = None

# This code block attempts to connect to MongoDB and get collection references
if MONGODB_URI:
    try:
        print("Attempting to connect to MongoDB...")
            
        mongo_client = MongoClient(MONGODB_URI) # Connect to MongoDB
            
        mongo_client.admin.command('ismaster')  # The ismaster command is cheap and does not require auth.
        print("MongoDB connection successful.")
            
        DB_NAME = "statsinsight" # database name
        db = mongo_client[DB_NAME]
        print(f"Using MongoDB database: {DB_NAME}")
            
        # Get references to your collections
        predictions_collection = db.predictions
        competitions_collection = db.competitions
        parameters_collection = db.parameters 
        print(f"Using MongoDB collection: {predictions_collection.name}")
        print(f"Using MongoDB collection: {competitions_collection.name}")
        print(f"Using MongoDB collection: {parameters_collection.name}")

    except ConnectionFailure as e:
        print(f"FATAL ERROR: Could not connect to MongoDB: {e}")
        
        # Set everything to None if connection failed
        mongo_client = None
        db = None
        predictions_collection = None
        competitions_collection = None
        parameters_collection = None
    except Exception as e:
        print(f"An unexpected error occurred during MongoDB connection: {e}")
        # Set everything to None on unexpected error
        mongo_client = None
        db = None
        predictions_collection = None
        competitions_collection = None
        parameters_collection = None
else:
    print("FATAL ERROR: MONGODB_URI environment variable not set. Cannot connect to MongoDB.")


    # --- Sample Data ---
DEFAULT_FIXTURE_URL_SAMPLE = "https://www.soccerstats.com/matches.asp?matchday=2&daym=tomorrow&matchdayn=104"
INITIAL_PREDICTION_PROMPT_SAMPLE = initial_predict_template
FINAL_PREDICTION_INSTRUCTION_SAMPLE = final_preddict_template 
POST_MATCH_INITIAL_PROMPT_SAMPLE = None
POST_MATCH_FINAL_PROMPT_SAMPLE = None
NUMBER_OF_PREDICTED_EVENTS_SAMPLE = 15
# Define sample rate limit values to insert
GEMINI_RPM_SAMPLE = 30
GEMINI_TPM_SAMPLE = 1000000
GEMINI_RPD_SAMPLE = 1500


# Sample Match Object
sample_match_object = {
    "competition": "England - Premier League",
    "date": "2025-04-20",
    "time": "14:00",
    "home_team": "Fulham",
    "away_team": "Chelsea",
    "stats_link": "https://www.soccerstats.com/pmatch.asp?league=england&stats=325-2-17-2025",
    "match_predictions": None,
    "post_match_analysis": None,
    "predict_status": False,
    "analysis_status": False
    }

# Sample Competition List
sample_competition_list = [
    {
        "name": "England - Premier League",
        "status": True
    },
    {
         "name": "Spain - La Liga",
        "status": False
    },
    {
        "name": "Germany - Bundesliga",
        "status": True
    }
]

# Sample Parameter Object
sample_parameter_object = {
    "fixture_url": DEFAULT_FIXTURE_URL_SAMPLE,
    "predict_initial_prompt": INITIAL_PREDICTION_PROMPT_SAMPLE,
    "predict_final_prompt": FINAL_PREDICTION_INSTRUCTION_SAMPLE,
    "post-match_initial_prompt": POST_MATCH_INITIAL_PROMPT_SAMPLE,
    "post-match_final_prompt": POST_MATCH_FINAL_PROMPT_SAMPLE,
    "number_of_predicted_events": NUMBER_OF_PREDICTED_EVENTS_SAMPLE,
    "rpm": GEMINI_RPM_SAMPLE,   # Added RPM
    "tpm": GEMINI_TPM_SAMPLE,   # Added TPM
    "rpd": GEMINI_RPD_SAMPLE    # Added RPD
}


# --- MongoDB Test Function ---
# This function is specifically for testing MongoDB connection and insertion.
async def test_mongodb_insertion():
    """
    Tests MongoDB connection and insertion with sample data across all collections.
    This function is for testing purposes only.
    """
    print("\n--- Running MongoDB Insertion Test ---")

    # Check if MongoDB is connected and collections are available
    # Using the global variables initialized in the startup-like block above
    global mongo_client, db, predictions_collection, competitions_collection, parameters_collection

  
    # Ensure all three collections are initialized by explicitly checking for None
    if mongo_client is None or db is None or predictions_collection is None or competitions_collection is None or parameters_collection is None:
        print("MongoDB client or collections not fully initialized. Cannot run test.")
        print("Please ensure MONGODB_URI is set in your .env file and MongoDB is running.")
        return
       


# --- Insert Sample Match Object ---
print("Attempting to insert sample match document into 'predictions' collection...")
try:
    insert_result_match = predictions_collection.insert_one(sample_match_object)
    print(f"Successfully inserted sample match document. ID: {insert_result_match.inserted_id}")
except Exception as e:
    print(f"Failed to insert sample match document: {e}")


# --- Insert Sample Competition List ---
print("\nAttempting to insert sample competition list into 'competitions' collection...")
try:
    insert_result_competitions = competitions_collection.insert_many(sample_competition_list)
    print(f"Successfully inserted {len(insert_result_competitions.inserted_ids)} sample competition documents.")
except Exception as e:
    print(f"Failed to insert sample competition list: {e}")

# --- Insert Sample Parameter Object ---
print("\nAttempting to insert sample parameter document into 'parameters' collection...")
try:
    insert_result_parameter = parameters_collection.insert_one(sample_parameter_object)
    print(f"Successfully inserted sample parameter document. ID: {insert_result_parameter.inserted_id}")
except Exception as e:
    print(f"Failed to insert sample parameter document: {e}")


print("\n--- MongoDB Insertion Test Complete ---")

# --- Main Execution Block for the Test Script ---
if __name__ == "__main__":
    
# This block runs the test function when you execute this script directly.
    async def run_test():
            
        # Allow the top-level initialization block (MongoDB connection) to run.
        # Just add a small delay to ensure it's had a chance to complete.
        await asyncio.sleep(2)

        # --- Run the MongoDB insertion test ---
        await test_mongodb_insertion()

        # Close the connection after the test (important for standalone scripts)
        global mongo_client
        if mongo_client:
            mongo_client.close()
            print("\nMongoDB connection closed after test.")


    # Use asyncio.run to start the async execution for the test
    asyncio.run(run_test())