import asyncio
import os
import uvicorn
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

# --- Import modules ---
from . import database
from . import scraper
from . import analyzer
# DO NOT import prompt or ai_output_schema here.
# Prompts and schemas are read from database parameters.

# Import dotenv for loading environment variables
from dotenv import load_dotenv

# Import google.generativeai for initializing the client
import google.generativeai as genai

# Import the ObjectId type if needed for handling MongoDB IDs in results
# from bson.objectid import ObjectId

# --- Load environment variables from .env file ---
load_dotenv()

# --- Global Configuration Variables ---
# These will be populated on application startup by reading from the database.
parameters_config: dict | None = None # Holds parameters read from the DB (including schemas and model name)
gemini_model_instance: genai.GenerativeModel | None = None # Holds the initialized Gemini model instance
competitions_collection = None # Holds the competitions collection object from MongoDB


# --- FastAPI App Instance ---
app = FastAPI()

# --- CORS Middleware ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Be more specific in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Application Startup Event ---
# This runs when uvicorn starts the application.
@app.on_event("startup")
async def startup_event():
    """Actions to run on application startup."""
    print("Application startup initiated.")

    # --- Step 1: Connect to MongoDB and get collection references ---
    await database.connect_to_mongo()
    # Get the competitions collection reference needed by the scraper
    global competitions_collection
    competitions_collection = database.get_competitions_collection()

    # --- Get parameters collection reference ---
    params_collection = database.get_parameters_collection()


    # --- Step 2: Load parameters (including schemas and model name) from the database ---
    global parameters_config
    if params_collection is None:
        print("FATAL ERROR: Parameters collection not initialized. Cannot load configuration.")
        parameters_config = None # Keep as None if collection is not available
    else:
        try:
            # Find the single parameter document (assuming there's only one or we take the first)
            print("Attempting to load parameters from the database...")
            parameter_document = await database.find_one(params_collection, {}) # Use find_one to get the single document

            if parameter_document:
                parameters_config = parameter_document
                print("Parameters successfully loaded from database.")
                # --- Debug print loaded parameters (optional) ---
                # import json
                # print(f"Loaded parameters: {json.dumps(parameters_config, indent=2)}")
            else:
                print("FATAL ERROR: No parameter document found in the database. Configuration loading failed.")
                parameters_config = None # Keep as None if document not found


        except Exception as e:
            print(f"FATAL ERROR: Error loading parameters from database: {e}")
            parameters_config = None # Keep as None on error


    # --- Step 3: Initialize Gemini Client using model name from parameters ---
    global gemini_model_instance
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

    if GEMINI_API_KEY and parameters_config and parameters_config.get("model"):
        try:
            print("Attempting to initialize Gemini client...")
            genai.configure(api_key=GEMINI_API_KEY)
            # Get the model name from the loaded parameters
            GEMINI_MODEL_NAME = parameters_config.get("model")
            if GEMINI_MODEL_NAME:
                gemini_model_instance = genai.GenerativeModel(GEMINI_MODEL_NAME)
                print(f"Gemini client initialized with model: {GEMINI_MODEL_NAME}.")
            else:
                print("Warning: 'model' key not found in loaded parameters. Gemini client not initialized.")
                gemini_model_instance = None

        except Exception as e:
            print(f"Error initializing Gemini client on startup: {e}")
            gemini_model_instance = None
    elif not GEMINI_API_KEY:
        print("Warning: GEMINI_API_KEY environment variable not set. Gemini client not initialized.")
        gemini_model_instance = None
    else: # parameters_config is None or does not have 'model' key
        print("Warning: Parameters not loaded or 'model' key missing. Cannot initialize Gemini client.")
        gemini_model_instance = None


    # --- Check if critical components are initialized ---
    if parameters_config is None or gemini_model_instance is None or competitions_collection is None:
        print("FATAL ERROR: Critical startup components failed to initialize.")
        # Depending on how critical, you might raise an exception here to prevent the app from starting
        # raise RuntimeError("Critical startup initialization failed.")
        pass # Allow app to start but endpoints relying on these will fail


    print("Application startup complete.")


# --- Application Shutdown Event ---
# This runs when uvicorn is shutting down.
@app.on_event("shutdown")
async def shutdown_event():
    """Actions to run on application shutdown."""
    print("Application shutdown initiated.")
    # Close the MongoDB connection
    await database.close_mongo_connection()
    print("Application shutdown complete.")


