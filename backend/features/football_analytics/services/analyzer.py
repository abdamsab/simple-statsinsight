# backend/features/football_analytics/services/analyzer.py

# This file contains the AI interaction logic, including calling the Gemini API.

import asyncio # For asynchronous operations and sleeping
import json # For parsing JSON output
from typing import Any, Dict, List, Optional # Explicitly import type hints for clarity
from google import genai # Correct library import
import time # Need time for timing the API request itself for logging

# --- Import shared utility functions ---
# Import the rate limiter function from shared/utils.py
from ....shared import utils # Adjusted import path (up three levels, then into shared)


# --- Rate Limiting Helper Function ---
# This asynchronous function is called before each API request to manage rate limits.
# It takes rate limits (RPM, RPD) and the model name for conditional sleep.
# This function remains the same as the correct version provided earlier in shared/utils.py.
# The logic here is just a copy for clarity, the actual function is in utils.py.
# We will call the function from utils.py directly.
"""
async def wait_for_rate_limit(
    rpm_limit: Optional[int] = None,
    rpd_limit: Optional[int] = None,
    model_name: Optional[str] = None
):
    # This code block is removed from here and lives in shared/utils.py
    # It's important that the global rate limiting variables and logic are centralized there.
    pass # Function definition now exists in utils.py
"""


