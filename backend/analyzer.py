# --- backend/analyzer.py (Modified for New Library and Schema approach from user's working example) ---

import asyncio # For asynchronous operations and sleeping
import json # For parsing JSON output
import time # For rate limiting timing
from datetime import datetime, timedelta # For rate limiting daily reset
from typing import Any, Dict, List, Optional # Explicitly import type hints for clarity
from google import genai

# --- Rate Limiting Variables ---
# Keep these module-level variables to maintain state across calls to wait_for_rate_limit.
# They track the number of requests within the current minute and day.
# These are global within this module.
request_count_minute = 0
last_request_time = time.time() # Timestamp of the last request initiation or minute reset
request_count_day = 0
last_day_reset = datetime.now().day # Stores the day number when the daily count was last reset (simple approach)


# --- Rate Limiting Helper Function (Modified to accept model_name for conditional sleep) ---
# This asynchronous function is called before each API request to manage rate limits.
# It takes rate limits (RPM, RPD) and the model name from the parameters configuration.
async def wait_for_rate_limit(
    rpm_limit: Optional[int] = None, # Pass RPM limit from parameters_config (Requests Per Minute)
    rpd_limit: Optional[int] = None, # Pass RPD limit from parameters_config (Requests Per Day)
    model_name: Optional[str] = None # ADD model_name parameter for conditional sleep logic based on model (e.g., "models/gemini-1.5-pro-latest")
):
    """
    Waits to respect AI API rate limits (RPM and RPD) defined in parameters_config.
    Takes limits as arguments. Includes conditional fixed sleep based on model name for
    strict free-tier limits, complementing counter-based rate limiting.
    """
    # Ensure limits are non-None integers > 0 for checks. If None or invalid, treat as no specific limit from config.
    effective_rpm_limit = rpm_limit if isinstance(rpm_limit, int) and rpm_limit > 0 else None
    effective_rpd_limit = rpd_limit if isinstance(rpd_limit, int) and rpd_limit > 0 else None

    # Access the global rate limiting state variables within this module.
    global request_count_minute, last_request_time, request_count_day, last_day_reset

    current_time = time.time() # Get the current timestamp (seconds since epoch).
    current_day = datetime.now().day # Get the current day number (1-31).

    # --- Minute Rate Limiting Check ---
    # Reset minute count if a minute (60 seconds) has passed since the last request timer was updated.
    # If the time difference is 60 seconds or more, a new minute has started according to our timer.
    if current_time - last_request_time >= 60:
        request_count_minute = 0 # Reset the minute request count.
        last_request_time = current_time # Update the last request timer to the current time.

    # Check minute limit BEFORE incrementing counts for the *current* request.
    # If an effective RPM limit is defined AND the current minute's requests already meet or exceed it.
    if effective_rpm_limit is not None and request_count_minute >= effective_rpm_limit:
        # Calculate how much time is left until the end of the current minute (60 seconds).
        # Subtract the time elapsed since the minute timer was last reset.
        sleep_time = 60 - (current_time - last_request_time)
        if sleep_time > 0:
            # If there's time left, print a message and pause execution.
            print(f"Minute request limit reached ({request_count_minute}/{effective_rpm_limit}). Waiting for {sleep_time:.2f} seconds.")
            await asyncio.sleep(sleep_time) # Pause execution using asyncio.sleep.

        # After waiting (or if no wait was needed because sleep_time was 0 or negative), reset the minute count and update the last request timer.
        request_count_minute = 0
        last_request_time = time.time() # Update the last request timer to the time *after* the wait.


    # --- Daily Rate Limiting Check ---
    # Reset daily count if a new day has started since the last day reset.
    # Compare the current day number with the stored last_day_reset day number.
    # This simple day number check works for most cases but might have edge cases around month/year ends or time zones.
    # A more robust check could compare datetime.date() objects: if datetime.now().date() != datetime.fromtimestamp(last_request_time).date():
    if current_day != last_day_reset:
        request_count_day = 0 # Reset the daily request count.
        last_day_reset = current_day # Update the last day reset to the current day number.
        # Optionally reset minute timer here too, or rely on the minute check above.
        # last_request_time = current_time


    # Check daily limit BEFORE incrementing counts for the *current* request.
    # If an effective RPD limit is defined AND the current day's requests already meet or exceed it.
    if effective_rpd_limit is not None and request_count_day >= effective_rpd_limit:
        print(f"Daily request limit reached ({request_count_day}/{effective_rpd_limit}). Waiting until next day.")
        # Calculate time until the start of the next day (simple approach).
        now = datetime.now()
        tomorrow = now + timedelta(days=1) # Add one day to the current datetime.
        # Create a datetime object for midnight (00:00:00) of tomorrow.
        midnight_tomorrow = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
        # Calculate the total seconds difference between now and midnight tomorrow.
        sleep_seconds = (midnight_tomorrow - now).total_seconds() + 60 # Add a minute buffer for safety after midnight.
        print(f"Sleeping for {sleep_seconds:.2f} seconds.")
        await asyncio.sleep(sleep_seconds) # Pause execution until approximately midnight tomorrow.

        # After waiting for the day change, reset counts and update reset times for the new day.
        request_count_day = 0
        last_day_reset = datetime.now().day
        last_request_time = time.time() # Also reset minute timer to the time *after* the long wait.


    # --- Implement Conditional Fixed Sleep based on Model (for strict free-tier limits or general politeness) ---
    # This adds an *additional* fixed delay *before* the API call is made, particularly useful for models with very low RPM limits like 1.5 Pro free tier (2 RPM = 1 request every 30 seconds).
    # It ensures a minimum time passes between requests for specific models, complementing the general RPM/RPD counters which might be less precise or based on higher configured limits.
    # Check if model_name is provided and matches the specific models needing extra delay.
    if model_name == "models/gemini-1.5-pro-latest": # Check against the model name string with prefix.
         # For 1.5 Pro free tier, a 30-second sleep before EACH request ensures we don't exceed 2 RPM.
         # Adjust this value based on the model's specific free-tier or paid quota.
         print("Applying 30-second delay before 1.5 Pro request (free tier).") # Log the delay.
         await asyncio.sleep(30) # Apply the longer fixed delay.

    elif model_name == "models/gemini-2.0-flash":
         # Add a smaller fixed delay for Flash if desired for politeness, even if its RPM quota is higher.
         # This is separate from the RPM counter logic above.
         # You could make this smaller delay configurable via parameters if needed.
         # print("Applying 3-second delay before 2.0 Flash request.") # Log the delay.
         await asyncio.sleep(3) # Apply a smaller fixed delay.

    # --- END Conditional Fixed Sleep ---


    # Increment counts for the current request *after* any necessary waiting has occurred due to RPM/RPD limits
    # and after applying the conditional fixed sleep. The actual API call will happen implicitly after this function returns.
    request_count_minute += 1
    request_count_day += 1
    # print(f"Debug: Request counts incremented. Minute count: {request_count_minute}, Day count: {request_count_day}") # Optional debug print


