# backend/main.py

import asyncio                                                              # For asynchronous operations
import os                                                                   # For accessing environment variables
import uvicorn                                                              # For running the FastAPI server
from fastapi import FastAPI, HTTPException, status, BackgroundTasks         # FastAPI core components, BackgroundTasks for the background process
from fastapi.middleware.cors import CORSMiddleware                          # Middleware for handling Cross-Origin Resource Sharing
import json                                                                 # Import json to pretty print params config for debugging
import datetime                                                             # Import datetime for timestamp
from datetime import timedelta # Already imported by datetime               # Import timedelta for fixture fetching date calculation if needed in main.py
from google import genai

# --- Import backend modules ---
from . import database                                                      # Assuming your database module handles MongoDB connection and collection access
from . import scraper                                                       # Assuming your scraper module contains data fetching functions (fixtures, stats markdown)
from . import analyzer                                                  # Assuming your analyzer module contains AI interaction logic (analyze_with_gemini)


from dotenv import load_dotenv

# --- Load environment variables from .env file ---
load_dotenv()                                                           # Ensure you have a .env file in your project root directory with GEMINI_API_KEY and MONGODB_URI set.


# --- Global Configuration Variables ---
parameters_config: dict | None = None                                       # Dictionary to hold configuration parameters loaded from the database document

competitions_collection = None                                      # Keep the global competition_collection reference if your scraper or other parts of the application need it. It's populated during database connection.

# --- NEW GENAI CLIENT INSTANCE ---
genai_client: genai.Client | None = None


# --- FastAPI App Instance ---
app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],                            # Allows requests from any origin (be cautious with "*" in production; list specific origins instead).
    allow_credentials=True,                         # Allows cookies, authorization headers, etc. to be included in cross-origin requests.
    allow_methods=["*"],                        # Allows all standard HTTP methods (GET, POST, PUT, DELETE, etc.).
    allow_headers=["*"],                        # Allows all standard HTTP headers to be included in cross-origin requests.
)


# --- Application Startup Event ---
# This asynchronous function runs automatically once when the FastAPI application starts up (e.g., when uvicorn is run).
# It's used for initializing resources that the application needs, like database connections and external clients.
@app.on_event("startup")
async def startup_event():
    """Actions to run on application startup: Connect to DB, load config, initialize AI client."""
    print("Application startup initiated.")

    global competitions_collection, parameters_config, genai_client
    
    # --- Step 1: Connect to MongoDB and get collection references ---
    
    await database.connect_to_mongo()               # Calls the connect_to_mongo function in the database module to establish MongoDB connection and set its global client/manager/collection references.
    competitions_collection = database.get_competitions_collection()            # Access the competitions collection via the database module's getter function
    params_collection = database.get_parameters_collection()                    # Access the parameters collection via the database module's getter function


    # --- Step 2: Load parameters (including schemas and model name) from the database ---  # The 'global parameters_config' is declared at the top now.
    if params_collection is None:
        print("FATAL ERROR: Parameters collection not initialized. Cannot load configuration.")
        parameters_config = None                                # Ensure parameters_config is None if the collection wasn't initialized, indicating a critical failure.
    else:
        try:
            print("Attempting to load parameters from the database...")
            parameter_document = await database.find_one(params_collection, {})

            if parameter_document:
                
                parameters_config = parameter_document              # Store the loaded parameters dictionary in the global parameters_config variable.
                print("Parameters successfully loaded from database.")


            else:
                print("FATAL ERROR: No parameter document found in the database. Configuration loading failed.")
                parameters_config = None 

        except Exception as e:
            print(f"FATAL ERROR: Error loading parameters from database: {e}")
            parameters_config = None # Ensure parameters_config is None if loading fails, indicating a critical configuration error.


    # --- Step 3: Initialize Gemini Client using the NEW google.genai library (as in user's working example) ---
    if parameters_config:                                                               # Proceed with AI client initialization only if parameters were successfully loaded.
        try:
            model_name_for_print = parameters_config.get("model", "Unknown Model")          # Get the model name from the loaded parameters for the print statement. Use .get() with a default value for safety in case the 'model' key is missing.
            print(f"Attempting to initialize Gemini client for model: {model_name_for_print} using google.genai...")

            GEMINI_API_KEY_VALUE = os.environ.get("GEMINI_API_KEY")

            if GEMINI_API_KEY_VALUE:
                genai_client = genai.Client(api_key=GEMINI_API_KEY_VALUE)           # Pass the key explicitly to the Client constructor using the new library. The 'global genai_client' is declared at the top now.
                print(f"Gemini client initialized successfully.")
            else:
                 # Handle the case where the GEMINI_API_KEY environment variable is NOT set.
                 print("FATAL ERROR: GEMINI_API_KEY environment variable not set during client initialization.")
                 print("Please ensure the GEMINI_API_KEY environment variable is set correctly in your environment.")
                 genai_client = None 

        except Exception as e:
            print(f"FATAL ERROR: Error initializing Gemini client: {e}")
            genai_client = None 


    else:
         print("FATAL ERROR: Parameters configuration not loaded, skipping Gemini client initialization.")
         genai_client = None 

    # --- Check if critical components are initialized ---
    if parameters_config is None or genai_client is None or competitions_collection is None or database.mongo_client is None or database.get_predictions_collection() is None or database.get_parameters_collection() is None:
        print("FATAL ERROR: One or more critical startup components failed to initialize.")
        pass # Allow the FastAPI application to start, but functionality relying on failed components will be unavailable.

    print("Application startup complete.") # Log the completion of the application startup event.


