# backend/features/football_analytics/services/analyzer.py

# This file contains the AI interaction logic, including calling the Gemini API.

import asyncio # For asynchronous operations and sleeping
import json # For parsing JSON output
from typing import Any, Dict, List, Optional # Explicitly import type hints for clarity
from google import genai # Correct library import (google-genai)
import time # Need time for timing the API request itself for logging

# --- Import shared utility functions ---
# Import the rate limiter function from shared/utils.py
from ....shared import utils # Adjusted import path (up three levels, then into shared)


# --- AI Analysis Function (Corrected to handle task_type logic) ---
# This function interacts with the Gemini API for analysis and prediction.
# It takes match data, input data (markdown or combined data), parameters configuration,
# the AI client instance, and the task type.
# It now uses the client.chats.create().send_message() pattern and selects
# prompts/schema based on task_type.
# Added task_type parameter to differentiate between pre-match and post-match analysis needs.
async def analyze_with_gemini(
    match_data: Dict[str, Any], # Pass match_data dictionary (used for pre-match prompt formatting)
    input_data: str, # The main data to send for analysis (markdown string or combined string)
    db_parameters: Dict[str, Any], # Accept DB parameters dictionary
    genai_client: genai.Client, # Accept AI client instance (from google.genai)
    task_type: str # <-- Parameter to specify the task type ("pre_match", "post_match")
) -> Dict[str, Any]:
    """
    Sends input data to the Gemini API for analysis based on task_type.
    Selects prompts and schema from db_parameters based on task_type.
    Handles multi-turn conversation, chunking input data, and requests JSON output.
    Uses client.chats.create().send_message() for API interaction.
    Manages rate limiting using the wait_for_rate_limit helper from shared.utils.
    Parses JSON response and returns a dictionary containing the analysis result
    or an error dictionary (including raw output/details and status).
    """
    print(f"\nStarting AI analysis with Gemini for task type: {task_type} (using chat session)...")

    # --- Extract necessary parameters from the passed db_parameters dictionary ---
    initial_prompt_template = None
    final_instruction_string = None
    output_schema = None
    number_of_predicted_events = db_parameters.get("number_of_predicted_events") # Needed for pre-match prompt formatting

    # --- ADDED Logic to select prompts and schema based on task_type ---
    if task_type == "pre_match":
        initial_prompt_template = db_parameters.get("predict_initial_prompt")
        final_instruction_string = db_parameters.get("predict_final_prompt")
        output_schema = db_parameters.get("match_prediction_schema")
        print("Selected pre-match prompts and schema.")
    elif task_type == "post_match":
        initial_prompt_template = db_parameters.get("post-match_initial_prompt") # Using post-match key from plan
        final_instruction_string = db_parameters.get("post-match_final_prompt") # Using post-match key from plan
        output_schema = db_parameters.get("post_match_analysis_schema")       # Using post-match key from plan
        print("Selected post-match prompts and schema.")
    else:
        print(f"Error: Invalid task_type received: {task_type}")
        return {"error": "Invalid task type provided for analyzer", "details": f"Received task_type: {task_type}", "status": "analysis_invalid_task_type"}


    # --- Access other common parameters ---
    rpm_limit = db_parameters.get("rpm")
    rpd_limit = db_parameters.get("rpd")
    chunk_size_chars_param = db_parameters.get("chunk_size_chars")
    max_output_tokens_param = db_parameters.get("max_output_tokens")
    model_name = db_parameters.get("model") # Get the model name string
    # Get AI Generation Parameters (Optional, default to None if missing)
    temperature = db_parameters.get("temperature", None)
    top_p = db_parameters.get("top_p", None)
    top_k = db_parameters.get("top_k", None)


    # --- Populate initial prompt template (handle pre-match formatting) ---
    formatted_initial_prompt_string = ""
    if initial_prompt_template and isinstance(initial_prompt_template, str):
         try:
              # Only attempt to format with match_data for pre_match tasks
              if task_type == "pre_match" and isinstance(match_data, dict):
                   formatted_initial_prompt_string = initial_prompt_template.format(
                        **match_data, # Pass all items from match_data dictionary as format arguments
                        number_of_predicted_events=number_of_predicted_events # Pass specific prediction count if needed
                   )
                   # print(f"Debug: Initial prompt template formatted for pre-match.") # Optional debug print
              else:
                   # For post-match or if match_data is not a dict, use the template directly
                   formatted_initial_prompt_string = initial_prompt_template
                   # print(f"Debug: Using raw initial prompt template for task {task_type} or missing match_data.") # Optional debug print

         except KeyError as e:
              print(f"Error formatting initial prompt string from template: Missing key {e}.")
              formatted_initial_prompt_string = initial_prompt_template
              print("Using raw initial prompt template due to formatting error.")
         except Exception as e:
              print(f"An unexpected error occurred formatting initial prompt string: {e}.")
              formatted_initial_prompt_string = initial_prompt_template
              print("Using raw initial prompt template due to formatting error.")

    else:
         print(f"Error: Initial prompt template for task '{task_type}' is missing or not a string in parameters config.")
         return {"error": f"Missing initial prompt template for task '{task_type}' in configuration.", "status": f"analysis_{task_type}_config_missing_prompt"}


    # --- Basic validation of essential parameters required for AI interaction ---
    # Check that the selected parameters based on task_type are valid
    is_essential_config_valid = (
        formatted_initial_prompt_string != ""
        and final_instruction_string is not None and isinstance(final_instruction_string, str) and final_instruction_string != ""
        and output_schema is not None and isinstance(output_schema, dict) and output_schema # Check if schema is a non-empty dictionary
        and model_name is not None and isinstance(model_name, str) and model_name != ""
    )

    if not is_essential_config_valid:
         print(f"Error: Missing one or more required parameters from configuration for AI interaction (task: {task_type}).")
         # Detailed debug prints for missing/invalid parameters (refined from previous steps)
         missing_details = {
              "initial_prompt_valid": formatted_initial_prompt_string != "",
              "final_instruction_valid": final_instruction_string is not None and isinstance(final_instruction_string, str) and final_instruction_string != "",
              "output_schema_valid": output_schema is not None and isinstance(output_schema, dict) and bool(output_schema),
              "model_name_valid": model_name is not None and isinstance(model_name, str) and model_name != ""
         }
         print(f"Missing/Invalid details for task '{task_type}': {missing_details}")
         return {"error": f"Missing required analysis configuration parameters for task '{task_type}'.", "details": missing_details, "status": f"analysis_{task_type}_config_missing_params"}


    # --- Determine effective settings, using parameters or sensible defaults ---
    effective_chunk_size = chunk_size_chars_param if isinstance(chunk_size_chars_param, int) and chunk_size_chars_param > 0 else 100000 # Use parameter or default
    # Use None if max_output_tokens is not set or invalid, allows model default.
    effective_max_output_tokens = max_output_tokens_param if isinstance(max_output_tokens_param, int) and max_output_tokens_param > 0 else None

    # Ensure model name string has the 'models/' prefix if required by the API calls.
    model_name_with_prefix = model_name if model_name.startswith("models/") else f"models/{model_name}"


    # --- Define Generation Configuration for the final message requesting JSON ---
    # This tells the AI model how to generate its final response.
    # Include max_output_tokens, temperature, top_p, top_k here if loaded from parameters and not None.
    json_generation_config: Dict[str, Any] = {
        "response_mime_type": "application/json", # Request JSON output MIME type
        "response_schema": output_schema, # Use the FULL selected schema dictionary directly
    }
    # Add optional parameters to the dictionary if they were successfully loaded from db_parameters and are not None/invalid
    if effective_max_output_tokens is not None:
        json_generation_config["max_output_tokens"] = effective_max_output_tokens
    # Check type and add if valid (Pydantic handles this on Settings, but doing it manually here)
    if temperature is not None and isinstance(temperature, (int, float)):
         json_generation_config["temperature"] = temperature
    if top_p is not None and isinstance(top_p, (int, float)):
         json_generation_config["top_p"] = top_p
    if top_k is not None and isinstance(top_k, int): # Top_k is usually integer
         json_generation_config["top_k"] = top_k

    # print(f"Debug: Generated json_generation_config dictionary: {json_generation_config}") # Optional debug print


    print(f"Using model: {model_name_with_prefix} for task {task_type}")
    print(f"Input data length: {len(input_data)}")


    # --- Start Chat Session using the Passed google.genai client instance ---
    try:
        chat = genai_client.chats.create(model=model_name_with_prefix, history=[])
        print(f"New Gemini chat started for {task_type} analysis.")
    except Exception as e:
        print(f"Error starting Gemini chat session for task {task_type}: {e}")
        if "unexpected model name format" in str(e).lower() or "invalid model name" in str(e).lower() or "models/" in str(e).lower():
             print(f"Ensure the model name '{model_name}' is correct in your database parameters (e.g., 'gemini-2.0-flash' or 'models/gemini-2.0-flash').")
             return {"error": f"Failed to start Gemini chat session for task {task_type}: Invalid model name '{model_name}' configured.", "details": str(e), "status": f"analysis_{task_type}_invalid_model"}
        return {"error": f"Failed to start Gemini chat session for task {task_type}", "details": str(e), "status": f"analysis_{task_type}_chat_startup_failed"}


    # --- Send Initial Prompt ---
    print("Sending initial prompt to Gemini...")
    await utils.wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

    try:
        response = chat.send_message(formatted_initial_prompt_string)

        if response.prompt_feedback and response.prompt_feedback.block_reason:
            print(f"Initial prompt blocked for task {task_type}: {response.prompt_feedback.block_reason}")
            return {"error": f"Initial prompt blocked by safety filters for task {task_type}", "block_reason": response.prompt_feedback.block_reason, "status": f"analysis_{task_type}_initial_prompt_blocked"}

        finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None
        if finish_reason_str and finish_reason_str != "STOP":
             print(f"Initial prompt response finish reason for task {task_type}: {finish_reason_str}")


    except Exception as e:
        print(f"Error sending initial prompt to Gemini for task {task_type}: {e}")
        if "429" in str(e):
             print("Rate limit hit on initial prompt.")
             return {"error": f"Rate limit hit on initial prompt for task {task_type}", "details": str(e), "status": f"analysis_{task_type}_initial_prompt_rate_limited"}
        return {"error": f"Failed to send initial prompt to Gemini for task {task_type}", "details": str(e), "status": f"analysis_{task_type}_initial_prompt_failed"}


    # --- Send Input Data (Chunks) ---
    if input_data is not None and isinstance(input_data, str) and input_data.strip():
        print(f"Sending string input data (length: {len(input_data)}) for analysis for task {task_type}...")

        chunks = [input_data[i:i + effective_chunk_size] for i in range(0, len(input_data), effective_chunk_size)]
        print(f"Input data split into {len(chunks)} chunks.")

        for i, chunk in enumerate(chunks):
            chunk_message = f"Data Part {i + 1}/{len(chunks)}:\n\n{chunk}"
            print(f"Sending chunk {i + 1} for task {task_type}...")
            await utils.wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

            try:
                response = chat.send_message(chunk_message)

                finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                     print(f"Chunk {i+1} prompt blocked for task {task_type}: {response.prompt_feedback.block_reason}")
                     return {"error": f"Chunk {i+1} blocked by safety filters for task {task_type}", "block_reason": response.prompt_feedback.block_reason, "status": f"analysis_{task_type}_chunk_blocked"}
                if finish_reason_str and finish_reason_str != "STOP":
                     print(f"Chunk {i+1} response finish reason for task {task_type}: {finish_reason_str}")
                     pass # Log and continue


            except Exception as e:
                print(f"Error sending input data chunk {i + 1} to Gemini for task {task_type}: {e}")
                if "429" in str(e):
                     print("Rate limit hit on sending chunk.")
                     return {"error": f"Rate limit hit on chunk {i+1} for task {task_type}", "details": str(e), "status": f"analysis_{task_type}_chunk_rate_limited"}
                return {"error": f"Failed to send data chunk {i+1} to Gemini for task {task_type}", "details": str(e), "status": f"analysis_{task_type}_chunk_failed"}

    elif not (isinstance(input_data, str) and input_data.strip()):
         print(f"Warning: No valid string input data provided for analysis for task {task_type}. Skipping data sending.")
         return {"error": f"No valid string input data provided for analysis for task {task_type}.", "status": f"analysis_{task_type}_no_input_data"}


    # --- Send Final Instruction and Request JSON Output ---
    print(f"Sending final instruction to Gemini for task {task_type} and requesting JSON output...")
    await utils.wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

    try:
        response = chat.send_message(
            final_instruction_string, # The final instruction string from DB parameters
            config=json_generation_config # Pass the GenerationConfig DICTIONARY here
        )

        # --- Process the Final Response ---
        finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None

        if response.prompt_feedback and response.prompt_feedback.block_reason:
             print(f"Final instruction prompt blocked for task {task_type}: {response.prompt_feedback.block_reason}")
             # Return block reason including the status
             return {"error": f"Final instruction blocked by safety filters for task {task_type}", "block_reason": response.prompt_feedback.block_reason, "status": f"analysis_{task_type}_final_prompt_blocked"}

        if finish_reason_str:
             print(f"Final response finish reason for task {task_type}: {finish_reason_str}")
             if finish_reason_str == "MAX_TOKENS":
                  print("Warning: Analysis incomplete due to hitting maximum output tokens.")
                  # Include status in the error dictionary
                  return {"error": f"Gemini analysis incomplete: Maximum output tokens reached for task {task_type}.", "raw_response": response.text if hasattr(response, 'text') and response.text else 'N/A', "finish_reason": finish_reason_str, "status": f"analysis_{task_type}_max_tokens"}
             elif finish_reason_str != "STOP":
                  print(f"Warning: Analysis may be incomplete due to non-STOP finish reason: {finish_reason_str}")
                  # Include status in the error dictionary
                  return {"error": f"Gemini analysis incomplete or stopped due to finish reason: {finish_reason_str} for task {task_type}", "raw_response": response.text if hasattr(response, 'text') and response.text else 'N/A', "finish_reason": finish_reason_str, "status": f"analysis_{task_type}_non_stop_finish"}


        # --- Get the generated text (should be a JSON string) ---
        gemini_analysis_text = ""
        try:
            if hasattr(response, 'text') and response.text is not None:
                 gemini_analysis_text = response.text
            elif response.candidates and len(response.candidates) > 0 and hasattr(response.candidates[0], 'content') and response.candidates[0].content and hasattr(response.candidates[0].content, 'parts') and response.candidates[0].content.parts:
                 # Fallback to accessing parts if response.text is not directly available
                 part_texts = [part.text for part in response.candidates[0].content.parts if hasattr(part, 'text') and part.text is not None]
                 gemini_analysis_text = "".join(part_texts)
            else:
                print(f"Warning: Received an unusual response format from Gemini for task {task_type}, expected text/JSON.")
                # Include status and the raw response object for debugging
                return {"error": f"Received an unusual response format from Gemini for task {task_type}, expected text/JSON.", "raw_response": response, "status": f"analysis_{task_type}_unusual_response_format"}

        except Exception as text_access_error:
             print(f"Warning: Could not access response text/parts for task {task_type}: {text_access_error}")
             # Include status in the error dictionary
             return {"error": f"Could not access Gemini response text for task {task_type}: {text_access_error}", "raw_response": response, "status": f"analysis_{task_type}_text_access_failed"}


        # --- Attempt to parse the generated text as JSON ---
        if not gemini_analysis_text:
             print(f"Warning: Gemini returned empty response text for task {task_type}.")
             # Include status in the error dictionary
             return {"error": f"Gemini returned empty response text for task {task_type}.", "status": f"analysis_{task_type}_empty_response"}

        # Clean the JSON string (remove markdown code block formatting)
        json_string = gemini_analysis_text.strip()
        if json_string.startswith("```json"):
            json_string = json_string[7:].strip()
            if json_string.endswith("```"):
                json_string = json_string[:-3].strip()
        # Handle cases where the model might output just ``` ```
        if json_string == "":
             print(f"Warning: Gemini output was just a JSON markdown code block with no content for task {task_type}.")
             # Include status in the error dictionary
             return {"error": f"Gemini output was empty JSON markdown block for task {task_type}.", "status": f"analysis_{task_type}_empty_json_block"}


        try:
            analysis_json = json.loads(json_string)
            print(f"Successfully parsed JSON output from Gemini for task {task_type}.")
            # Return the parsed dictionary.
            return analysis_json # SUCCESS!

        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON output from Gemini for task {task_type}: {e}")
            print("Raw Gemini output that failed parsing:", gemini_analysis_text)
            # Return an error dictionary including the raw output, the JSON parsing error details, and status.
            return {"error": f"Failed to parse Gemini JSON output for task {task_type}", "raw_output": gemini_analysis_text, "details": str(e), "status": f"analysis_{task_type}_json_decode_error"}

        except Exception as e:
             # Log any other unexpected errors after receiving and attempting to parse the response.
             print(f"An unexpected error occurred after receiving Gemini response for task {task_type}: {e}")
             # Include the raw output and error details in the returned dictionary, and status.
             print("Raw Gemini output:", gemini_analysis_text)
             return {"error": f"An unexpected error occurred after receiving Gemini response for task {task_type}", "details": str(e), "raw_output": gemini_analysis_text, "status": f"analysis_{task_type}_unexpected_processing_error"}


    except Exception as e:
        # Catch any other exceptions during the final API request process
        print(f"An error occurred during the final analysis request for task {task_type}: {e}")
        # Include details about rate limit if applicable, and status.
        error_details = str(e)
        if "429" in error_details:
             print("Rate limit hit on final instruction.")
             return {"error": f"Rate limit hit on final instruction for task {task_type}", "details": error_details, "status": f"analysis_{task_type}_final_rate_limited"}
        return {"error": f"Gemini analysis API request failed for task {task_type}", "details": error_details, "status": f"analysis_{task_type}_api_request_failed"}

# --- End of analyze_with_gemini ---