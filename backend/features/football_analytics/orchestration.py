# backend/features/football_analytics/orchestration.py

# This file contains the core business logic and orchestration
# for the football analytics feature, including the prediction and post-match analysis workflows.
# It interacts with the scraper, analyzer, and database modules.

import datetime
from datetime import timedelta
import asyncio
import json # Needed for combining JSON and markdown
import traceback # Needed for logging exceptions

from typing import Dict, Any, List, Optional # Import type hints
from pymongo.collection import Collection # Import Collection for type hinting
from google import genai # Import genai for type hinting
from bson import ObjectId # Needed for fetching documents by ID


# --- Import modules from their locations ---
# Import scraper from THIS folder
from .services import scraper
# Import analyzer from THIS folder
from .services import analyzer
# Import database functions from db/ folder
from ...db import mongo_client as database # Adjusted import path
# Import shared utility functions
from ...shared import utils
# Import Settings class for type hinting
from ...config.settings import Settings


# --- Main Orchestration Logic (Pre-Match Prediction Process - Modified in Step 3) ---
# This function orchestrates the pre-match process.
async def run_full_prediction_process(
    settings: Settings, # Accept Settings object
    db_parameters: Dict[str, Any], # Accept DB parameters dictionary
    genai_client: genai.Client | None, # Accept AI client instance
    competitions_collection: Collection | None, # Accept competitions collection
    predictions_collection: Collection | None # Accept predictions collection
):
    """
    Background function to orchestrate scraping, analysis (pre-match), and saving to MongoDB.
    Receives configuration, clients, and collections.
    Calls scraper and analyzer with task_type="pre_match".
    Includes error handling and logging for each step.
    """
    print("Starting full pre-match prediction process in background...")

    # --- Check for essential components ---
    if settings is None or db_parameters is None or genai_client is None or competitions_collection is None or predictions_collection is None:
         print("Error: One or more critical components are missing for pre-match process.")
         print(f"Debug app.state check: settings is None: {settings is None}, db_parameters is None: {db_parameters is None}, genai_client is None: {genai_client is None}, competitions_collection is None: {competitions_collection is None}, predictions_collection is None: {predictions_collection is None}")
         print("Pre-match prediction process cannot proceed.")
         # Return a specific status indicating startup failure for the pre-match process
         return {"message": "Error: Critical components missing for pre-match process.", "status": "process_startup_failed_pre_match"}


    # --- Access configuration from parameters ---
    # Access specific parameters from the db_parameters dictionary.
    today_fixtures_url = db_parameters.get("today_fixture_url")
    tomorrow_fixtures_url = db_parameters.get("tomorrow_fixture_url")
    fetch_today = db_parameters.get("fetch_today", True) # Default to True

    # Placeholder access for pre-match specific parameters needed in analysis/validation (Will be selected based on task_type in analyzer)
    # These are used here for basic validation checks.
    initial_predict_prompt_template = db_parameters.get("predict_initial_prompt")
    final_predict_instruction_string = db_parameters.get("predict_final_prompt")
    match_prediction_schema = db_parameters.get("match_prediction_schema")

    rpm_limit = db_parameters.get("rpm") # Rate limit: Requests Per Minute
    rpd_limit = db_parameters.get("rpd") # Rate limit: Requests Per Day
    # tpm_limit = db_parameters.get("tpm") # TPM limit parameter (not strictly used in wait_for_rate_limit in utils)
    number_of_predicted_events = db_parameters.get("number_of_predicted_events")
    chunk_size_chars = db_parameters.get("chunk_size_chars")
    max_output_tokens = db_parameters.get("max_output_tokens")
    model_name = db_parameters.get("model")
    delay_between_matches = db_parameters.get("delay_between_matches", 15) # Default delay

    # Get AI Generation Parameters (Optional, default to None if missing)
    temperature = db_parameters.get("temperature", None)
    top_p = db_parameters.get("top_p", None)
    top_k = db_parameters.get("top_k", None)


    # --- Select Fixture URL and Calculate Target Date based on the 'fetch_today' flag ---
    selected_fixture_url = None
    target_match_date_str = None # Will be in DD-MM-YYYY format

    # Check if the URLs are present and are strings.
    if not isinstance(today_fixtures_url, str) or today_fixtures_url == "" or not isinstance(tomorrow_fixtures_url, str) or tomorrow_fixtures_url == "":
         print("Error: 'today_fixture_url' or 'tomorrow_fixture_url' parameters are missing, empty, or not strings in DB configuration.")
         return {"message": "Error: Missing or invalid fixture URLs in configuration.", "status": "failed_config_urls"} # Specific status

    # Use .get() with a default of True and explicitly check if the value retrieved is boolean True.
    if db_parameters.get("fetch_today", True) is True:
        selected_fixture_url = today_fixtures_url
        # Calculate today's date in DD-MM-YYYY format (using your preferred format)
        target_datetime = datetime.datetime.now()
        target_match_date_str = target_datetime.strftime('%d-%m-%Y')
        print(f"Fetching TODAY's matches from: {selected_fixture_url} (Date: {target_match_date_str})")
    else: # fetch_today is False or any other value indicating 'not today'
        selected_fixture_url = tomorrow_fixtures_url
        # Calculate tomorrow's date in DD-MM-YYYY format (using your preferred format)
        target_datetime = datetime.datetime.now() + timedelta(days=1)
        target_match_date_str = target_datetime.strftime('%d-%m-%Y')
        print(f"Fetching TOMORROW's matches from: {selected_fixture_url} (Date: {target_match_date_str})")


    # --- Check if required parameters for the process are available and valid ---
    # Using the simplified validation logic (this logic will be refined in a later step)
    missing_or_invalid = []

    # Check Date/URL parameters
    if not isinstance(today_fixtures_url, str) or today_fixtures_url == "":
        missing_or_invalid.append("today_fixture_url (missing, empty, or not string)")
    if not isinstance(tomorrow_fixtures_url, str) or tomorrow_fixtures_url == "":
         missing_or_invalid.append("tomorrow_fixture_url (missing, empty, or not string)")
    fetch_today_val = db_parameters.get("fetch_today")
    if fetch_today_val is not None and not isinstance(fetch_today_val, bool):
         missing_or_invalid.append(f"fetch_today (invalid type: {type(fetch_today_val)})")

    # Check essential Prompt/Schema parameters (specific to pre-match task)
    if not initial_predict_prompt_template or not isinstance(initial_predict_prompt_template, str):
        missing_or_invalid.append("predict_initial_prompt (missing or not string)")
    if not final_predict_instruction_string or not isinstance(final_predict_instruction_string, str):
        missing_or_invalid.append("predict_final_prompt (missing or not string)")
    if not match_prediction_schema or not isinstance(match_prediction_schema, dict):
        missing_or_invalid.append("match_prediction_schema (missing or not dictionary)")

    # Check numeric parameters
    if not isinstance(rpm_limit, (int, float)) or rpm_limit < 0: # Allow float for rpm/rpd
        missing_or_invalid.append("rpm (missing, not numeric, or negative)")
    if not isinstance(rpd_limit, (int, float)) or rpd_limit < 0: # Allow float for rpm/rpd
        missing_or_invalid.append("rpd (missing, not numeric, or negative)")
    if number_of_predicted_events is not None and (not isinstance(number_of_predicted_events, int) or number_of_predicted_events <= 0): # Allow None if optional
         missing_or_invalid.append("number_of_predicted_events (not integer or not positive)")
    if not isinstance(chunk_size_chars, int) or chunk_size_chars <= 0:
        missing_or_invalid.append("chunk_size_chars (missing, not integer, or not positive)")
    if max_output_tokens is not None and (not isinstance(max_output_tokens, int) or max_output_tokens <= 0): # Allow None if optional
        missing_or_invalid.append("max_output_tokens (not integer or not positive)")

    # Check model name
    if not model_name or not isinstance(model_name, str):
         missing_or_invalid.append("model (missing or not string)")

    # Check optional AI generation parameters if present but invalid type
    if temperature is not None and not isinstance(temperature, (int, float)):
        missing_or_invalid.append(f"temperature (invalid type: {type(temperature)})")
    if top_p is not None and not isinstance(top_p, (int, float)):
         missing_or_invalid.append(f"top_p (invalid type: {type(top_p)})")
    if top_k is not None and not isinstance(top_k, int):
         missing_or_invalid.append(f"top_k (invalid type: {type(top_k)})")


    # Also check if critical objects from app.state are None
    if settings is None or db_parameters is None or genai_client is None or competitions_collection is None or predictions_collection is None:
         missing_or_invalid.append("One or more critical components from app.state are None (settings, db_parameters, genai_client, collections).")


    # If any essential parameters are missing or invalid, log and return failed status.
    if missing_or_invalid:
        print("Error: Missing or invalid essential configuration parameters loaded from DB or app.state for running pre-match process.")
        print(f"Missing or invalid keys: {missing_or_invalid}")
        return {"message": "Error: Missing or invalid essential configuration parameters for pre-match process. Check database config and app.state.", "status": "failed_config_parameters"} # Specific status

    # --- End Parameter/Component Validation ---


    # --- Step 1: Fetch match fixtures (filtered by DB status) ---
    # Pass competitions_collection and the target date string
    fixtures = await scraper.fetch_matches_fixtures(selected_fixture_url, competitions_collection, target_match_date_str)

    if not fixtures:
        print("No fixtures found to process after scraping and filtering.")
        return {"message": "No fixtures found to process.", "status": "completed_no_fixtures"} # Specific status

    print(f"\nProcessing {len(fixtures)} matches...")

    successfully_processed_count = 0 # Counts matches successfully analyzed and saved
    failed_count = 0 # Counts matches that encountered errors during fetch/analysis/save

    # --- Step 2: Process each fixture ---
    for i, match_data_from_scrape in enumerate(fixtures):
        # Introduce a try-except block around individual match processing to prevent one match failure from stopping the whole process
        try:
            print(f"\n--- Processing Match {i + 1}/{len(fixtures)} ---")
            home_team = match_data_from_scrape.get('home_team', 'N/A')
            away_team = match_data_from_scrape.get('away_team', 'N/A')
            stats_link = match_data_from_scrape.get('stats_link', 'N/A')
            match_date = match_data_from_scrape.get('date', 'N/A') # Ensure this is the DD-MM-YYYY string
            match_time = match_data_from_scrape.get('time', 'N/A')
            competition = match_data_from_scrape.get('competition', 'N/A')

            print(f"Match: {home_team} vs {away_team} ({match_date})")

            # Prepare the base match document structure for saving prediction results or errors.
            match_document_base = {
                "competition": competition,
                "date": match_date, # Store the date string (DD-MM-YYYY)
                "time": match_time,
                "home_team": home_team,
                "away_team": away_team,
                "stats_link": stats_link,
                "predict_status": False,
                "post_match_analysis_status": False, # New field for post-match status
                "timestamp": datetime.datetime.utcnow(),
                "predictions": None,
                "post_match_analysis": None, # New field for post-match analysis result
                "error_details": None,
                "status": "pending_analysis", # Initial status
                "markdown_content": None # Initialize markdown_content field (saved on analysis failure)
            }


            # --- Check if match already exists and prediction is complete ---
            # This prevents re-predicting the same match if the script is run multiple times.
            # Query by unique combination of date, home team, away team.
            existing_match_query = {
                "date": match_date, # Use the date string
                "home_team": home_team,
                "away_team": away_team
            }
            existing_match = await database.find_one(predictions_collection, existing_match_query)

            # If an existing match document is found AND its predict_status is True, skip it.
            if existing_match and existing_match.get("predict_status", False) is True:
                 print(f"Match {home_team} vs {away_team} on {match_date} already exists with pre-match prediction complete. Skipping analysis.")
                 successfully_processed_count += 1 # Count as processed even if skipped
                 # Implement a delay before the next match processing loop iteration.
                 delay_between_matches_param = db_parameters.get("delay_between_matches", 15)
                 effective_delay_between_matches = delay_between_matches_param if isinstance(delay_between_matches_param, (int, float)) and delay_between_matches_param >= 0 else 15
                 if i < len(fixtures) - 1: # Only delay if it's not the last match
                     print(f"Waiting for {effective_delay_between_matches} seconds before the next match...")
                     await asyncio.sleep(effective_delay_between_matches)
                 continue # Skip to the next match in the loop


            # --- Step 3: Scrape match stats ---
            # Pass task_type="pre_match" to the scraper
            print("Fetching stats markdown for pre-match...")
            # Pass the stats_link and explicitly the task_type
            stats_markdown = await scraper.fetch_match_stats_markdown(stats_link, task_type="pre_match")


            if stats_markdown and isinstance(stats_markdown, str) and stats_markdown.strip():
                 print(f"Stats markdown fetched successfully. Length: {len(stats_markdown)}")
            else:
                 print("Stats fetch returned None, empty, or invalid markdown.")
                 # Prepare an error document for stats fetch failure
                 # This structure is used for both inserting a new doc or updating an existing incomplete one
                 stats_fetch_error_data = {
                     "predict_status": False, # Prediction failed
                     "status": "stats_fetch_failed",
                     "error_details": {"analysis_outcome": "Stats Fetch Failed", "details": "Failed to fetch stats markdown or received empty markdown."},
                     "markdown_content": None, # Markdown is None if fetch failed
                     "timestamp": datetime.datetime.utcnow() # Update timestamp
                 }
                 # Use the predictions_collection (should be available from app.state)
                 if predictions_collection is None:
                      print("Error: Predictions collection not available. Cannot save stats fetch error result.")
                      print("Stats fetch failed, but DB collection for saving is missing. Skipping save for this match.")
                      failed_count += 1
                 else:
                      # If an existing match document exists but prediction was NOT complete (e.g., previous stats_fetch_failed)
                      # UPDATE the existing document instead of inserting a new one.
                      if existing_match:
                           print(f"Existing match found for {home_team} vs {away_team} on {match_date} but prediction incomplete. Attempting to UPDATE with stats fetch failure status.")
                           # Use the update_one_by_id function (assuming it's added in mongo_client.py)
                           update_success = await database.update_one_by_id(predictions_collection, str(existing_match['_id']), stats_fetch_error_data)
                           if update_success:
                                print(f"Successfully updated existing match with stats fetch error for {home_team} vs {away_team}.")
                                failed_count += 1 # Count as failed analysis attempt
                           else:
                                print(f"Failed to update existing match with stats fetch error for {home_team} vs {away_team}.")
                                failed_count += 1
                      else:
                          # No existing document found or prediction incomplete, insert a new one with stats fetch failure status.
                          print(f"No existing incomplete match found for {home_team} vs {away_team} on {match_date}. Attempting to INSERT new document with stats fetch failure status.")
                          # Start with the base document structure and update it with failure data
                          new_match_document = match_document_base # Use the base structure defined earlier
                          new_match_document.update(stats_fetch_error_data) # Overlay failure data

                          insert_id = await database.insert_one(predictions_collection, new_match_document)
                          if insert_id:
                             print(f"Successfully saved match with stats fetch error for {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                             failed_count += 1 # Count as failed analysis attempt
                          else:
                             print(f"Warning: Failed to get inserted ID for match with stats fetch error {home_team} vs {away_team}.")
                             failed_count += 1

                 # Implement a delay before the next match processing loop iteration.
                 delay_between_matches_param = db_parameters.get("delay_between_matches", 15)
                 effective_delay_between_matches = delay_between_matches_param if isinstance(delay_between_matches_param, (int, float)) and delay_between_matches_param >= 0 else 15
                 if i < len(fixtures) - 1: # Only delay if it's not the last match
                     print(f"Waiting for {effective_delay_between_matches} seconds before the next match...")
                     await asyncio.sleep(effective_delay_between_matches)
                 continue # Skip to the next match in the loop


            # --- Step 4: Analyze stats with AI (Pre-Match Prediction) ---
            # Proceed with AI analysis only if stats markdown was fetched successfully and is not empty.
            print("Sending stats for AI analysis (pre-match)...")

            # Pass db_parameters and genai_client explicitly to analyzer
            # Pass task_type="pre-match" to the analyzer
            analysis_result = await analyzer.analyze_with_gemini(
                match_data=match_data_from_scrape,
                input_data=stats_markdown,
                db_parameters=db_parameters, # Pass DB parameters
                genai_client=genai_client, # Pass AI client
                task_type="pre_match" # Explicitly pass task type
            )


            # --- Step 5: Process analysis result and save to DB ---
            # Use the predictions_collection (should be available from app.state)
            if predictions_collection is None:
                 print("Error: Predictions collection not available. Cannot save analysis result.")
                 failed_count += 1
                 print("Analysis was attempted but DB collection for saving is missing. Skipping save for this match.")
                 # Implement a delay before the next match processing loop iteration.
                 delay_between_matches_param = db_parameters.get("delay_between_matches", 15)
                 effective_delay_between_matches = delay_between_matches_param if isinstance(delay_between_matches_param, (int, float)) and delay_between_matches_param >= 0 else 15
                 if i < len(fixtures) - 1: # Only delay if it's not the last match
                     print(f"Waiting for {effective_delay_between_matches} seconds before the next match...")
                     await asyncio.sleep(effective_delay_between_matches)
                 continue # Skip to the next match in the loop


            if isinstance(analysis_result, dict) and "error" not in analysis_result:
                # Analysis was successful
                print("AI analysis successful. Preparing document for MongoDB.")
                # Prepare update/insert data for success
                success_data = {
                    "predictions": analysis_result,
                    "predict_status": True,
                    "status": "analysis_complete", # Status indicates prediction is done
                    "error_details": None, # Clear any previous error details
                    "timestamp": datetime.datetime.utcnow(), # Update timestamp
                    "markdown_content": None # Ensure markdown is NOT saved on success
                }

                try:
                     # If an existing match document was found (even if prediction was incomplete), UPDATE it.
                     if existing_match:
                           print(f"Existing match found for {home_team} vs {away_team} on {match_date}. Attempting to UPDATE with successful analysis.")
                           # Use the update_one_by_id function (assuming it's added in mongo_client.py)
                           update_success = await database.update_one_by_id(predictions_collection, str(existing_match['_id']), success_data)
                           if update_success:
                                print(f"Successfully updated existing match with analysis for {home_team} vs {away_team}.")
                                successfully_processed_count += 1
                           else:
                                print(f"Failed to update existing match with analysis for {home_team} vs {away_team}.")
                                failed_count += 1
                     else:
                         # No existing document found, INSERT a new one.
                         print(f"No existing match found for {home_team} vs {away_team} on {match_date}. Attempting to INSERT new document with analysis.")
                         # Start with the base document structure and update it with success data
                         new_match_document = match_document_base # Use the base structure defined earlier
                         new_match_document.update(success_data) # Overlay failure data

                         insert_id = await database.insert_one(predictions_collection, new_match_document)
                         if insert_id:
                             print(f"Successfully saved match analysis for {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                             successfully_processed_count += 1
                         else:
                             print(f"Warning: Failed to get inserted ID for match {home_team} vs {away_team}.")
                             successfully_processed_count += 1 # Still count as processed if analysis was good but save failed

                except Exception as e:
                    print(f"Error saving/updating successful analysis for match {home_team} vs {away_team} on {match_date} to MongoDB: {e}")
                    # Include traceback for unexpected DB save/update errors
                    # The analysis result itself is valid, but couldn't be saved.
                    # We might want to capture the analysis result here too for debugging the save failure.
                    failed_count += 1
                    print(traceback.format_exc())


            else:
                # Analysis failed
                print(f"AI analysis failed for {home_team} vs {away_team} on {match_date}.")
                print("Analysis result:", analysis_result)

                # Prepare update/insert data for analysis failure
                failure_data = {
                     "predictions": None, # Ensure predictions is None on failure
                     "predict_status": False, # Prediction status is False
                     "status": "analysis_failed", # Status indicates analysis failed
                     "error_details": { # Capture error details from analyzer result
                         "analysis_outcome": analysis_result.get("error", "Unknown analysis error"),
                         "details": analysis_result.get("details", "N/A"),
                         "raw_output": analysis_result.get("raw_output", analysis_result.get('raw_response', 'N/A')), # Capture raw AI output if available
                         "finish_reason": analysis_result.get("finish_reason", "N/A") # Capture finish reason if available
                     },
                     "timestamp": datetime.datetime.utcnow(), # Update timestamp
                     "markdown_content": stats_markdown # --- Save markdown content on analysis failure as per requirements ---
                }

                try:
                     # If an existing match document was found (even if prediction was incomplete), UPDATE it.
                     if existing_match:
                           print(f"Existing match found for {home_team} vs {away_team} on {match_date} but prediction incomplete. Attempting to UPDATE with analysis failure status.")
                           # Use the update_one_by_id function (assuming it's added in mongo_client.py)
                           update_success = await database.update_one_by_id(predictions_collection, str(existing_match['_id']), failure_data)
                           if update_success:
                                print(f"Successfully updated existing match with analysis failure for {home_team} vs {away_team}.")
                                failed_count += 1
                           else:
                                print(f"Failed to update existing match with analysis failure for {home_team} vs {away_team}.")
                                failed_count += 1
                     else:
                          # No existing document found or prediction incomplete, insert a new one with analysis failure status.
                          print(f"No existing incomplete match found for {home_team} vs {away_team} on {match_date}. Attempting to INSERT new document with analysis failure status.")
                          # Start with the base document structure and update it with failure data
                          new_match_document = match_document_base # Use the base structure defined earlier
                          new_match_document.update(failure_data) # Overlay failure data

                          insert_id = await database.insert_one(predictions_collection, new_match_document)
                          if insert_id:
                             print(f"Successfully saved match with analysis error for {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                             failed_count += 1
                          else:
                             print(f"Warning: Failed to get inserted ID for match with analysis error {home_team} vs {away_team}.")
                             failed_count += 1


                except Exception as e:
                       print(f"Failed to save/update match with analysis error to MongoDB: {e}")
                       # Include traceback for unexpected DB save/update errors
                       failed_count += 1
                       print(traceback.format_exc())


            # Implement a delay between processing matches to avoid hammering services.
            # This delay is already handled at the start of the loop iteration IF we skipped the match.
            # It should also happen AFTER processing/saving a match.
            delay_between_matches_param = db_parameters.get("delay_between_matches", 15)
            effective_delay_between_matches = delay_between_matches_param if isinstance(delay_between_matches_param, (int, float)) and delay_between_matches_param >= 0 else 15

            if i < len(fixtures) - 1: # Only delay if it's not the last match in the fixture list
                print(f"Waiting for {effective_delay_between_matches} seconds before processing the next match...")
                await asyncio.sleep(effective_delay_between_matches)

        # End of individual match processing try block
        except Exception as match_e:
             # Catch any unexpected error during the processing of a *single* match
             print(f"An unexpected error occurred while processing match {i + 1}/{len(fixtures)}: {match_e}")
             print(traceback.format_exc())
             failed_count += 1 # Count this specific match as a failure due to unexpected error
             # We could attempt to log this to the DB document for the match if we had its ID,
             # but if the error happened before getting the ID, we just log locally.
             # For now, the global error handling will capture the overall process status.


    print("Background pre-match prediction process complete.")
    summary_message = f"Summary: {successfully_processed_count} matches successfully analyzed and saved, {failed_count} matches encountered errors during fetch/analysis/save."
    print(summary_message)

    # In a background task, you typically don't return a value.


# --- Post-Match Analysis Orchestration (Modified - Includes Steps 5, 6, 7, 8, 9, 10) ---
# This function contains the workflow for identifying, processing, and saving post-match analysis.
async def run_post_match_analysis_process(
    settings: Settings, # Accept Settings object
    db_parameters: Dict[str, Any], # Accept DB parameters dictionary
    genai_client: genai.Client | None, # Accept AI client instance
    predictions_collection: Collection | None, # Accept predictions collection
    target_date_str: str # Accept the target date string (DD-MM-YYYY)
):
    """
    Background function to orchestrate fetching post-match results, analysis,
    and updating existing match documents in MongoDB for a specific date.
    Uses refined error handling, logging, and status updates, including global error handling.
    """
    print(f"\nStarting post-match analysis process in background for date: {target_date_str}...")

    # --- Check for essential components ---
    if settings is None or db_parameters is None or genai_client is None or predictions_collection is None:
         print("Error: One or more critical components are missing for post-match process.")
         print(f"Debug app.state check: settings is None: {settings is None}, db_parameters is None: {db_parameters is None}, genai_client is None: {genai_client is None}, predictions_collection is None: {predictions_collection is None}")
         print("Post-match analysis process cannot proceed.")
         # Return a specific status indicating startup failure for the post-match process
         return {"message": "Error: Critical components missing for post-match analysis.", "status": "process_startup_failed_post_match"}

    # --- ADDED: Global Try block (Step 10) ---
    try:
        # --- Step 5: Query DB for matches ready for post-match analysis ---
        print(f"Querying DB for matches on {target_date_str} ready for post-match analysis...")

        # Define the query based on your specified criteria
        post_match_query = {
            "date": target_date_str, # Match the specific date (DD-MM-YYYY)
            "predict_status": True, # Ensure pre-match prediction is complete
            "post_match_analysis_status": False, # Ensure post-match analysis is NOT complete
            "post_match_analysis": None # Ensure the post_match_analysis field is None or does not exist
        }

        try:
            # Use database.find_many to get the list of potential matches
            # We need _id and stats_link, predictions from the query result for later steps
            # Added 'predictions' field to the projection for efficiency
            matches_to_analyze = await database.find_many(
                predictions_collection, post_match_query, 
                options={"projection": {
                    "_id": 1, 
                    "stats_link": 1, 
                    "home_team": 1, 
                    "away_team": 1, 
                    "date": 1, 
                    "predictions": 1}})

            if not matches_to_analyze:
                print(f"No matches found on {target_date_str} matching post-match analysis criteria.")
                print("Post-match analysis process complete (no matches to process).")
                return {"message": f"No matches found on {target_date_str} ready for post-match analysis.", "status": "completed_no_matches"} # Refined status

            print(f"Found {len(matches_to_analyze)} matches on {target_date_str} ready for post-match analysis.")
            # print(f"Debug: Matches found: {[f'{m.get("home_team")} vs {m.get("away_team")}' for m in matches_to_analyze]}") # Optional debug print list of matches

        except Exception as e:
            # This catch block handles errors specifically from the initial DB query
            print(f"Error querying database for post-match analysis matches on {target_date_str}: {e}")
            print(traceback.format_exc()) # Include traceback for DB query errors
            print("Post-match analysis process failed during initial database query.")
            # Return a specific status indicating DB query failure
            return {"message": f"Error querying database for post-match analysis matches on {target_date_str}.", "status": "process_db_query_failed"}


        # --- Step 6, 7, 8, 9: Process each match ready for post-match analysis (Combined Steps with Refinements) ---
        print(f"\nProcessing {len(matches_to_analyze)} matches for post-match analysis...")

        successfully_processed_count = 0 # Counts matches successfully analyzed and updated in DB
        skipped_count = 0 # Counts matches skipped due to missing initial data (link/predictions)
        failed_count = 0 # Counts matches that hit an error during fetch, input prep, analysis, or update save

        # Get delay parameter (re-use from pre-match, as it's a shared config)
        delay_between_matches = db_parameters.get("delay_between_matches", 15) # Default delay
        effective_delay_between_matches = delay_between_matches if isinstance(delay_between_matches, (int, float)) and delay_between_matches >= 0 else 15


        for i, match_document in enumerate(matches_to_analyze): # Iterate through the documents from find_many projection
            # match_document is a dictionary from the find_many result (with projection fields: _id, stats_link, home_team, away_team, date, predictions)
            match_id_str: Optional[str] = str(match_document.get('_id')) if match_document.get('_id') else None # Get the ID string, handle missing ID
            home_team = match_document.get('home_team', 'N/A') # Get from projection
            away_team = match_document.get('away_team', 'N/A') # Get from projection
            match_date = match_document.get('date', 'N/A') # Should be target_date_str, get from projection
            stats_link = match_document.get('stats_link') # Get from projection
            original_predictions_json = match_document.get('predictions') # Get predictions from projection


            print(f"\n--- Processing Post-Match Analysis for Match {i + 1}/{len(matches_to_analyze)}: {home_team} vs {away_team} ({match_date}) (ID: {match_id_str}) ---")

            # Skip this match if the ID is somehow missing from the document (shouldn't happen with projection but safety check)
            if match_id_str is None:
                 print(f"Error: Document found without an _id. Skipping this entry.")
                 skipped_count += 1
                 # We cannot update this document if it has no ID. Log and continue.
                 continue # Skip to next match


            # --- Validate essential data from the projection (Step 9 Refinement) ---
            if not stats_link or not isinstance(stats_link, str):
                 print(f"Error: Stats link is missing or invalid in document for match ID {match_id_str}. Skipping analysis for this match.")
                 skipped_count += 1
                 # UPDATE the existing document with a specific skipped status
                 update_data = {
                      "post_match_analysis_status": False,
                      "status": "post_analysis_skipped_no_link", # Specific status for missing link
                      "error_details": {"analysis_outcome": "Post-Match Skipped", "details": "Stats link missing or invalid in DB document."},
                      "timestamp": datetime.datetime.utcnow()
                 }
                 # Attempt to update the document with the skipped status
                 try:
                     await database.update_one_by_id(predictions_collection, match_id_str, update_data)
                     print(f"Updated document for match ID {match_id_str} with status '{update_data['status']}'.")
                 except Exception as db_e:
                     print(f"Error updating document for match ID {match_id_str} after skipping due to missing link: {db_e}")
                     print(traceback.format_exc())

                 continue # Skip to next match

            if original_predictions_json is None or not isinstance(original_predictions_json, dict):
                 print(f"Error: Original predictions JSON is missing or not a dictionary in document for match ID {match_id_str}. Skipping analysis for this match.")
                 skipped_count += 1
                 # UPDATE the existing document with a specific skipped status
                 update_data = {
                      "post_match_analysis_status": False,
                      "status": "post_analysis_skipped_no_predictions", # Specific status for missing predictions
                      "error_details": {"analysis_outcome": "Post-Match Skipped", "details": "Original predictions JSON missing or invalid in DB document."},
                      "timestamp": datetime.datetime.utcnow()
                 }
                 # Attempt to update the document with the skipped status
                 try:
                     await database.update_one_by_id(predictions_collection, match_id_str, update_data)
                     print(f"Updated document for match ID {match_id_str} with status '{update_data['status']}'.")
                 except Exception as db_e:
                      print(f"Error updating document for match ID {match_id_str} after skipping due to missing predictions: {db_e}")
                      print(traceback.format_exc())

                 continue # Skip to next match

            print(f"Stats link from DB: {stats_link}")
            # print(f"Original predictions JSON keys: {list(original_predictions_json.keys()) if original_predictions_json else 'N/A'}") # Optional debug print keys


            # --- Call scraper for post-match results (Step 6) ---
            # Pass the stats_link and explicitly the task_type="post_match"
            print("Fetching post-match results markdown...")
            post_match_markdown = await scraper.fetch_match_stats_markdown(stats_link, task_type="post_match")

            # --- Process scraper result (Step 9 Refinement) ---
            if not (post_match_markdown and isinstance(post_match_markdown, str) and post_match_markdown.strip()):
                print("Post-match results fetch returned None, empty, or invalid markdown. Skipping analysis for this match.")
                failed_count += 1 # Count as failed
                # UPDATE the existing document with an error status for post-match analysis fetch failure
                update_data = {
                     "post_match_analysis_status": False,
                     "status": "post_analysis_fetch_failed", # Specific status for fetch failure
                     "error_details": {"analysis_outcome": "Post-Match Fetch Failed", "details": "Failed to fetch post-match results markdown from stats link."},
                     "timestamp": datetime.datetime.utcnow()
                }
                # Attempt to update the document with the fetch failed status
                try:
                    await database.update_one_by_id(predictions_collection, match_id_str, update_data)
                    print(f"Updated document for match ID {match_id_str} with status '{update_data['status']}'.")
                except Exception as db_e:
                    print(f"Error updating document for match ID {match_id_str} after fetch failure: {db_e}")
                    print(traceback.format_exc())

                continue # Skip to next match

            print(f"Post-match results markdown fetched successfully. Length: {len(post_match_markdown)}")


            # --- Step 7: Combine input and call analyzer ---
            print("Combining predictions JSON and post-match markdown for analyzer input...")

            try:
                # Convert predictions dictionary to a formatted JSON string
                predictions_json_string = json.dumps(original_predictions_json, indent=2)
                # Combine the JSON string and the markdown with clear headers
                combined_input_string = f"PRE-MATCH PREDICTIONS:\n{predictions_json_string}\n\nPOST-MATCH STATS:\n\n{post_match_markdown}"
                print(f"Combined input string prepared. Length: {len(combined_input_string)}")

            except Exception as e:
                 print(f"Error combining input data for match ID {match_id_str}: {e}")
                 print(traceback.format_exc())
                 failed_count += 1 # Count as failed
                 # UPDATE the existing document with an error status for input combining failure
                 update_data = {
                      "post_match_analysis_status": False,
                      "status": "post_analysis_input_failed", # Specific status for input prep failure
                      "error_details": {"analysis_outcome": "Post-Match Input Prep Failed", "details": f"Error combining input data: {e}"},
                      "timestamp": datetime.datetime.utcnow()
                 }
                 # Attempt to update the document with the input failed status
                 try:
                     await database.update_one_by_id(predictions_collection, match_id_str, update_data)
                     print(f"Updated document for match ID {match_id_str} with status '{update_data['status']}'.")
                 except Exception as db_e:
                      print(f"Error updating document for match ID {match_id_str} after input combining failure: {db_e}")
                      print(traceback.format_exc())

                 continue # Skip to next match


            # --- Call analyzer for post-match analysis (Step 9 Refinement - added try/except) ---
            print("Sending combined data for AI analysis (post-match)...")
            analysis_result = None # Initialize analysis_result before the try block
            try:
                 # Pass the combined input string and explicitly the task_type="post_match"
                 # Pass the original match document (or relevant parts) and db_parameters/genai_client
                 analysis_result = await analyzer.analyze_with_gemini(
                     match_data=match_document, # Pass the match document (or relevant parts)
                     input_data=combined_input_string, # Pass the combined input string
                     db_parameters=db_parameters, # Pass DB parameters
                     genai_client=genai_client, # Pass AI client
                     task_type="post_match" # Explicitly pass task type
                 )
            except Exception as e:
                 # Catch unexpected exceptions from the analyzer call itself
                 print(f"Unexpected error calling analyzer for match ID {match_id_str}: {e}")
                 print(traceback.format_exc())
                 # Create an error dictionary format similar to analyzer's expected error return
                 analysis_result = {"error": f"Unexpected error during analyzer call: {e}", "details": str(e), "status": "post_analysis_analyzer_exception"} # Specific status for analyzer exception


            # --- Step 8 & 9: Process analyzer result and prepare for DB update (Refined Logic) ---
            print(f"Processing analyzer result for match ID {match_id_str}...")

            # Default update data for failure case, will be overwritten if analysis is successful
            update_data: Dict[str, Any] = {
                 "post_match_analysis": None, # Ensure post_match_analysis is None on failure
                 "post_match_analysis_status": False, # Keep status as False
                 "status": "post_analysis_failed", # Default status for failed post-match analysis
                 "error_details": { # Default capture of error details
                     "analysis_outcome": "Unknown post-match analysis error",
                     "details": "Analyzer returned unexpected result or had an internal error.",
                     "raw_output": "N/A",
                     "finish_reason": "N/A",
                     "block_reason": "N/A" # Ensure block_reason is always present
                 },
                 "timestamp": datetime.datetime.utcnow(), # Update timestamp
                 # markdown_content is not updated here.
            }

            if isinstance(analysis_result, dict) and "error" not in analysis_result:
                # Analysis was successful (returned a dictionary without an 'error' key)
                print("AI analysis successful. Preparing document for MongoDB update.")
                update_data = {
                    "post_match_analysis": analysis_result, # Save the successful analysis result
                    "post_match_analysis_status": True, # Set status to True
                    "status": "post_analysis_complete", # New status for successful post-match analysis
                    "error_details": None, # Clear any previous error details
                    "timestamp": datetime.datetime.utcnow() # Update timestamp
                }
                # successfully_processed_count increment happens after successful DB update

            else:
                # Analysis failed (returned an error dictionary or unexpected format)
                print(f"AI analysis failed for match ID {match_id_str}.")
                print("Analysis result:", analysis_result)
                # failed_count increment happens after DB update attempt

                # Capture error details more specifically if available in the analysis_result dict
                if isinstance(analysis_result, dict):
                     update_data["error_details"] = {
                         "analysis_outcome": analysis_result.get("error", update_data["error_details"]["analysis_outcome"]),
                         "details": analysis_result.get("details", update_data["error_details"]["details"]),
                         "raw_output": analysis_result.get("raw_output", analysis_result.get('raw_response', update_data["error_details"]["raw_output"])),
                         "finish_reason": analysis_result.get("finish_reason", update_data["error_details"]["finish_reason"]),
                         "block_reason": analysis_result.get("block_reason", update_data["error_details"]["block_reason"]) # Capture block reason specifically
                     }
                     # If analyzer returned a specific status in the error dict, use it
                     if "status" in analysis_result and isinstance(analysis_result["status"], str):
                         update_data["status"] = analysis_result["status"] # Allow analyzer to set a more specific failure status


            # --- Step 9: Update the document in MongoDB and handle update result ---
            print(f"Attempting to update document for match ID {match_id_str} with post-match analysis result...")
            try:
                update_success = await database.update_one_by_id(predictions_collection, match_id_str, update_data)

                if update_success:
                     print(f"Successfully updated document for match ID {match_id_str} with status '{update_data.get('status', 'N/A')}'.")
                     # Increment counters based on the analysis outcome that was successfully saved
                     if update_data.get("post_match_analysis_status") is True:
                          successfully_processed_count += 1
                     else: # If post_match_analysis_status is False after update (meaning it was a failure status)
                          failed_count += 1

                else:
                     # If DB update fails, this is a critical failure for this match's process
                     print(f"CRITICAL WARNING: Failed to update document for match ID {match_id_str} in MongoDB after analysis attempt.")
                     print("DB Update data attempted:", update_data)
                     # Increment failed count as the final result could not be saved.
                     # If analysis had succeeded, that success is now unrecorded.
                     failed_count += 1

            except Exception as e:
                # Handle case where update_one_by_id call itself raised an exception
                print(f"CRITICAL ERROR: Exception during database update call for match ID {match_id_str}: {e}")
                print(traceback.format_exc())
                print("DB Update data attempted:", update_data)
                failed_count += 1 # Count as a failure


            # Implement a delay between processing matches.
            # Only delay if it's not the last match in the list
            if i < len(matches_to_analyze) - 1:
                print(f"Waiting for {effective_delay_between_matches} seconds before processing the next match...")
                await asyncio.sleep(effective_delay_between_matches)


        print("\nPost-match analysis process loop completed.")

        # --- Final logging and return (Success path of global try) ---
        # Summary counts are now calculated within the loop based on successful DB updates.
        summary_message = f"Post-match analysis process for {target_date_str} finished. Summary: {successfully_processed_count} successfully analyzed and updated, {skipped_count} skipped (data missing), {failed_count} failed (fetch/input/analysis/update save)."
        print(summary_message)
        # Return a detailed summary dictionary
        return {"message": summary_message, "status": "completed", "date": target_date_str, "successfully_processed": successfully_processed_count, "skipped": skipped_count, "failed": failed_count}


    # --- ADDED: Global Except block (Step 10) ---
    except Exception as e:
        # This catch block handles any unexpected errors that occur outside the specific per-match handling
        global_error_message = f"An unexpected global error occurred during post-match analysis process for date {target_date_str}: {e}"
        print(global_error_message)
        print(traceback.format_exc()) # Include traceback for global errors
        # Return a global error status with details
        return {"message": global_error_message, "status": "process_global_failure", "date": target_date_str, "error_details": str(e), "traceback": traceback.format_exc()}


# --- ADDED: Function to Fetch Post-Match Analysis Results by Date/ID (Step 11) ---
async def fetch_post_match_analysis_results(
    predictions_collection: Collection | None, # Accept predictions collection
    target_date_str: Optional[str] = None, # Optional target date string (DD-MM-YYYY)
    match_id_str: Optional[str] = None # Optional specific match ID string
) -> List[Dict[str, Any]] | Dict[str, Any] | None:
    """
    Fetches post-match analysis results from the database.
    Can fetch results for a specific date OR a specific match ID.
    Returns a list of documents for a date query, a single document for an ID query, or None if collection is missing/error.
    """
    print(f"\nFetching post-match analysis results from DB for date: {target_date_str}, ID: {match_id_str}")

    if predictions_collection is None:
        print("Error: Predictions collection not available for fetching results.")
        return None # Indicate critical dependency missing

    query: Dict[str, Any] = {}
    # Only fetch documents where post_match_analysis_status is True (successful analysis)
    query["post_match_analysis_status"] = True

    if match_id_str:
        # If a specific ID is provided, query by ID
        print(f"Fetching result for single match ID: {match_id_str}")
        try:
            # Ensure the ID string is a valid ObjectId before querying
            object_id = ObjectId(match_id_str)
            query["_id"] = object_id
            # Use find_one for a single document lookup
            result = await database.find_one(predictions_collection, query)
            if result:
                 # Convert ObjectId to string for easier JSON serialization
                 result['_id'] = str(result['_id'])
                 print(f"Found single result for ID {match_id_str}.")
            else:
                 print(f"No result found for ID {match_id_str} with post_match_analysis_status: True.")
            return result # Return the single document or None

        except Exception as e:
            # Catch errors during ObjectId conversion or find_one call
            print(f"Error fetching single result for ID {match_id_str}: {e}")
            print(traceback.format_exc())
            return None # Indicate error during fetch


    elif target_date_str:
        # If a date is provided, query by date
        print(f"Fetching results for date: {target_date_str}")
        query["date"] = target_date_str
        # Use find_many for multiple documents
        try:
            # Fetch all documents matching the date and status criteria
            results = await database.find_many(predictions_collection, query)
            # Convert ObjectIds to strings for easier JSON serialization
            for doc in results:
                 doc['_id'] = str(doc['_id'])

            print(f"Found {len(results)} results for date {target_date_str} with post_match_analysis_status: True.")
            return results # Return list of documents

        except Exception as e:
            # Catch errors during find_many call
            print(f"Error fetching results for date {target_date_str}: {e}")
            print(traceback.format_exc())
            return None # Indicate error during fetch

    else:
        # Neither ID nor date provided
        print("No date or match ID provided for fetching post-match analysis results.")
        return [] # Return empty list if no criteria provided


# --- End of run_post_match_analysis_process ---
# --- End of fetch_post_match_analysis_results ---