# --- Application Shutdown Event ---
# This asynchronous function runs automatically when the FastAPI application is shutting down.
# It's used for cleaning up resources, like closing database connections.
@app.on_event("shutdown")
async def shutdown_event():
    """Actions to run on application shutdown: Close DB connection."""
    print("Application shutdown initiated.")
    await database.close_mongo_connection()          # Calls the close_mongo_connection function in the database module to close the MongoDB client connection.
    print("Application shutdown complete.")


# --- Root Endpoint ---
# Basic GET endpoint at the root URL ("/") to check if the FastAPI application is running and accessible.
@app.get("/")
async def read_root():
    return {"message": "Football Analysis Backend is running."}


# --- Endpoint to Trigger Analysis and Predictions ---
# This POST endpoint triggers the full pre-match prediction process in a background task.
# Using BackgroundTasks prevents the HTTP request from blocking until the long-running process completes, allowing for a quick response.
@app.post("/run-predictions") 
async def run_predictions_endpoint(background_tasks: BackgroundTasks):
    """Endpoint to trigger the full pre-match prediction process in the background."""
    # Before starting the background task, perform quick checks to ensure necessary components were initialized during startup.

    if database.mongo_client is None or database.get_predictions_collection() is None or database.get_parameters_collection() is None or competitions_collection is None: # Check mongo_client and collection getters, and global competitions_collection
        print("Endpoint /run-predictions called before database components were ready.")
        # Raise a 503 Service Unavailable error if critical database components are not initialized.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backend database components not initialized. Cannot start prediction process.")

    if genai_client is None:
        print("Endpoint /run-predictions called before AI client was ready.")
        # Raise a 503 Service Unavailable error if the AI client is not initialized.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backend AI client not initialized. Ensure GEMINI_API_KEY environment variable is set and parameters loaded successfully on startup.")

    # Check if the global parameters_config variable was populated during startup.
    if parameters_config is None:
        print("Endpoint /run-predictions called before parameters configuration was loaded.")
        # Raise a 503 Service Unavailable error if the parameters configuration is not loaded.
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Parameters configuration not loaded. Cannot start prediction process.")


    # If all critical components are initialized, add the prediction process function (run_full_prediction_process) to background tasks.
    # This allows the endpoint to return an immediate response while the potentially long-running process runs in the background,
    # preventing the HTTP request from timing out.
    # The background task function (run_full_prediction_process) will access necessary
    # configuration and clients from the global variables populated during startup.
    background_tasks.add_task(
        run_full_prediction_process,
        # Since run_full_prediction_process accesses globals directly in this structure, no arguments are explicitly passed here from the endpoint.
    )

    # Return an immediate success response indicating the task has been successfully started in the background.
    return {"message": "Prediction process started in the background. Check server logs for progress and results saved to DB."}