# --- Main Orchestration Logic (Example: Pre-Match Prediction Process) ---
# This function orchestrates the full process using the other modules.
# It reads configuration from the global parameters_config.
async def run_full_prediction_process():
    """Main function to orchestrate the scraping, analysis (pre-match), and saving to MongoDB."""

    print("Starting full pre-match prediction process...")

    # --- Access configuration from loaded parameters ---
    # Check if parameters_config is loaded and has expected keys
    global parameters_config, gemini_model_instance, competitions_collection
    if parameters_config is None:
         print("Error: Parameters not loaded on startup. Cannot run process.")
         return {"message": "Error: Configuration not loaded.", "status": "failed"}

    # Get parameters, including prompts, schemas, and rate limits
    fixture_url = parameters_config.get("fixture_url")
    initial_predict_prompt_template = parameters_config.get("predict_initial_prompt") # Get template string
    final_predict_instruction_string = parameters_config.get("predict_final_prompt") # Get string
    match_prediction_schema = parameters_config.get("prediction_schema") # Get schema dictionary
    # Get rate limits and prediction count
    rpm_limit = parameters_config.get("rpm")
    rpd_limit = parameters_config.get("rpd")
    tpm_limit = parameters_config.get("tpm")
    number_of_predicted_events = parameters_config.get("number_of_predicted_events")
    chunk_size_chars = parameters_config.get("chunk_size_chars") # --- NEW PARAMETER ---
    # Model name is used during initialization, not passed to analyzer typically

    # Check if required parameters are available
    if not fixture_url or not initial_predict_prompt_template or not final_predict_instruction_string or not match_prediction_schema or rpm_limit is None or rpd_limit is None or number_of_predicted_events is None or chunk_size_chars is None:
         print("Error: Missing essential configuration parameters loaded from DB.")
         # Print missing keys for debugging
         missing_keys_check = {
             "fixture_url": fixture_url,
             "predict_initial_prompt": initial_predict_prompt_template,
             "predict_final_prompt": final_predict_instruction_string,
             "prediction_schema": match_prediction_schema,
             "rpm": rpm_limit,
             "rpd": rpd_limit,
             "number_of_predicted_events": number_of_predicted_events,
             "chunk_size_chars": chunk_size_chars # Include the new key
         }
         missing = [k for k, v in missing_keys_check.items() if v is None]
         print(f"Missing or None keys: {missing}")

         return {"message": "Error: Missing essential configuration.", "status": "failed"}

    if gemini_model_instance is None:
        print("Error: Gemini client not initialized. Cannot run analysis.")
        return {"message": "Error: AI client not initialized.", "status": "failed"}

    if competitions_collection is None:
         print("Error: Competitions collection not available. Cannot filter fixtures.")
         return {"message": "Error: Database collection not available.", "status": "failed"}


    # --- Step 1: Fetch match fixtures (filtered by DB status) ---
    # Pass the fixture_url from parameters and the competitions_collection object
    fixtures = await scraper.fetch_matches_fixtures(fixture_url, competitions_collection)

    if not fixtures:
        print("No fixtures found to process after scraping and filtering.")
        return {"message": "No fixtures found to process.", "status": "completed"}

    print(f"\nProcessing {len(fixtures)} matches...")

    processed_count = 0
    failed_count = 0
    results = []

    # --- Step 2: Process each fixture ---
    for i, match_data_from_scrape in enumerate(fixtures):
        print(f"\n--- Processing Match {i + 1}/{len(fixtures)} ---")
        home_team = match_data_from_scrape.get('home_team', 'N/A')
        away_team = match_data_from_scrape.get('away_team', 'N/A')
        stats_link = match_data_from_scrape.get('stats_link', 'N/A')

        print(f"Match: {home_team} vs {away_team}")

        # --- Construct the initial document structure (will be updated with analysis results) ---
        match_document = {
            "competition": match_data_from_scrape.get('competition', 'N/A'),
            "date": match_data_from_scrape.get('date', 'N/A'),
            "time": match_data_from_scrape.get('time', 'N/A'),
            "home_team": home_team,
            "away_team": away_team,
            "stats_link": stats_link,
            "match_predictions": None, # Placeholder for analysis result
            "post_match_analysis": None, # Placeholder for future post-match analysis
            "predict_status": False, # Indicates if prediction was attempted/successful
            "analysis_status": False # Indicates if post-match analysis was attempted/successful
        }


        # --- Step 3: Scrape match stats ---
        stats_markdown = await scraper.fetch_match_stats_markdown(stats_link)


        # --- Step 4: Analyze stats with AI (Pre-Match Prediction) ---
        if stats_markdown:
            print("Sending stats for AI analysis...")

            # --- Format the initial prediction prompt string ---
            # Use the template and parameters loaded from the database
            try:
                # Format the initial prompt string with dynamic data
                formatted_initial_prompt_string = initial_predict_prompt_template.format(
                    home_team=home_team,
                    away_team=away_team,
                    number_of_predicted_events=number_of_predicted_events
                    # Add other format placeholders if needed in the future
                )
                print("Initial prediction prompt formatted.")
            except KeyError as e:
                 print(f"Error formatting initial prediction prompt: Missing key {e}. Using raw template.")
                 formatted_initial_prompt_string = initial_predict_prompt_template # Use raw template if formatting fails
            except Exception as e:
                 print(f"An unexpected error occurred formatting initial prediction prompt: {e}. Using raw template.")
                 formatted_initial_prompt_string = initial_predict_prompt_template # Use raw template if formatting fails


            # Call the analyzer function, passing all necessary parameters
            # The analyzer function receives the schema dictionary from here.
            analysis_result = await analyzer.analyze_with_gemini(
                model=gemini_model_instance, # Pass the initialized model instance
                input_data=stats_markdown, # Pass the markdown input
                initial_prompt_string=formatted_initial_prompt_string, # Pass the FORMATTED initial prompt string
                final_instruction_string=final_predict_instruction_string, # Pass the final instruction string (from params)
                output_schema=match_prediction_schema, # Pass the prediction schema DICTIONARY (from params)
                rpm_limit=rpm_limit, # Pass rate limits from parameters
                rpd_limit=rpd_limit,
                tpm_limit=tpm_limit,
                # number_of_predicted_events is used in prompt formatting, not directly by analyzer logic
                chunk_size_chars=chunk_size_chars # --- NEW PARAMETER ---
            )

            # --- Step 5: Process analysis result and save to DB ---
            predictions_collection = database.get_predictions_collection() # Get predictions collection reference
            if predictions_collection is None:
                 print("Error: Predictions collection not available. Cannot save analysis result.")
                 # Decide how to handle - fail process or continue? Let's log and continue.
                 failed_count += 1
                 result_status = "Analysis Successful, Save Failed (Collection not available)"
                 results.append({"match": f"{home_team} vs {away_team}", "status": result_status})
                 # Add a delay between matches, even on failure, to avoid overwhelming systems
                 if i < len(fixtures) - 1: await asyncio.sleep(10)
                 continue


            if analysis_result and "error" not in analysis_result:
                print("AI analysis successful. Preparing document for MongoDB.")
                match_document["match_predictions"] = analysis_result
                match_document["predict_status"] = True
                processed_count += 1
                result_status = "Analysis Successful"

                try:
                    # Use the insert_one function from the database module
                    insert_id = await database.insert_one(predictions_collection, match_document)
                    if insert_id:
                         print(f"Successfully saved match {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                         result_status += " (Saved)"
                    else:
                         print(f"Failed to get inserted ID for match {home_team} vs {away_team}.")
                         result_status += " (Save Attempted, No ID)"

                except Exception as e: # Catching generic Exception here for simplicity, refine later
                    print(f"Error saving match {home_team} vs {away_team} to MongoDB: {e}")
                    failed_count += 1
                    result_status += f" (Save Failed: {e})"

            else:
                print(f"AI analysis failed for {home_team} vs {away_team}.")
                # Store error details in the document
                match_document["match_predictions"] = {
                    "error_details": analysis_result.get("error", "Unknown analysis error"),
                    "raw_output": analysis_result.get("raw_output", "N/A") # Include raw output for debugging
                }
                failed_count += 1
                result_status = f"Analysis Failed: {analysis_result.get('error', 'Unknown')}"
                # Still attempt to save the document with error details
                try:
                     insert_id = await database.insert_one(predictions_collection, match_document)
                     if insert_id:
                        print(f"Saved match with analysis error {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                        result_status += " (Saved with error details)"
                     else:
                         print(f"Failed to get inserted ID for match with analysis error {home_team} vs {away_team}.")
                         result_status += " (Save Attempted, No ID)"

                except Exception as e:
                       print(f"Failed to save match with analysis error to MongoDB: {e}")
                       result_status += f" (Save Failed: {e})"


        else:
            print(f"Skipping analysis and saving for {home_team} vs {away_team} due to failed stats fetch.")
            failed_count += 1
            result_status = "Stats Fetch Failed"
            match_document["match_predictions"] = {"error_details": "Failed to fetch stats"}
            # Still attempt to save the document with stats fetch error details
            predictions_collection = database.get_predictions_collection() # Get predictions collection reference
            if predictions_collection is None:
                 print("Error: Predictions collection not available. Cannot save stats fetch error result.")
                 result_status += " (Save Failed: Collection not available)"
            else:
                 try:
                      insert_id = await database.insert_one(predictions_collection, match_document)
                      if insert_id:
                         print(f"Saved match with stats fetch error {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                         result_status += " (Saved with error details)"
                      else:
                         print(f"Failed to get inserted ID for match with stats fetch error {home_team} vs {away_team}.")
                         result_status += " (Save Attempted, No ID)"
                 except Exception as e:
                       print(f"Failed to save match with stats fetch error to MongoDB: {e}")
                       result_status += f" (Save Failed: {e})"


        results.append({
            "match": f"{home_team} vs {away_team}",
            "status": result_status
        })

        # Add a delay between processing matches
        if i < len(fixtures) - 1:
            delay_between_matches = 10 # Delay in seconds
            print(f"Waiting for {delay_between_matches} seconds before processing the next match...")
            await asyncio.sleep(delay_between_matches)

    print("\n--- Pre-Match Prediction Process Complete ---")
    summary_message = f"Summary: {processed_count} matches processed and saved successfully, {failed_count} matches encountered errors during fetch/analysis/save."
    print(summary_message)

    return {"message": summary_message, "results": results}


# --- FastAPI Endpoints ---
# Define your API endpoints here. They will call the orchestration logic.

# Example Endpoint to trigger the pre-match prediction process
@app.get("/run-predictions")
async def run_predictions_endpoint():
    """Endpoint to trigger the full pre-match prediction process."""
    # Check if critical components are initialized before allowing the endpoint to run
    global parameters_config, gemini_model_instance, competitions_collection
    if parameters_config is None or gemini_model_instance is None or competitions_collection is None:
         print("Endpoint /run-predictions called before critical startup components were ready.")
         raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Backend not fully initialized. Parameters, AI client, or DB collections not available."
         )

    # Run the orchestration process and return its result
    process_result = await run_full_prediction_process()
    return process_result


# You will define other endpoints here for post-match analysis,
# fetching predictions from the DB for the frontend, etc.
# Example: Endpoint to get predictions from the DB
# @app.get("/predictions")
# async def get_predictions_endpoint():
#     predictions_collection = database.get_predictions_collection()
#     if predictions_collection is None:
#          raise HTTPException(
#             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
#             detail="Database predictions collection not available."
#          )
#     try:
#         # Fetch recent predictions (e.g., limit 20, sort by date/time)
#         # Use find_many from database module
#         # from bson import ObjectId # Import ObjectId if you need to convert IDs to strings
#         recent_predictions_cursor = await database.find_many(predictions_collection, {}, options={"limit": 20, "sort": [("date", -1), ("time", 1)]})
#         # Convert ObjectId to string for JSON serialization if necessary
#         # for doc in recent_predictions_cursor:
#         #     if '_id' in doc and isinstance(doc['_id'], ObjectId):
#         #         doc['_id'] = str(doc['_id'])
#         return recent_predictions_cursor
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Error fetching predictions: {e}"
#         )


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
        host="0.0.0.0", # Listen on all available interfaces
        port=8000,      # Default FastAPI port
        reload=True     # Auto-reload code on changes (for development)
    )

    # If you were NOT using uvicorn.run here and wanted to test startup/shutdown manually:
    # async def main_dev_run_manual():
    #      print("Running manual startup/shutdown sequence...")
    #      await startup_event()
    #      print("Manual startup complete. App is notionally running.")
    #      # Keep the script alive or run test logic here
    #      # await run_full_prediction_process() # Example manual trigger
    #      print("Manual test/process complete.")
    #      await shutdown_event()
    #      print("Manual shutdown complete.")
    #
    # try:
    #     # Use asyncio.run to execute the manual async sequence
    #     asyncio.run(main_dev_run_manual())
    # except KeyboardInterrupt:
    #     print("\nManual run interrupted. Exiting.")
    #     # Manual shutdown call might be needed here if interrupted before shutdown_event
    #     # global mongo_client
    #     # if mongo_client:
    #     #      mongo_client.close()
    #     pass