# --- Generalized AI Analysis Function (Modified for google.genai client and parameters, passing config as dictionary) ---
# This asynchronous function performs the core AI interaction logic for a single analysis task.
# It handles sending prompts, input data (potentially chunked), requesting structured output,
# and includes rate limiting logic and error handling.
# It uses the NEW google.genai library and receives the client and configuration parameters.
# CRITICALLY, it defines and passes the GenerationConfig as a Python dictionary.
async def analyze_with_gemini(
    match_data: dict, # Pass match_data dictionary if needed for prompt formatting (used in template). E.g., {'home_team': 'Team A', 'away_team': 'Team B', ...}
    input_data: str | list[Any] | None, # The main data to send for analysis (e.g., a markdown string of stats, or potentially a list of messages for other tasks).
    parameters_config: dict, # Add parameter to pass the full configuration dictionary loaded from DB in main.py. Contains AI prompts, schema, limits, etc.
    genai_client: genai.Client # Add parameter to pass the initialized google.genai client instance from main.py startup.
):
    """
    Sends input data to Gemini for analysis and prediction/analysis using the new google.genai library.
    Generalized for pre-match and post-match tasks. Uses max_output_tokens in GenerationConfig (as a dictionary key).
    Uses the FULL schema directly from parameters_config, including propertyOrdering.
    Passes the GenerationConfig as a Python dictionary via the 'config=' argument in send_message.
    Returns a dictionary: either the parsed JSON output on successful analysis and parsing, or an error dictionary on failure.
    """
    # --- Extract necessary parameters from the passed parameters_config dictionary ---
    # Access parameters from the configuration dictionary passed as an argument.
    # Use .get() with default or None fallback for safety in case a parameter is missing in the DB document.
    # Ensure parameter names match exactly what is stored in your database parameters document.
    initial_prompt_template = parameters_config.get("predict_initial_prompt") # Assuming this is the template string for the initial prompt from DB parameters
    final_instruction_string = parameters_config.get("predict_final_prompt") # Assuming this is the final instruction string to trigger JSON output from DB parameters
    output_schema = parameters_config.get("match_prediction_schema") # Assuming the schema dictionary for JSON output structure is stored in DB parameters
    rpm_limit = parameters_config.get("rpm") # Rate limit parameter: Requests Per Minute
    rpd_limit = parameters_config.get("rpd") # Rate limit parameter: Requests Per Day
    tpm_limit = parameters_config.get("tpm") # TPM limit parameter (not strictly used in wait_for_rate_limit in this version)
    chunk_size_chars_param = parameters_config.get("chunk_size_chars") # Chunk size parameter for splitting string input (markdown)
    max_output_tokens_param = parameters_config.get("max_output_tokens") # Max output tokens parameter for AI GenerationConfig
    model_name = parameters_config.get("model") # Get the model name string (e.g., "gemini-2.0-flash", "gemini-1.5-pro-latest")
    number_of_predicted_events = parameters_config.get("number_of_predicted_events", 15) # Number of events requested in prompt template, default to 15 if missing
    # Add other generation parameters like temperature, top_k, top_p if they are included in your DB parameters
    temperature = parameters_config.get("temperature", None) # Use None if not in parameters, model default will apply
    top_p = parameters_config.get("top_p", None) # Use None if not in parameters, model default will apply
    top_k = parameters_config.get("top_k", None) # Use None if not in parameters, model default will apply


    # --- Populate initial prompt template with match data ---
    # This formats the initial prompt string by inserting values into placeholders in the template string loaded from DB.
    # Assuming the initial prompt template stored in the DB expects placeholders like {home_team}, {away_team}, and {number_of_predicted_events}.
    formatted_initial_prompt_string = "" # Initialize as empty string
    if initial_prompt_template and isinstance(initial_prompt_template, str) and isinstance(match_data, dict):
         try:
              # Attempt to format the prompt template using match data keys and the number of events parameter.
              # Use .get() for safety when accessing match_data dictionary keys.
              formatted_initial_prompt_string = initial_prompt_template.format(
                   home_team=match_data.get('home_team', 'N/A'), # Get home team name from match_data dictionary, default 'N/A'
                   away_team=match_data.get('away_team', 'N/A'), # Get away team name from match_data dictionary, default 'N/A'
                   number_of_predicted_events=number_of_predicted_events # Use the parameter value for the number of events
              )
              # print(f"Debug: Initial prompt template formatted.") # Optional debug print
         except KeyError as e:
              # Handle KeyError if a placeholder in the template is missing from the match_data or parameters.
              print(f"Error formatting initial prompt string from template: Missing key {e}.")
              formatted_initial_prompt_string = initial_prompt_template # Fallback to using the raw template string if formatting fails
              print("Using raw initial prompt template due to formatting error.")
         except Exception as e:
              # Handle any other unexpected errors during formatting.
              print(f"An unexpected error occurred formatting initial prompt string: {e}.")
              formatted_initial_prompt_string = initial_prompt_template # Fallback to using the raw template string if formatting fails
              print("Using raw initial prompt template due to formatting error.")

    elif initial_prompt_template and isinstance(initial_predict_prompt_template, str):
         # If match_data wasn't a dictionary but template exists, use the raw template string.
         # Placeholders like {home_team} etc. might not be formatted correctly in this case.
         formatted_initial_prompt_string = initial_predict_prompt_template
         print("Warning: match_data is not a dictionary or initial prompt template is missing. Using raw template.")

    else:
         # If initial prompt template is missing entirely or is not a string.
         print("Error: Initial prediction prompt template is missing or not a string in parameters config.")
         # Cannot proceed with analysis if the initial prompt template is missing.
         return {"error": "Missing initial prediction prompt template in configuration."}


    # --- Basic validation of essential parameters required for AI interaction ---
    # Check if we have the formatted initial prompt, final instruction, schema, and model name string.
    # These are critical for making the AI calls and requesting structured output correctly.
    is_essential_config_valid = (
        formatted_initial_prompt_string != "" # Check if the formatted prompt is not empty
        and final_instruction_string is not None and isinstance(final_instruction_string, str) and final_instruction_string != "" # Check if final instruction is a non-empty string
        and output_schema is not None and isinstance(output_schema, dict) and output_schema # Check if schema is a non-empty dictionary
        and model_name is not None and isinstance(model_name, str) and model_name != "" # Check if model name is a non-empty string
    )

    if not is_essential_config_valid:
         print("Error: Missing one or more required parameters from configuration for AI interaction.")
         # Print debug info about which essential parameters are missing/empty/invalid for better debugging.
         print(f"Debug: formatted_initial_prompt_string: {formatted_initial_prompt_string != ''}")
         print(f"Debug: final_instruction_string: {final_instruction_string is not None and isinstance(final_instruction_string, str) and final_instruction_string != ''}")
         print(f"Debug: output_schema: {output_schema is not None and isinstance(output_schema, dict) and bool(output_schema)}") # Check for None, dict type, and not empty
         print(f"Debug: model_name: {model_name is not None and isinstance(model_name, str) and model_name != ''}")

         return {"error": "Missing required analysis configuration parameters for AI interaction."}


    # --- Determine effective settings, using parameters or sensible defaults ---
    # Use the chunk size parameter from DB for splitting string input. Default to 28000 characters if parameter is missing, not an integer, or not positive.
    effective_chunk_size = chunk_size_chars_param if isinstance(chunk_size_chars_param, int) and chunk_size_chars_param > 0 else 100000 # Use parameter or default (changed default to match working code)
    # print(f"Debug: Using input chunk size: {effective_chunk_size}") # Optional debug print


    # Use the max_output_tokens parameter from DB for the GenerationConfig. Default to None if parameter is missing, not an integer, or not positive.
    # Setting to None means using the model's default limit.
    effective_max_output_tokens = max_output_tokens_param if isinstance(max_output_tokens_param, int) and max_output_tokens_param > 0 else None # Use parameter or None
    # print(f"Debug: Using max_output_tokens: {effective_max_output_tokens}") # Optional debug print


    # Ensure model name string has the 'models/' prefix as required by the new library's API calls if it doesn't already.
    model_name_with_prefix = model_name if model_name.startswith("models/") else f"models/{model_name}"
    # print(f"Debug: Using model name with prefix for API calls: {model_name_with_prefix}") # Optional debug print


    # --- Define Generation Configuration for the final message requesting JSON (as a Python DICTIONARY, like in user's working example) ---
    # This tells the AI model how to generate its final response.
    # Pass this DICTIONARY using the 'config=' argument when sending the final message.
    # Include max_output_tokens, temperature, top_p, top_k here if loaded from parameters and not None.
    json_generation_config: Dict[str, Any] = {
        "response_mime_type": "application/json", # Request JSON output MIME type
        "response_schema": output_schema, # Use the FULL schema dictionary from parameters directly
    }
    # Add optional parameters to the dictionary if they were successfully loaded from parameters_config and are not None
    if effective_max_output_tokens is not None:
        json_generation_config["max_output_tokens"] = effective_max_output_tokens
    if temperature is not None:
         json_generation_config["temperature"] = temperature
    if top_p is not None:
         json_generation_config["top_p"] = top_p
    if top_k is not None:
         json_generation_config["top_k"] = top_k
    # --- END CORRECTED: Defined as Dictionary ---

    # print(f"Debug: Generated json_generation_config dictionary: {json_generation_config}") # Optional debug print


    # --- Start Chat Session using the NEW google.genai client instance ---
    # Use the passed genai_client instance (initialized in main.py) to create a new chat session.
    # Specify the model name string (with prefix) for this chat session.
    # Start with an empty history for a new analysis session.
    try:
        # NOTE: While the user's working example might use a model name without the "models/" prefix in their script's GEMINI_MODEL variable,
        # the API calls (client.chats.create) typically require the prefix, which we handle by using model_name_with_prefix.
        chat = genai_client.chats.create(model=model_name_with_prefix, history=[]) # Use the client instance and specified model
        print("New Gemini chat started for analysis.")
    except Exception as e:
        # Log an error if starting the chat session fails.
        print(f"Error starting Gemini chat session: {e}")
        # Check if the error message suggests an invalid model name format (common issue during initialization).
        # Check lower case of error message just in case it varies.
        if "unexpected model name format" in str(e).lower() or "invalid model name" in str(e).lower():
             print(f"Ensure the model name '{model_name}' is correct in your database parameters (e.g., 'gemini-2.0-flash' or 'models/gemini-2.0-flash').")
             # Return an error dictionary including the invalid model name for debugging.
             return {"error": f"Failed to start Gemini chat session: Invalid model name '{model_name}' configured.", "details": str(e)}
        # Return a general error dictionary for other exceptions during chat creation.
        return {"error": "Failed to start Gemini chat session", "details": str(e)}


    # --- Send Initial Prompt ---
    print("Sending initial prompt to Gemini...")
    # Use the wait_for_rate_limit function BEFORE sending the API request for the initial prompt.
    # Pass the limits (RPM, RPD) and the model name (with prefix) from parameters_config to the rate limiter.
    await wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

    try:
        # Send the formatted initial prompt message in the chat session.
        response = chat.send_message(formatted_initial_prompt_string)

        # --- Check Response Feedback for Initial Prompt ---
        # Access response feedback (e.g., safety filters) and candidates from the response object.

        # Check for prompt blocking by safety filters.
        if response.prompt_feedback and response.prompt_feedback.block_reason:
            print(f"Initial prompt blocked: {response.prompt_feedback.block_reason}")
            # Return an error dictionary if the initial prompt was blocked.
            return {"error": "Initial prompt blocked by safety filters", "block_reason": response.prompt_feedback.block_reason}

        # Access the finish reason from the first candidate if candidates exist and finish_reason is present.
        # Use getattr with default for safety. Accessing .name is standard for the FinishReason enum in the new library.
        finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None

        # Log non-STOP finish reasons for the initial prompt (usually just informative for the first turn).
        # 'STOP' indicates successful completion of the turn. Other reasons might indicate interruption.
        if finish_reason_str and finish_reason_str != "STOP":
             print(f"Initial prompt response finish reason: {finish_reason_str}")
             # Decide how to handle non-STOP initial response if needed (e.g., log, but continue the process).
             # For analysis, a non-STOP initial response is usually not critical, the model is just indicating it stopped mid-thought on the first turn.
             pass # Log but continue for now

    except Exception as e:
        # Log an error if sending the initial prompt fails (e.g., network error, API issue).
        print(f"Error sending initial prompt to Gemini: {e}")
        # Check if the error message indicates a 429 rate limit.
        if "429" in str(e):
             print("Rate limit hit on initial prompt.")
             # Return an error dictionary for rate limits.
             return {"error": "Rate limit hit on initial prompt", "details": str(e)}
        # Return a general error dictionary for other exceptions during the API call.
        return {"error": "Failed to send initial prompt to Gemini", "details": str(e)}


    # --- Send Input Data (Markdown Chunks or List Messages) ---
    # This section handles sending the large input data (like the scraped markdown), splitting it into chunks if necessary.
    # It supports both string input (which gets chunked) and list input (treated as individual messages).
    if input_data is not None:
        if isinstance(input_data, str):
            # Handle string input (like markdown) by chunking it into smaller parts to fit within context window limits per turn.
            print("Sending string input data (markdown)...")
            # Use the determined effective_chunk_size for splitting the string.
            chunks = [input_data[i:i + effective_chunk_size] for i in range(0, len(input_data), effective_chunk_size)]
            print(f"Input data split into {len(chunks)} chunks.")
            for i, chunk in enumerate(chunks):
                # Create a message for each chunk, indicating its part number in the sequence.
                chunk_message = f"Data Part {i + 1}/{len(chunks)}:\n\n{chunk}"
                print(f"Sending chunk {i + 1}...")
                # Use wait_for_rate_limit function BEFORE sending the API request for the chunk.
                # Pass the limits (RPM, RPD) and the model name (with prefix) to the rate limiter.
                await wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

                try:
                    # Send the chunk message in the chat session.
                    response = chat.send_message(chunk_message)

                    # Check for prompt blocking or non-STOP finish reason for chunk responses.
                    finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None
                    if response.prompt_feedback and response.prompt_feedback.block_reason:
                         print(f"Chunk {i+1} prompt blocked: {response.prompt_feedback.block_reason}")
                         # Return an error dictionary if the chunk message was blocked.
                         return {"error": f"Chunk {i+1} blocked by safety filters", "block_reason": response.prompt_feedback.block_reason}
                    if finish_reason_str and finish_reason_str != "STOP":
                         print(f"Chunk {i+1} response finish reason: {finish_reason_str}")
                         # Log and continue for now. Non-STOP on a chunk response might be ok
                         # as the model processes the input sequentially.
                         pass # Log but continue for now

                except Exception as e:
                    # Log an error if sending the chunk fails.
                    print(f"Error sending chunk {i + 1} to Gemini: {e}")
                    # Check if the error message indicates a 429 rate limit.
                    if "429" in str(e):
                         print("Rate limit hit on sending chunk.")
                         # Return an error dictionary for rate limits.
                         return {"error": f"Rate limit hit on chunk {i+1}", "details": str(e)}
                    # Return a general error dictionary for other exceptions during the API call.
                    return {"error": f"Failed to send data chunk {i+1} to Gemini", "details": str(e)}

        elif isinstance(input_data, list):
             # Handle list input (e.g., a list of messages or parts). This is less common for sending one large document but supported.
             print("Sending list of input data messages...")
             for i, message_content in enumerate(input_data):
                  # Basic check that list items are valid message types (string or dictionary/Part).
                  if not isinstance(message_content, (str, dict, genai.types.Part)): # Added check for genai.types.Part if needed
                     print(f"Warning: Input message content {i+1} in list is not a string, dict, or Part ({type(message_content)}). Skipping.")
                     continue

                  message_label = f"Input Message {i + 1}/{len(input_data)}"
                  print(f"Sending {message_label}...")
                  # Use wait_for_rate_limit function BEFORE sending the API request for the message.
                  # Pass the limits (RPM, RPD) and the model name (with prefix) to the rate limiter.
                  await wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

                  try:
                      # Send the message content in the chat session.
                      response = chat.send_message(message_content)

                      # Check for prompt blocking or non-STOP finish reason for messages.
                      finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None
                      if response.prompt_feedback and response.prompt_feedback.block_reason:
                          print(f"{message_label} prompt blocked: {response.prompt_feedback.block_reason}")
                          # Return an error dictionary if the message was blocked.
                          return {"error": f"{message_label} blocked by safety filters", "block_reason": response.prompt_feedback.block_reason}
                      if finish_reason_str and finish_reason_str != "STOP":
                          print(f"{message_label} response finish reason: {finish_reason_str}")
                          # Log and continue for now. A non-STOP finish reason on a message response might be okay.
                          pass # Log but continue for now

                  except Exception as e:
                      # Log an error if sending the list item message fails.
                      print(f"Error sending {message_label} to Gemini: {e}")
                      # Check if the error message indicates a 429 rate limit.
                      if "429" in str(e):
                          print("Rate limit hit on sending input message.")
                          # Return an error dictionary for rate limits.
                          return {"error": f"Rate limit hit on {message_label}", "details": str(e)}
                      # Return a general error dictionary for other exceptions during the API call.
                      return {"error": f"Failed to send input message {i+1} to Gemini", "details": str(e)}

        else:
            # Log a warning and return an error dictionary if input_data is an unexpected type.
            print(f"Warning: Unexpected input_data type: {type(input_data)}. Expected str or list. Skipping data sending.")
            return {"error": f"Unexpected input data type provided for analysis: {type(input_data)}"}

    else:
        # Log a message and return an error dictionary if input_data is None.
        print("No input data provided to send for analysis.")
        return {"error": "No input data provided for analysis."} # This case shouldn't happen if analyze_with_gemini is called correctly from main.py


    # --- Send Final Instruction and Request JSON Output ---
    print("Sending final instruction to Gemini and requesting JSON output...")
    # Use the wait_for_rate_limit function BEFORE sending the final API request.
    # Pass the limits (RPM, RPD) and the model name (with prefix) to the rate limiter.
    await wait_for_rate_limit(rpm_limit, rpd_limit, model_name=model_name_with_prefix)

    try:
        # Send the final instruction message in the chat session.
        # Pass the json_generation_config DICTIONARY using the 'config=' argument, as shown in the user's working example.
        # This final message, combined with the config dictionary, triggers the structured output generation after all data has been provided.
        response = chat.send_message(
            final_instruction_string, # The final instruction string from DB parameters
            config=json_generation_config # Pass the GenerationConfig DICTIONARY here, matching the working example's approach
        )

        # --- Process the Final Response ---
        # Check response feedback (e.g., safety filters) and candidates from the final response object.

        # Check for prompt blocking by safety filters for the final instruction.
        if response.prompt_feedback and response.prompt_feedback.block_reason:
             print(f"Final instruction prompt blocked: {response.prompt_feedback.block_reason}")
             # Return an error dictionary if the final instruction was blocked by safety filters.
             return {"error": "Final instruction blocked by safety filters", "block_reason": response.prompt_feedback.block_reason}

        # Access the finish reason from the first candidate if candidates exist and finish_reason is present.
        # Use getattr with default for safety. Accessing .name is standard for the FinishReason enum in the new library.
        finish_reason_str = getattr(response.candidates[0].finish_reason, 'name', str(response.candidates[0].finish_reason)) if response.candidates and response.candidates[0].finish_reason else None

        if finish_reason_str:
             print(f"Final response finish reason: {finish_reason_str}")
             # --- Check specifically for MAX_TOKENS ---
             # If the finish reason is MAX_TOKENS, the model stopped because the output token limit was reached.
             # This was the original issue. With the new library and correct config passing, this should be handled better.
             # However, it's still possible depending on response size and model capabilities.
             if finish_reason_str == "MAX_TOKENS": # Check the string name of the finish reason
                  print("Warning: Analysis incomplete due to hitting maximum output tokens.")
                  # Return an error dictionary indicating the MAX_TOKENS issue.
                  # Include the raw response text if available for debugging what was generated before stopping.
                  return {"error": "Gemini analysis incomplete: Maximum output tokens reached.", "raw_response": response.text if response.text else 'N/A', "finish_reason": finish_reason_str}
             # --- Check for other non-STOP finish reasons that might indicate incomplete generation or issues ---
             # 'STOP' is the expected finish reason for successful generation. Other reasons like SAFETY, RECITATION, OTHER, etc., indicate interruption.
             elif finish_reason_str != "STOP":
                  print(f"Warning: Analysis may be incomplete due to non-STOP finish reason: {finish_reason_str}")
                  # Return an error dictionary for other non-STOP finish reasons that prevented successful completion.
                  return {"error": f"Gemini analysis incomplete or stopped due to finish reason: {finish_reason_str}", "raw_response": response.text if response.text else 'N/A', "finish_reason": finish_reason_str}


        # --- Get the generated text (should be a JSON string because response_mime_type was set) ---
        gemini_analysis_text = "" # Initialize as empty string
        try:
            # Attempt to access the text attribute of the response object from the new library.
            # For structured JSON output requests, response.text is expected to contain the JSON string.
            if response.text:
                 gemini_analysis_text = response.text
            # Fallback: If response.text is not directly available (less likely for JSON output with this config), try joining parts.
            elif response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                 # Filter for parts that have a 'text' attribute and whose text is not None.
                 part_texts = [part.text for part in response.candidates[0].content.parts if hasattr(part, 'text') and part.text is not None]
                 gemini_analysis_text = "".join(part_texts)
            else:
                # Log a warning and return an error dictionary if response text/parts are not found as expected.
                print("Warning: Received an unusual response format from Gemini, expected text/JSON.")
                # Include the full raw response object for debugging if possible.
                return {"error": "Received an unusual response format from Gemini, expected text/JSON.", "raw_response": response}

        except Exception as text_access_error:
             # Log an error if accessing response text/parts fails unexpectedly.
             print(f"Warning: Could not access response text/parts: {text_access_error}")
             # Return an error dictionary for text access failures.
             return {"error": f"Could not access Gemini response text: {text_access_error}", "raw_response": response}


        # --- Attempt to parse the generated text as JSON ---
        if not gemini_analysis_text:
             # Log a warning and return an error dictionary if the generated text is empty.
             print("Warning: Gemini returned empty response text.")
             return {"error": "Gemini returned empty response text."}

        try:
            # Parse the received text string as a JSON dictionary.
            # This is the expected output format due to response_mime_type="application/json".
            analysis_json = json.loads(gemini_analysis_text)
            print("Successfully parsed JSON output from Gemini.")
            return analysis_json # Return the parsed JSON dictionary on successful analysis and parsing.

        except json.JSONDecodeError as e:
            # Log an error if JSON parsing fails (this means the AI did not output valid JSON).
            print(f"Failed to parse JSON output from Gemini: {e}")
            # Print the raw text that failed to parse for debugging the AI's output format.
            print("Raw Gemini output that failed parsing:", gemini_analysis_text)
            # Return an error dictionary including the raw output and the JSON parsing error details.
            return {"error": "Failed to parse Gemini JSON output", "raw_output": gemini_analysis_text, "details": str(e)}

        except Exception as e:
             # Log any other unexpected errors after receiving and attempting to parse the response.
             print(f"An unexpected error occurred after receiving Gemini response: {e}")
             # Include the raw output and error details in the returned dictionary.
             print("Raw Gemini output:", gemini_analysis_text)
             return {"error": "An unexpected error occurred after receiving Gemini response", "details": str(e), "raw_output": gemini_analysis_text}


    except Exception as e:
        # Log an error if the final API request itself fails (e.g., network error, API issue, rate limit).
        print(f"An error occurred during the final analysis request: {e}")
        # Check if the error message indicates a 429 rate limit specifically.
        if "429" in str(e):
             print("Rate limit hit on final instruction.")
             # Return an error dictionary for rate limits.
             return {"error": "Rate limit hit on final instruction", "details": str(e)}
        # Return a general error dictionary for other exceptions during the API call.
        return {"error": "Gemini analysis API request failed", "details": str(e)}

# --- End of analyze_with_gemini ---