# --- Main Orchestration Logic (Pre-Match Prediction Process) ---
# This asynchronous function contains the core logic for fetching data, running AI analysis, and saving results.
# It is intended to be run as a background task, orchestrated by the /run-predictions endpoint.
# It accesses necessary configuration and clients (AI client, DB collections) from global variables populated during startup.
async def run_full_prediction_process():
    """
    Background function to orchestrate the scraping, analysis (pre-match), and saving to MongoDB.
    Accesses configuration and clients from global variables populated during application startup.
    Logs progress and saves results (successful analysis or errors) to the database.
    """

    print("Starting full pre-match prediction process in background...")

    # --- Access configuration and clients from global variables ---
    global parameters_config, genai_client, competitions_collection

    # Access the predictions collection reference from the database module (needed later for saving)
    # Get it here at the start for clarity and potentially use in initial checks if needed.
    predictions_collection_instance = database.get_predictions_collection()
    # Access the parameters collection reference from the database module (needed for parameter reload in future, but accessed globally here)
    params_collection_instance = database.get_parameters_collection() # Keep reference if needed


    # --- Check if critical components are available (redundant check here, but adds robustness) ---
    if parameters_config is None:
         print("Error: Parameters not loaded on startup. Cannot run process.")
         return {"message": "Error: Configuration not loaded.", "status": "failed"} # Return early on error if config is missing

    # Check for the new genai_client global
    if genai_client is None:
        print("Error: AI client not initialized. Cannot run analysis.")
        return {"message": "Error: AI client not initialized.", "status": "failed"} # Return early on error if AI client is missing

    # Check for necessary database components
    if database.mongo_client is None or competitions_collection is None or predictions_collection_instance is None or params_collection_instance is None: # Check mongo_client and collection instances
         print("Error: Database components not fully available. Cannot run process.")
         # Print specific missing components for better debugging if needed
         print(f"Debug DB Check: mongo_client is None: {database.mongo_client is None}, competitions_collection is None: {competitions_collection is None}, predictions_collection is None: {predictions_collection_instance is None}, parameters_collection is None: {params_collection_instance is None}")
         return {"message": "Error: Database components not available.", "status": "failed"} # Return early on error if DB is missing


    # --- Get parameters needed for this specific process run ---
    fixture_url = parameters_config.get("fixture_url") # URL for fetching fixture list
    initial_predict_prompt_template = parameters_config.get("predict_initial_prompt") # Template string for the initial prompt
    final_predict_instruction_string = parameters_config.get("predict_final_prompt") # Final instruction string to trigger JSON output
    match_prediction_schema = parameters_config.get("match_prediction_schema") # Schema dictionary for JSON output structure
    rpm_limit = parameters_config.get("rpm") # Rate limit: Requests Per Minute
    rpd_limit = parameters_config.get("rpd") # Rate limit: Requests Per Day
    # tpm_limit = parameters_config.get("tpm") # Rate limit: Tokens Per Minute (not strictly used in wait_for_rate_limit in this version)
    number_of_predicted_events = parameters_config.get("number_of_predicted_events") # Number of events requested in prompt template
    chunk_size_chars = parameters_config.get("chunk_size_chars") # Chunk size parameter for splitting string input (markdown)
    max_output_tokens = parameters_config.get("max_output_tokens") # Max output tokens parameter for AI GenerationConfig
    model_name = parameters_config.get("model") # Get the model name string (e.g., "gemini-2.0-flash", "gemini-1.5-pro-latest") - This is needed by the rate limiter helper in the NEW analyzer.py.
    delay_between_matches = parameters_config.get("delay_between_matches", 15) # Delay in seconds between processing each match, default 15s


    # --- Check if required parameters for the process are available and valid ---
    is_config_valid = (
        fixture_url is not None and fixture_url != "" # fixture_url must be a non-empty string
        and initial_predict_prompt_template is not None and initial_predict_prompt_template != "" # initial_predict_prompt_template must be a non-empty string
        and final_predict_instruction_string is not None and final_predict_instruction_string != "" # final_predict_instruction_string must be a non-empty string
        and match_prediction_schema is not None and isinstance(match_prediction_schema, dict) and match_prediction_schema # match_prediction_schema must be a non-empty dictionary
        and rpm_limit is not None and isinstance(rpm_limit, int) and rpm_limit >= 0 # rpm_limit must be a non-negative integer
        and rpd_limit is not None and isinstance(rpd_limit, int) and rpd_limit >= 0 # rpd_limit must be a non-negative integer
        and number_of_predicted_events is not None and isinstance(number_of_predicted_events, int) and number_of_predicted_events > 0 # number_of_predicted_events must be a positive integer
        and chunk_size_chars is not None and isinstance(chunk_size_chars, int) and chunk_size_chars > 0 # chunk_size_chars must be a positive integer
        and max_output_tokens is not None and isinstance(max_output_tokens, int) and max_output_tokens > 0 # max_output_tokens must be a positive integer
        and model_name is not None and isinstance(model_name, str) and model_name != "" # model_name must be a non-empty string for rate limiter helper
    )

    if not is_config_valid:
         print("Error: Missing or invalid essential configuration parameters loaded from DB for running process.")
         # List the keys that are missing, empty string, or empty dict/invalid type for better debugging.
         missing_or_invalid = [k for k, v in parameters_config.items() if k in ["fixture_url", "predict_initial_prompt", "predict_final_prompt", "match_prediction_schema", "rpm", "rpd", "number_of_predicted_events", "chunk_size_chars", "max_output_tokens", "model"] and (v is None or (isinstance(v, str) and v == '') or (isinstance(v, dict) and not v) or (k in ["rpm", "rpd", "number_of_predicted_events", "chunk_size_chars", "max_output_tokens"] and not (isinstance(v, int) and v > 0 if k in ["number_of_predicted_events", "chunk_size_chars", "max_output_tokens"] else isinstance(v, int) and v >= 0)) or (k == "model" and not isinstance(v, str) and v != ""))] # Complex check including model_name

         print(f"Missing or invalid essential keys: {missing_or_invalid}")

         return {"message": "Error: Missing or invalid essential configuration parameters for running process. Check database config.", "status": "failed"}


    # --- Step 1: Fetch match fixtures (filtered by DB status) ---
    fixtures = await scraper.fetch_matches_fixtures(fixture_url, competitions_collection)

    if not fixtures:
        print("No fixtures found to process after scraping and filtering.")
        # Return completed status even if no fixtures found, it's not a failure state of the process itself.
        return {"message": "No fixtures found to process.", "status": "completed"}

    print(f"\nProcessing {len(fixtures)} matches...")

    processed_count = 0 # Counter for successfully processed matches
    failed_count = 0 # Counter for matches that encountered errors


    # --- Step 2: Process each fixture ---
    # Loop through each fetched match fixture (each item in the 'fixtures' list).
    for i, match_data_from_scrape in enumerate(fixtures):
        print(f"\n--- Processing Match {i + 1}/{len(fixtures)} ---")
        # Use .get() with default values for safety when accessing match_data_from_scrape dictionary keys.
        home_team = match_data_from_scrape.get('home_team', 'N/A')
        away_team = match_data_from_scrape.get('away_team', 'N/A')
        stats_link = match_data_from_scrape.get('stats_link', 'N/A')
        match_date = match_data_from_scrape.get('date', 'N/A') # Get date for the database document
        match_time = match_data_from_scrape.get('time', 'N/A') # Get time for the database document
        competition = match_data_from_scrape.get('competition', 'N/A') # Get competition for the database document


        print(f"Match: {home_team} vs {away_team}")

        # Prepare the base match document structure for saving prediction results or errors to the database.
        # This document will be inserted into the predictions collection.
        match_document_base = {
            "competition": competition,
            "date": match_date,
            "time": match_time,
            "home_team": home_team,
            "away_team": away_team,
            "stats_link": stats_link,
            # Initialize prediction/analysis fields or status markers.
            "predict_status": False, # Set prediction status to False initially
            "post_match_analysis_status": False, # Set analysis status to False initially (for post-match if implemented)
            "timestamp": datetime.datetime.utcnow(), # Add a timestamp for when this analysis was attempted
            # Add placeholders for analysis data or error details
            "predictions": None,   #for predictions analysis by AI
            "post_match_analysis": None, #for post match analysis of result by Ai
            "error_details": None,
            "status": "pending_analysis" # Initial status
        }


        # --- Step 3: Scrape match stats ---
        # Call the scraper function to get detailed match stats as markdown from the stats link.
        # This should return a string or None.
        stats_markdown = await scraper.fetch_match_stats_markdown(stats_link)
        if stats_markdown:
             print(f"Markdown Length: {len(stats_markdown)}")
        else:
             print("Stats fetch returned None or empty markdown.")


        # --- Step 4: Analyze stats with AI (Pre-Match Prediction) ---
        # Proceed with AI analysis only if stats markdown was fetched successfully and is not empty.
        if stats_markdown and isinstance(stats_markdown, str) and stats_markdown.strip(): # Check if it's a non-empty string after stripping whitespace
            print("Sending stats for AI analysis...")

            # Pass match_data, stats_markdown, parameters_config, and genai_client to the analyzer function.
            analysis_result = await analyzer.analyze_with_gemini(
                match_data=match_data_from_scrape, # Pass original match data (dictionary) for prompt formatting inside analyzer
                input_data=stats_markdown, # Pass the markdown input (string)
                parameters_config=parameters_config, # Pass the full parameters config dictionary loaded globally
                genai_client=genai_client # Pass the initialized global google-genai client instance
            )


            # --- Step 5: Process analysis result and save to DB ---
            # Get the predictions collection reference again (safety check, though global should be set)
            predictions_collection_instance = database.get_predictions_collection()
            if predictions_collection_instance is None:
                 print("Error: Predictions collection not available. Cannot save analysis result.")
                 failed_count += 1 # Increment failed count as we cannot save the result
                 # Log the failure but cannot save the specific result for this match if the collection is not available.
                 print("Analysis was attempted but DB collection for saving is missing. Skipping save for this match.")
                 continue # Skip saving for this match and move to the next if DB is not ready

            # Check if the analysis_result is a dictionary AND does NOT contain an 'error' key.
            if isinstance(analysis_result, dict) and "error" not in analysis_result:
                # Analysis was successful (analyze_with_gemini returned the parsed JSON dictionary)
                print("AI analysis successful. Preparing document for MongoDB.")
                # Update the base document with the analysis data and status fields.
                match_document_base["predictions"] = analysis_result # Store the AI's parsed JSON output under the 'analysis_data' key
                match_document_base["predict_status"] = True # Set prediction status to successful (boolean True)
                match_document_base["status"] = "analysis_complete" # Set an overall status for the document

                try:
                    # Use the database module's insert_one function, passing the collection instance.
                    insert_id = await database.insert_one(predictions_collection_instance, match_document_base)
                    if insert_id:
                         print(f"Successfully saved match analysis for {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                         processed_count += 1 # Increment processed count only on successful save
                    else:
                         # Log a warning if inserting didn't return an ID (might depend on the MongoDB driver/version used).
                         print(f"Warning: Failed to get inserted ID for match {home_team} vs {away_team}.")
                         # Depending on how critical getting an ID is, you might count this as a partial failure.
                         # For now, we'll assume the document was likely saved if no exception was raised.
                         processed_count += 1 # Still count as processed if no exception


                except Exception as e:
                    # Log an error if saving the successful analysis to the database fails (e.g., network error to DB).
                    print(f"Error saving successful analysis for match {home_team} vs {away_team} to MongoDB: {e}")
                    failed_count += 1 # Count as a failed process due to save error
                    # You might want to add more robust error handling here, like saving to a different collection or retrying the save.


            else:
                # Analysis failed or analyze_with_gemini returned an error dictionary or unexpected type
                print(f"AI analysis failed for {home_team} vs {away_team}.")
                # Print the analysis_result returned by analyze_with_gemini for debugging.
                print("Analysis result:", analysis_result) # This will print the error dictionary or unexpected return value

                # Update the base document with the error details and failure status fields.
                match_document_base["analysis_data"] = None # Clear analysis_data field as analysis failed

                # Check if analysis_result is a dictionary and has error/details keys, otherwise provide default failure info
                if isinstance(analysis_result, dict):
                     # Store the error dictionary under 'error_details', including raw output if available from the analyzer error dictionary
                     match_document_base["error_details"] = {
                         "analysis_outcome": analysis_result.get("error", "Unknown analysis error"),
                         "details": analysis_result.get("details", "N/A"), # Include nested details if available
                         "raw_output": analysis_result.get("raw_output", analysis_result.get('raw_response', 'N/A')), # Include raw output/response from analyzer error dict
                         "finish_reason": analysis_result.get("finish_reason", "N/A") # Include finish reason if available
                     }
                else:
                     # Handle cases where analysis_result is not a dictionary (e.g., a simple error string)
                     match_document_base["error_details"] = {
                          "analysis_outcome": "Unexpected analysis function return type or value",
                          "details": f"Analyzer returned: {analysis_result}", # Store the raw return value
                          "raw_output": analysis_result, # Store the raw return value as raw output
                          "finish_reason": "N/A"
                     }

                match_document_base["predict_status"] = False # Set prediction status to failed (boolean False)
                match_document_base["status"] = "analysis_failed" # Set an overall status for the document


                # Still attempt to save the document with error details for debugging purposes, even though analysis failed.
                try:
                     # Use the database module's insert_one function, passing the collection instance.
                     insert_id = await database.insert_one(predictions_collection_instance, match_document_base)
                     if insert_id:
                        print(f"Saved match with analysis error for {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                        failed_count += 1 # Count as failed only after save attempt
                     else:
                         # Log a warning if inserting didn't return an ID.
                         print(f"Warning: Failed to get inserted ID for match with analysis error {home_team} vs {away_team}.")
                         failed_count += 1 # Count as failed if no exception but no ID


                except Exception as e:
                       # Log an error if saving the failure details to the database fails.
                       print(f"Failed to save match with analysis error details to MongoDB: {e}")
                       failed_count += 1 # Count as failed if save fails


        else:
            # Stats fetch failed or markdown was empty - log this and save failure status.
            print(f"Skipping analysis and saving for {home_team} vs {away_team} due to failed stats fetch or empty markdown.")
            failed_count += 1 # Count as a failed process

            # Prepare a document indicating stats fetch failure.
            stats_fetch_error_document = {
                "competition": competition,
                "date": match_date,
                "time": match_time,
                "home_team": home_team,
                "away_team": away_team,
                "stats_link": stats_link,
                "timestamp": datetime.datetime.utcnow(),
                "status": "stats_fetch_failed", # Indicate stats fetch failure status
                "error_details": {"analysis_outcome": "Stats Fetch Failed", "details": "Failed to fetch stats markdown or received empty markdown."}
            }
            # Get the predictions collection reference again (safety check)
            predictions_collection_instance = database.get_predictions_collection()
            if predictions_collection_instance is None:
                 print("Error: Predictions collection not available. Cannot save stats fetch error result.")
                 # Log the failure but cannot save if collection is None.
                 print("Stats fetch failed, but DB collection for saving is missing. Skipping save for this match.")
            else:
                 try:
                      # Use the database module's insert_one function, passing the collection instance.
                      insert_id = await database.insert_one(predictions_collection_instance, stats_fetch_error_document)
                      if insert_id:
                         print(f"Successfully saved match with stats fetch error for {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                      else:
                         # Log a warning if inserting didn't return an ID.
                         print(f"Warning: Failed to get inserted ID for match with stats fetch error {home_team} vs {away_team}.")
                 except Exception as e:
                       # Log an error if saving the stats fetch failure details to the database fails.
                       print(f"Failed to save match with stats fetch error to MongoDB: {e}")


        # Implement a delay between processing matches to avoid hammering services (scraper, AI API).
        # Get delay parameter from parameters_config_dict, defaulting to 15 seconds if parameter is missing or invalid.
        # Ensure the delay value is a number and non-negative.
        delay_between_matches_param = parameters_config.get("delay_between_matches", 15)
        effective_delay_between_matches = delay_between_matches_param if isinstance(delay_between_matches_param, (int, float)) and delay_between_matches_param >= 0 else 15

        if i < len(fixtures) - 1: # Apply delay BETWEEN matches, not after the very last match in the list.
            print(f"Waiting for {effective_delay_between_matches} seconds before processing the next match...")
            await asyncio.sleep(effective_delay_between_matches)


    print("Background pre-match prediction process complete.") # Log completion of the background task.
    # Log a summary message at the end of the process run.
    summary_message = f"Summary: {processed_count} matches successfully analyzed and saved, {failed_count} matches encountered errors during fetch/analysis/save."
    print(summary_message)

    # In a background task, you typically don't return a value that's used by an HTTP response.
    # The results are saved to the DB. The log message provides the summary.

# --- End of run_full_prediction_process ---


# You will define other endpoints here for post-match analysis,
# fetching predictions from the DB for the frontend, etc.
# Example: Endpoint to get predictions from the DB
# @app.get("/predictions")
# async def get_predictions_endpoint():
#     predictions_collection_instance = database.get_predictions_collection() # Use the getter
#     if predictions_collection_instance is None:
#          raise HTTPException(
#             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
#             detail="Database predictions collection not available."
#          )
#     try:
#         # Fetch recent predictions (e.g., limit 20, sort by date/time)
#         # Use find_many from database module, passing the collection instance
#         # from bson import ObjectId # Import ObjectId if you need to convert IDs to strings
#         recent_predictions_cursor = await database.find_many(predictions_collection_instance, {}, options={"limit": 20, "sort": [("date", -1), ("time", 1)]})
#         # Convert ObjectId to string for JSON serialization if necessary
#         # for doc in recent_predictions_cursor:
#         #     if '_id' in doc and isinstance(doc['_id'], ObjectId):
#         #         doc['_id'] = str(doc['_id'])
#         return recent_predictions_cursor
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Error fetching predictions: {e}"
#         )


# --- Main Execution Block for running via `python main.py` ---
if __name__ == "__main__":
    # This block is primarily for development convenience.
    # In production, you typically run via `uvicorn main:app`.

    # Note: Running this file directly with `python main.py` might behave differently
    # regarding startup/shutdown events compared to running with `uvicorn backend.main:app`.
    # Uvicorn is the recommended way to run a FastAPI application.

    print("Starting FastAPI server with uvicorn...")
    # Running uvicorn programmatically. Uvicorn handles the startup and shutdown events.
    uvicorn.run(
        "backend.main:app", # Specify the package and app
        host="0.0.0.0",      # Listen on all available interfaces
        port=8000,           # Default FastAPI port
        reload=True          # Auto-reload code on changes (for development)
    )

    # If you were NOT using uvicorn.run here and wanted to test startup/shutdown manually:
    # async def main_dev_run_manual():
    #     print("Running manual startup/shutdown sequence...")
    #     await startup_event()
    #     print("Manual startup complete. App is notionally running.")
    #     # Keep the script alive or run test logic here
    #     # await run_full_prediction_process() # Example manual trigger
    #     # print("Manual test/process complete.")
    #     # await shutdown_event()
    #     # print("Manual shutdown complete.")
    #
    # try:
    #     # Use asyncio.run to execute the manual async sequence
    #     asyncio.run(main_dev_run_manual())
    # except KeyboardInterrupt:
    #     print("\nManual run interrupted. Exiting.")
    #     # Manual shutdown call might be needed here if interrupted before shutdown_event
    #     # global mongo_client
    #     # if mongo_client:
    #     #     mongo_client.close()
    #     pass