# --- AI Analysis Function (Pre-Match Prediction - Corrected to use Chat Session) ---
# This function interacts with the Gemini API for analysis and prediction.
# It takes match data, input data (markdown), parameters configuration, and the AI client instance.
# It now uses the client.chats.create().send_message() pattern.
# It returns a dictionary containing the analysis result or an error dictionary (including raw output/details).
async def analyze_with_gemini(
    match_data: Dict[str, Any], # Pass match_data dictionary for prompt formatting
    input_data: str, # The main data to send for analysis (markdown string)
    db_parameters: Dict[str, Any], # Accept DB parameters dictionary
    genai_client: genai.Client # Accept AI client instance (from google.genai)
) -> Dict[str, Any]:
    """
    Sends match stats markdown to the Gemini API for pre-match prediction analysis.
    Formats prompt using templates and schema from db_parameters.
    Uses client.chats.create().send_message() for API interaction.
    Manages rate limiting using the wait_for_rate_limit helper from shared.utils.
    Parses JSON response and returns a dictionary or an error dictionary (with raw output/details).
    """
    print("Starting AI analysis with Gemini (using chat session)...")

    # --- Extract necessary parameters from the passed db_parameters dictionary ---
    initial_predict_prompt_template = db_parameters.get("predict_initial_prompt")
    final_instruction_string = db_parameters.get("predict_final_prompt")
    match_prediction_schema = db_parameters.get("match_prediction_schema")
    rpm_limit = db_parameters.get("rpm")
    rpd_limit = db_parameters.get("rpd")
    # tpm_limit = db_parameters.get("tpm") # TPM limit parameter (not strictly used in wait_for_rate_limit)
    number_of_predicted_events = db_parameters.get("number_of_predicted_events")
    chunk_size_chars_param = db_parameters.get("chunk_size_chars")
    max_output_tokens_param = db_parameters.get("max_output_tokens")
    model_name = db_parameters.get("model") # Get the model name string
    # Get AI Generation Parameters (Optional, default to None if missing)
    temperature = db_parameters.get("temperature", None)
    top_p = db_parameters.get("top_p", None)
    top_k = db_parameters.get("top_k", None)


    # --- Populate initial prompt template with match data ---
    # Use the logic from your working example's approach for formatting the initial prompt
    formatted_initial_prompt_string = ""
    if initial_predict_prompt_template and isinstance(initial_predict_prompt_template, str) and isinstance(match_data, dict):
         try:
              formatted_initial_prompt_string = initial_predict_prompt_template.format(
                   # Pass all items from match_data dictionary as format arguments
                   **match_data, # <-- Pass match_data here to cover placeholders like home_team, away_team etc.
                   # Explicitly pass number_of_predicted_events as it might be in the prompt template too
                   number_of_predicted_events=number_of_predicted_events
              )
              # print(f"Debug: Initial prompt template formatted.") # Optional debug print
         except KeyError as e:
              print(f"Error formatting initial prompt string from template: Missing key {e}.")
              formatted_initial_prompt_string = initial_predict_prompt_template
              print("Using raw initial prompt template due to formatting error.")
         except Exception as e:
              print(f"An unexpected error occurred formatting initial prompt string: {e}.")
              formatted_initial_prompt_string = initial_predict_prompt_template
              print("Using raw initial prompt template due to formatting error.")

    elif initial_predict_prompt_template and isinstance(initial_predict_prompt_template, str):
         formatted_initial_prompt_string = initial_predict_prompt_template
         print("Warning: match_data is not a dictionary or initial prompt template is missing. Using raw template.")

    else:
         print("Error: Initial prediction prompt template is missing or not a string in parameters config.")
         return {"error": "Missing initial prediction prompt template in configuration."}


    # --- Basic validation of essential parameters required for AI interaction ---
    is_essential_config_valid = (
        formatted_initial_prompt_string != ""
        and final_instruction_string is not None and isinstance(final_instruction_string, str) and final_instruction_string != ""
        and match_prediction_schema is not None and isinstance(match_prediction_schema, dict) and match_prediction_schema
        and model_name is not None and isinstance(model_name, str) and model_name != ""
    )

    if not is_essential_config_valid:
         print("Error: Missing one or more required parameters from configuration for AI interaction.")
         print(f"Debug: formatted_initial_prompt_string: {formatted_initial_prompt_string != ''}")
         print(f"Debug: final_instruction_string: {final_instruction_string is not None and isinstance(final_instruction_string, str) and final_instruction_string != ''}")
         print(f"Debug: output_schema: {output_schema is not None and isinstance(output_schema, dict) and bool(output_schema)}")
         print(f"Debug: model_name: {model_name is not None and isinstance(model_name, str) and model_name != ''}")
         return {"error": "Missing required analysis configuration parameters for AI interaction."}


    # --- Determine effective settings, using parameters or sensible defaults ---
    effective_chunk_size = chunk_size_chars_param if isinstance(chunk_size_chars_param, int) and chunk_size_chars_param > 0 else 100000 # Use parameter or default
    effective_max_output_tokens = max_output_tokens_param if isinstance(max_output_tokens_param, int) and max_output_tokens_param > 0 else None # Use parameter or None

    # Ensure model name string has the 'models/' prefix as required by the new library's API calls if it doesn't already.
    model_name_with_prefix = model_name if model_name.startswith("models/") else f"models/{model_name}"
    # print(f"Debug: Using model name with prefix for API calls: {model_name_with_prefix}") # Optional debug print


    # --- Define Generation Configuration for the final message requesting JSON (as a Python DICTIONARY) ---
    # This tells the AI model how to generate its final response.
    # Pass this DICTIONARY using the 'config=' argument when sending the final message.
    # Include max_output_tokens, temperature, top_p, top_k here if loaded from parameters and not None.
    json_generation_config: Dict[str, Any] = {
        "response_mime_type": "application/json", # Request JSON output MIME type
        "response_schema": match_prediction_schema, # Use the FULL schema dictionary from parameters directly
    }
    # Add optional parameters to the dictionary if they were successfully loaded from db_parameters and are not None
    if effective_max_output_tokens is not None:
        json_generation_config["max_output_tokens"] = effective_max_output_tokens
    if temperature is not None:
         json_generation_config["temperature"] = temperature
    if top_p is not None:
         json_generation_config["top_p"] = top_p
    if top_k is not None:
         json_generation_config["top_k"] = top_k
    # print(f"Debug: Generated json_generation_config dictionary: {json_generation_config}") # Optional debug print


    # --- Start Chat Session using the Passed google.genai client instance ---
    # Use the passed genai_client instance (initialized in main.py) to create a new chat session.
    # Specify the model name string (with prefix) for this chat session.
    # Start with an empty history for a new analysis session.
    try:
        # Use the passed client instance and specified model name (with prefix).
        # The error occurred on genai_client.generate_content - this is the fix, use .chats.create() instead.
        chat = genai_client.chats.create(model=model_name_with_prefix, history=[])
        print("New Gemini chat started for analysis.")
    except Exception as e:
        print(f"Error starting Gemini chat session: {e}")
        if "unexpected model name format" in str(e).lower() or "invalid model name" in str(e).lower():
             print(f"Ensure the model name '{model_name}' is correct in your database parameters (e.g., 'gemini-2.0-flash' or 'models/gemini-2.0-flash').")
             return {"error": f"Failed to start Gemini chat session: Invalid model name '{model_name}' configured.", "details": str(e)}
        return {"error": "Failed to start Gemini chat session", "details": str(e)}


    # --- Send Initial Prompt ---
    print("Sending initial prompt to Gemini...")
    # Use the wait_for_rate_limit function from shared.utils BEFORE sending the API request.
    await utils.wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

    try:
        # Send the formatted initial prompt message using chat.send_message().
        response = chat.send_message(formatted_initial_prompt_string)

        # Check for prompt blocking for Initial Prompt
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            print(f"Initial prompt blocked: {response.prompt_feedback.block_reason}")
            return {"error": "Initial prompt blocked by safety filters", "block_reason": response.prompt_feedback.block_reason}

        # Log non-STOP finish reasons (optional, usually just informative here)
        finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None
        if finish_reason_str and finish_reason_str != "STOP":
             print(f"Initial prompt response finish reason: {finish_reason_str}")
             pass # Log but continue


    except Exception as e:
        print(f"Error sending initial prompt to Gemini: {e}")
        if "429" in str(e):
             print("Rate limit hit on initial prompt.")
             return {"error": "Rate limit hit on initial prompt", "details": str(e)}
        return {"error": "Failed to send initial prompt to Gemini", "details": str(e)}


    # --- Send Input Data (Markdown Chunks) ---
    if input_data is not None and isinstance(input_data, str) and input_data.strip():
        print("Sending string input data (markdown)...")
        chunks = [input_data[i:i + effective_chunk_size] for i in range(0, len(input_data), effective_chunk_size)]
        print(f"Input data split into {len(chunks)} chunks.")
        for i, chunk in enumerate(chunks):
            chunk_message = f"Data Part {i + 1}/{len(chunks)}:\n\n{chunk}"
            print(f"Sending chunk {i + 1}...")
            # Use wait_for_rate_limit function from shared.utils BEFORE sending the API request.
            await utils.wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

            try:
                # Send the chunk message using chat.send_message().
                response = chat.send_message(chunk_message)

                # Check for prompt blocking or non-STOP finish reason for chunk responses.
                finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None
                if response.prompt_feedback and response.prompt_feedback.block_reason:
                     print(f"Chunk {i+1} prompt blocked: {response.prompt_feedback.block_reason}")
                     return {"error": f"Chunk {i+1} blocked by safety filters", "block_reason": response.prompt_feedback.block_reason}
                if finish_reason_str and finish_reason_str != "STOP":
                     print(f"Chunk {i+1} response finish reason: {finish_reason_str}")
                     pass # Log and continue

            except Exception as e:
                print(f"Error sending chunk {i + 1} to Gemini: {e}")
                if "429" in str(e):
                     print("Rate limit hit on sending chunk.")
                     return {"error": f"Rate limit hit on chunk {i+1}", "details": str(e)}
                return {"error": f"Failed to send data chunk {i+1} to Gemini", "details": str(e)}

    elif not (isinstance(input_data, str) and input_data.strip()):
         # Log a warning and return an error if input_data is None or empty string.
         print("Warning: No valid string input data provided for analysis. Skipping data sending.")
         # This case should ideally not happen if analyze_with_gemini is called correctly with fetched markdown.
         return {"error": "No valid string input data provided for analysis."}

    # Note: This version of analyze_with_gemini is specifically tailored for string markdown input,
    # not the list input handling that was present in the working example's generalized version.
    # If you need list input, the logic would need to be added back here.


    # --- Send Final Instruction and Request JSON Output ---
    print("Sending final instruction to Gemini and requesting JSON output...")
    # Use the wait_for_rate_limit function from shared.utils BEFORE sending the final API request.
    await utils.wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

    try:
        # Send the final instruction message using chat.send_message().
        # Pass the json_generation_config DICTIONARY using the 'config=' argument.
        # This is the corrected call using the chat session object.
        response = chat.send_message(
            final_instruction_string, # The final instruction string from DB parameters
            config=json_generation_config # Pass the GenerationConfig DICTIONARY here
        )

        # --- Process the Final Response ---
        # Check response feedback (e.g., safety filters) and candidates from the final response object.

        # Check for prompt blocking by safety filters for the final instruction.
        if response.prompt_feedback and response.prompt_feedback.block_reason:
             print(f"Final instruction prompt blocked: {response.prompt_feedback.block_reason}")
             return {"error": "Final instruction blocked by safety filters", "block_reason": response.prompt_feedback.block_reason}

        # Access the finish reason from the first candidate.
        finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None

        if finish_reason_str:
             print(f"Final response finish reason: {finish_reason_str}")
             # Check specifically for MAX_TOKENS or other non-STOP reasons
             if finish_reason_str == "MAX_TOKENS":
                  print("Warning: Analysis incomplete due to hitting maximum output tokens.")
                  return {"error": "Gemini analysis incomplete: Maximum output tokens reached.", "raw_response": response.text if response.text else 'N/A', "finish_reason": finish_reason_str}
             elif finish_reason_str != "STOP":
                  print(f"Warning: Analysis may be incomplete due to non-STOP finish reason: {finish_reason_str}")
                  return {"error": f"Gemini analysis incomplete or stopped due to finish reason: {finish_reason_str}", "raw_response": response.text if response.text else 'N/A', "finish_reason": finish_reason_str}


        # --- Get the generated text (should be a JSON string) ---
        gemini_analysis_text = ""
        try:
            if response.text:
                 gemini_analysis_text = response.text
            elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                 part_texts = [part.text for part in response.candidates[0].content.parts if hasattr(part, 'text') and part.text is not None]
                 gemini_analysis_text = "".join(part_texts)
            else:
                print("Warning: Received an unusual response format from Gemini, expected text/JSON.")
                return {"error": "Received an unusual response format from Gemini, expected text/JSON.", "raw_response": response}

        except Exception as text_access_error:
             print(f"Warning: Could not access response text/parts: {text_access_error}")
             return {"error": f"Could not access Gemini response text: {text_access_error}", "raw_response": response}


        # --- Attempt to parse the generated text as JSON ---
        if not gemini_analysis_text:
             print("Warning: Gemini returned empty response text.")
             return {"error": "Gemini returned empty response text."}

        try:
            analysis_json = json.loads(gemini_analysis_text)
            print("Successfully parsed JSON output from Gemini.")
            return analysis_json # Return the parsed JSON dictionary on successful analysis and parsing.

        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON output from Gemini: {e}")
            print("Raw Gemini output that failed parsing:", gemini_analysis_text)
            return {"error": "Failed to parse Gemini JSON output", "raw_output": gemini_analysis_text, "details": str(e)}

        except Exception as e:
             print(f"An unexpected error occurred after receiving Gemini response: {e}")
             print("Raw Gemini output:", gemini_analysis_text)
             return {"error": "An unexpected error occurred after receiving Gemini response", "details": str(e), "raw_output": gemini_analysis_text}


    except Exception as e:
        print(f"An error occurred during the final analysis request: {e}")
        if "429" in str(e):
             print("Rate limit hit on final instruction.")
             return {"error": "Rate limit hit on final instruction", "details": str(e)}
        return {"error": "Gemini analysis API request failed", "details": str(e)}

# --- End of analyze_with_gemini ---