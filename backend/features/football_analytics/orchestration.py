# backend/features/football_analytics/services.py

# This file contains the core business logic and orchestration
# for the football analytics feature, specifically the prediction process workflow.

import datetime
from datetime import timedelta
import asyncio
from typing import Dict, Any
from pymongo.collection import Collection # Import Collection for type hinting
from google import genai # Import genai for type hinting

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


# --- Main Orchestration Logic (Pre-Match Prediction Process - Modified to accept params) ---
async def run_full_prediction_process(
    settings: Settings, # Accept Settings object
    db_parameters: Dict[str, Any], # Accept DB parameters dictionary
    genai_client: genai.Client, # Accept AI client instance
    competitions_collection: Collection, # Accept collections
    predictions_collection: Collection
):
    """
    Background function to orchestrate scraping, analysis (pre-match), and saving to MongoDB.
    Receives configuration, clients, and collections as parameters.
    Logs progress and saves results (successful analysis or errors) to the database,
    including saving markdown on analysis failure as per requirements.
    Selects fixture URL and calculates target date based on 'fetch_today' flag in db_parameters.
    Reads AI generation parameters from db_parameters.
    """

    print("Starting full pre-match prediction process in background...")

    # --- Access configuration from parameters ---
    # Access specific parameters from the db_parameters dictionary.
    today_fixtures_url = db_parameters.get("today_fixture_url")
    tomorrow_fixtures_url = db_parameters.get("tomorrow_fixture_url")
    fetch_today = db_parameters.get("fetch_today", True)

    initial_predict_prompt_template = db_parameters.get("predict_initial_prompt")
    final_predict_instruction_string = db_parameters.get("predict_final_prompt")
    match_prediction_schema = db_parameters.get("match_prediction_schema")
    rpm_limit = db_parameters.get("rpm") # Rate limit: Requests Per Minute
    rpd_limit = db_parameters.get("rpd") # Rate limit: Requests Per Day
    tpm_limit = db_parameters.get("tpm") # TPM limit parameter (not strictly used in wait_for_rate_limit in utils)
    number_of_predicted_events = db_parameters.get("number_of_predicted_events")
    chunk_size_chars = db_parameters.get("chunk_size_chars")
    max_output_tokens = db_parameters.get("max_output_tokens")
    model_name = db_parameters.get("model")
    delay_between_matches = db_parameters.get("delay_between_matches", 15)

    # Get AI Generation Parameters (Optional, default to None if missing)
    temperature = db_parameters.get("temperature", None)
    top_p = db_parameters.get("top_p", None)
    top_k = db_parameters.get("top_k", None)


    # --- Select Fixture URL and Calculate Target Date based on the 'fetch_today' flag ---
    selected_fixture_url = None
    target_match_date_str = None

    # Check if the URLs are present and are strings.
    if not isinstance(today_fixtures_url, str) or today_fixtures_url == "" or not isinstance(tomorrow_fixtures_url, str) or tomorrow_fixtures_url == "":
         print("Error: 'today_fixture_url' or 'tomorrow_fixture_url' parameters are missing, empty, or not strings in DB configuration.")
         return {"message": "Error: Missing or invalid fixture URLs in configuration.", "status": "failed"}

    # Use .get() with a default of True and explicitly check if the value retrieved is boolean True.
    if db_parameters.get("fetch_today", True) is True:
        selected_fixture_url = today_fixtures_url
        # Calculate today's date in DD-MM-YYYY format (using your preferred format)
        target_match_date_str = datetime.datetime.now().strftime('%d-%m-%Y')
        print(f"Fetching TODAY's matches from: {selected_fixture_url}")
    else: # fetch_today is False or any other value indicating 'not today'
        selected_fixture_url = tomorrow_fixtures_url
        # Calculate tomorrow's date in DD-MM-YYYY format (using your preferred format)
        target_match_date_str = (datetime.datetime.now() + timedelta(days=1)).strftime('%d-%m-%Y')
        print(f"Fetching TOMORROW's matches from: {selected_fixture_url}")


    # --- Check if required parameters for the process are available and valid ---
    # Using the simplified validation logic
    missing_or_invalid = []

    # Check Date/URL parameters
    if not isinstance(today_fixtures_url, str) or today_fixtures_url == "":
        missing_or_invalid.append("today_fixture_url (missing, empty, or not string)")
    if not isinstance(tomorrow_fixtures_url, str) or tomorrow_fixtures_url == "":
         missing_or_invalid.append("tomorrow_fixture_url (missing, empty, or not string)")
    fetch_today_val = db_parameters.get("fetch_today")
    if fetch_today_val is not None and not isinstance(fetch_today_val, bool):
         missing_or_invalid.append(f"fetch_today (invalid type: {type(fetch_today_val)})")

    # Check essential Prompt/Schema parameters
    if not initial_predict_prompt_template or not isinstance(initial_predict_prompt_template, str):
        missing_or_invalid.append("predict_initial_prompt (missing or not string)")
    if not final_predict_instruction_string or not isinstance(final_predict_instruction_string, str):
        missing_or_invalid.append("predict_final_prompt (missing or not string)")
    if not match_prediction_schema or not isinstance(match_prediction_schema, dict):
        missing_or_invalid.append("match_prediction_schema (missing or not dictionary)")

    # Check numeric parameters
    if not isinstance(rpm_limit, int) or rpm_limit < 0:
        missing_or_invalid.append("rpm (missing, not integer, or negative)")
    if not isinstance(rpd_limit, int) or rpd_limit < 0:
        missing_or_invalid.append("rpd (missing, not integer, or negative)")
    if not isinstance(number_of_predicted_events, int) or number_of_predicted_events <= 0:
        missing_or_invalid.append("number_of_predicted_events (missing, not integer, or not positive)")
    if not isinstance(chunk_size_chars, int) or chunk_size_chars <= 0:
        missing_or_invalid.append("chunk_size_chars (missing, not integer, or not positive)")
    if not isinstance(max_output_tokens, int) or max_output_tokens <= 0:
        missing_or_invalid.append("max_output_tokens (missing, not integer, or not positive)")

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


    # If any essential parameters are missing or invalid, log and return failed status.
    if missing_or_invalid:
        print("Error: Missing or invalid essential configuration parameters loaded from DB for running process.")
        print(f"Missing or invalid keys: {missing_or_invalid}")
        return {"message": "Error: Missing or invalid essential configuration parameters for running process. Check database config.", "status": "failed"}

    # --- End Parameter Validation ---


    # --- Step 1: Fetch match fixtures (filtered by DB status) ---
    # Pass competitions_collection
    fixtures = await scraper.fetch_matches_fixtures(selected_fixture_url, competitions_collection, target_match_date_str)

    if not fixtures:
        print("No fixtures found to process after scraping and filtering.")
        return {"message": "No fixtures found to process.", "status": "completed"}

    print(f"\nProcessing {len(fixtures)} matches...")

    processed_count = 0
    failed_count = 0


    # --- Step 2: Process each fixture ---
    for i, match_data_from_scrape in enumerate(fixtures):
        print(f"\n--- Processing Match {i + 1}/{len(fixtures)} ---")
        home_team = match_data_from_scrape.get('home_team', 'N/A')
        away_team = match_data_from_scrape.get('away_team', 'N/A')
        stats_link = match_data_from_scrape.get('stats_link', 'N/A')
        match_date = match_data_from_scrape.get('date', 'N/A')
        match_time = match_data_from_scrape.get('time', 'N/A')
        competition = match_data_from_scrape.get('competition', 'N/A')

        print(f"Match: {home_team} vs {away_team}")

        # Prepare the base match document structure for saving prediction results or errors.
        match_document_base = {
            "competition": competition,
            "date": match_date,
            "time": match_time,
            "home_team": home_team,
            "away_team": away_team,
            "stats_link": stats_link,
            "predict_status": False,
            "post_match_analysis_status": False,
            "timestamp": datetime.datetime.utcnow(),
            "predictions": None,
            "post_match_analysis": None,
            "error_details": None,
            "status": "pending_analysis",
            "markdown_content": None # Initialize markdown_content field
        }


        # --- Step 3: Scrape match stats ---
        stats_markdown = await scraper.fetch_match_stats_markdown(stats_link)
        if stats_markdown:
             print(f"Markdown Length: {len(stats_markdown)}")
        else:
             print("Stats fetch returned None or empty markdown.")


        # --- Step 4: Analyze stats with AI (Pre-Match Prediction) ---
        # Proceed with AI analysis only if stats markdown was fetched successfully and is not empty.
        if stats_markdown and isinstance(stats_markdown, str) and stats_markdown.strip():
            print("Sending stats for AI analysis...")

            # Pass db_parameters and genai_client explicitly to analyzer
            analysis_result = await analyzer.analyze_with_gemini(
                match_data=match_data_from_scrape,
                input_data=stats_markdown,
                db_parameters=db_parameters, # Pass DB parameters
                genai_client=genai_client # Pass AI client
            )


            # --- Step 5: Process analysis result and save to DB ---
            # Use the passed predictions_collection
            if predictions_collection is None:
                 print("Error: Predictions collection not available. Cannot save analysis result.")
                 failed_count += 1
                 print("Analysis was attempted but DB collection for saving is missing. Skipping save for this match.")
                 continue

            if isinstance(analysis_result, dict) and "error" not in analysis_result:
                # Analysis was successful
                print("AI analysis successful. Preparing document for MongoDB.")
                match_document_base["predictions"] = analysis_result
                match_document_base["predict_status"] = True
                match_document_base["status"] = "analysis_complete"
                # Ensure markdown is NOT saved on success
                match_document_base["markdown_content"] = None


                try:
                    insert_id = await database.insert_one(predictions_collection, match_document_base)
                    if insert_id:
                         print(f"Successfully saved match analysis for {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                         processed_count += 1
                    else:
                         print(f"Warning: Failed to get inserted ID for match {home_team} vs {away_team}.")
                         processed_count += 1


                except Exception as e:
                    print(f"Error saving successful analysis for match {home_team} vs {away_team} to MongoDB: {e}")
                    failed_count += 1


            else:
                # Analysis failed
                print(f"AI analysis failed for {home_team} vs {away_team}.")
                print("Analysis result:", analysis_result)

                match_document_base["predictions"] = None

                if isinstance(analysis_result, dict):
                     match_document_base["error_details"] = {
                         "analysis_outcome": analysis_result.get("error", "Unknown analysis error"),
                         "details": analysis_result.get("details", "N/A"),
                         "raw_output": analysis_result.get("raw_output", analysis_result.get('raw_response', 'N/A')),
                         "finish_reason": analysis_result.get("finish_reason", "N/A")
                     }
                else:
                     match_document_base["error_details"] = {
                          "analysis_outcome": "Unexpected analysis function return type or value",
                          "details": f"Analyzer returned: {analysis_result}",
                          "raw_output": analysis_result,
                          "finish_reason": "N/A"
                     }

                match_document_base["predict_status"] = False
                match_document_base["status"] = "analysis_failed"
                # --- Save markdown content on analysis failure ---
                match_document_base["markdown_content"] = stats_markdown
                # --- END NEW ---


                try:
                     insert_id = await database.insert_one(predictions_collection, match_document_base)
                     if insert_id:
                        print(f"Saved match with analysis error for {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                        failed_count += 1
                     else:
                         print(f"Warning: Failed to get inserted ID for match with analysis error {home_team} vs {away_team}.")
                         failed_count += 1


                except Exception as e:
                       print(f"Failed to save match with analysis error to MongoDB: {e}")
                       failed_count += 1


        else:
            # Stats fetch failed or markdown was empty - log this and save failure status.
            print(f"Skipping analysis and saving for {home_team} vs {away_team} due to failed stats fetch or empty markdown.")
            failed_count += 1

            # Prepare a document indicating stats fetch failure.
            stats_fetch_error_document = {
                "competition": competition,
                "date": match_date,
                "time": match_time,
                "home_team": home_team,
                "away_team": away_team,
                "stats_link": stats_link,
                "timestamp": datetime.datetime.utcnow(),
                "status": "stats_fetch_failed",
                "error_details": {"analysis_outcome": "Stats Fetch Failed", "details": "Failed to fetch stats markdown or received empty markdown."},
                "markdown_content": None # Markdown is None if fetch failed
            }
            # Use the passed predictions_collection
            if predictions_collection is None:
                 print("Error: Predictions collection not available. Cannot save stats fetch error result.")
                 print("Stats fetch failed, but DB collection for saving is missing. Skipping save for this match.")
            else:
                 try:
                      insert_id = await database.insert_one(predictions_collection, stats_fetch_error_document)
                      if insert_id:
                         print(f"Successfully saved match with stats fetch error for {home_team} vs {away_team} to MongoDB with ID: {insert_id}")
                      else:
                         print(f"Warning: Failed to get inserted ID for match with stats fetch error {home_team} vs {away_team}.")
                 except Exception as e:
                       print(f"Failed to save match with stats fetch error to MongoDB: {e}")


        # Implement a delay between processing matches to avoid hammering services.
        delay_between_matches_param = db_parameters.get("delay_between_matches", 15)
        effective_delay_between_matches = delay_between_matches_param if isinstance(delay_between_matches_param, (int, float)) and delay_between_matches_param >= 0 else 15

        if i < len(fixtures) - 1:
            print(f"Waiting for {effective_delay_between_matches} seconds before processing the next match...")
            await asyncio.sleep(effective_delay_between_matches)


    print("Background pre-match prediction process complete.")
    summary_message = f"Summary: {processed_count} matches successfully analyzed and saved, {failed_count} matches encountered errors during fetch/analysis/save."
    print(summary_message)

    # In a background task, you typically don't return a value.

# --- End of run_full_prediction_process ---