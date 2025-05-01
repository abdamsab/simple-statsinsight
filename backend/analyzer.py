import json
import time
from datetime import datetime , timedelta
from typing import Any # For type hinting in input_data
import google.generativeai as genai
from pymongo.errors import PyMongoError


# Rate Limiting Variables
request_count_minute = 0
last_request_time = time.time()
request_count_day = 0
last_day_reset = datetime.now().day


# --- Rate Limiting Helper Function ---
# Uses global rate limiting variables and takes limits as arguments
# Needs datetime and time imported
async def wait_for_rate_limit(rpm_limit: int | None, rpd_limit: int | None):
    """Waits to respect AI API rate limits (RPM and RPD), taking limits as arguments."""
    # Ensure limits are non-None integers > 0 for checks
    rpm_limit = rpm_limit if isinstance(rpm_limit, int) and rpm_limit > 0 else None
    rpd_limit = rpd_limit if isinstance(rpd_limit, int) and rpd_limit > 0 else None


    global request_count_minute, last_request_time, request_count_day, last_day_reset

    current_time = time.time()
    current_day = datetime.now().day

    # Reset minute count if a minute has passed
    if current_time - last_request_time > 60:
        request_count_minute = 0
        last_request_time = current_time

    # Reset daily count if a new day has started
    # Using day number check - might need more robust date comparison for edge cases
    if current_day != last_day_reset:
        request_count_day = 0
        last_day_reset = current_day

    # Check daily limit BEFORE incrementing
    if rpd_limit is not None and request_count_day >= rpd_limit:
        print("Daily request limit reached. Waiting until next day.")
        # Calculate time until start of next day
        now = datetime.now()
        tomorrow = now + timedelta(days=1)
        midnight_tomorrow = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
        sleep_seconds = (midnight_tomorrow - now).total_seconds()
        print(f"Sleeping for {sleep_seconds:.2f} seconds.")
        await asyncio.sleep(sleep_seconds)
        request_count_day = 0 # Reset after waiting
        last_day_reset = datetime.now().day # Update last reset day
        last_request_time = time.time() # Also reset minute timer


    # Check minute limit BEFORE incrementing
    if rpm_limit is not None and request_count_minute >= rpm_limit:
        sleep_time = 60 - (current_time - last_request_time)
        if sleep_time > 0:
            print(f"Minute request limit reached. Waiting for {sleep_time:.2f} seconds.")
            await asyncio.sleep(sleep_time)
        request_count_minute = 0 # Reset after waiting
        last_request_time = time.time() # Update last reset time


    # Increment counts for the current request *after* waiting
    request_count_minute += 1
    request_count_day += 1
    # print(f"Debug: Request sent. Minute count: {request_count_minute}, Day count: {request_count_day}") # Optional debug print


# --- Generalized AI Analysis Function ---
# Takes AI model, input data, prompts, schema, and params as arguments
async def analyze_with_gemini(
    model: genai.GenerativeModel,
    input_data: str | list[Any] | None, # Accepts stats markdown (str), list (e.g., for post-match JSON/text), or None
    initial_prompt_string: str, # Accepts the pre-formatted initial prompt string
    final_instruction_string: str, # Accepts the final instruction string (pre-formatted if needed)
    output_schema: dict, # Accepts the schema dictionary to use
    rpm_limit: int | None = None,
    rpd_limit: int | None = None,
    tpm_limit: int | None = None, # TPM limit included but not strictly enforced in wait_for_rate_limit yet
    # number_of_predicted_events is primarily for prompt formatting, handled by caller
     number_of_predicted_events: int | None = None
    chunk_size_chars: int | None = None # --- NEW PARAMETER ---
):
    """
    Sends data to Gemini for analysis and prediction/analysis, requesting JSON output via schema.
    Generalized for pre-match and post-match tasks.
    """
    # Use a default chunk size if none is provided (e.g., 28000 as a fallback)
    effective_chunk_size = chunk_size_chars if isinstance(chunk_size_chars, int) and chunk_size_chars > 0 else 28000
    # print(f"Debug: Using chunk size: {effective_chunk_size}") # Optional debug


    if model is None:
        print("Error: AI model not initialized.")
        return {"error": "AI model not initialized."}
    if not initial_prompt_string or not final_instruction_string or not output_schema:
        print("Error: Missing prompt, instruction, or schema for analysis.")
        # Print which one is missing for better debugging
        print(f"Debug: initial_prompt_string is None/empty: {not initial_prompt_string}")
        print(f"Debug: final_instruction_string is None/empty: {not final_instruction_string}")
        print(f"Debug: output_schema is None/empty: {not output_schema}")
        return {"error": "Missing analysis configuration."}

    print("Starting AI analysis...")

    # --- Define Generation Configuration with the Schema ---
    # Uses the schema dictionary passed as an argument
    json_generation_config = genai.GenerationConfig(
        response_mime_type="application/json",
        response_schema=output_schema,
        # Add token limits from parameters if needed for generation_config
        # max_output_tokens=...
        # top_k=...
        # top_p=...
        # temperature=...
    )

    try:
        # Start a new chat session
        # History management for multi-turn prompts is done here
        chat = model.start_chat(history=[])
        print("New Gemini chat started for analysis.")
    except Exception as e:
        print(f"Error starting Gemini chat session: {e}")
        return {"error": "Failed to start Gemini chat session", "details": str(e)}

    print("Sending initial prompt to Gemini...")
    # Use the wait_for_rate_limit helper
    await wait_for_rate_limit(rpm_limit, rpd_limit)
    try:
        # Send the initial prompt (pre-formatted by the caller)
        response = chat.send_message(initial_prompt_string)
        # Optional: Add initial prompt response to history if needed for context in later turns
        # Gemini library often handles history automatically, verify behavior.
        # print(f"Debug: Initial prompt response: {response.text[:100]}...") # Optional debug print

    except Exception as e:
        print(f"Error sending initial prompt to Gemini: {e}")
        # Consider checking response.prompt_feedback for rejection reasons
        # Check if response object exists before accessing feedback
        feedback = getattr(response, 'prompt_feedback', None) if 'response' in locals() else None
        if feedback:
             print(f"Prompt feedback: {feedback}")
        return {"error": "Failed to send initial prompt to Gemini", "details": str(e)}


    # --- Send Input Data (Markdown or JSON/Results) ---
    # input_data can be a string (markdown) or a list (e.g., [json_string, results_string])
    if input_data is not None:
        if isinstance(input_data, str):
            # Assuming input_data is markdown for pre-match
            print("Sending markdown input data...")
            # Split large markdown into chunks using the effective chunk size
            chunks = [input_data[i:i + effective_chunk_size] for i in range(0, len(input_data), effective_chunk_size)]
            print(f"Markdown split into {len(chunks)} chunks.")
            for i, chunk in enumerate(chunks):
                chunk_message = f"Data Part {i + 1}/{len(chunks)}:\n\n{chunk}"
                print(f"Sending chunk {i + 1}...")
                await wait_for_rate_limit(rpm_limit, rpd_limit)
                try:
                    response = chat.send_message(chunk_message)
                    # print(f"Debug: Chunk {i+1} response: {response.text[:50]}...") # Optional debug print
                except Exception as e:
                    print(f"Error sending chunk {i + 1} to Gemini: {e}")
                    # Decide how to handle chunk errors - continue or fail? Let's fail the analysis for this match.
                    return {"error": f"Failed to send data chunk {i+1} to Gemini", "details": str(e)}

        elif isinstance(input_data, list):
             # Assuming input_data is a list of messages for post-match (e.g., pre-match JSON text, results text)
             print("Sending list of input data messages...")
             for i, message_content in enumerate(input_data):
                  if not isinstance(message_content, (str, dict)): # Check if message content is string or dict
                      print(f"Warning: Input message content {i+1} is not string or dict ({type(message_content)}). Skipping.")
                      continue # Skip non-string/non-dict items in the list

                  message_label = f"Input Message {i + 1}/{len(input_data)}"
                  print(f"Sending {message_label}...")
                  await wait_for_rate_limit(rpm_limit, rpd_limit)
                  try:
                      # Send message content (can be string or dict/JSON object)
                      response = chat.send_message(message_content)
                      # print(f"Debug: Message {i+1} response: {response.text[:50]}...") # Optional debug print
                  except Exception as e:
                      print(f"Error sending {message_label} to Gemini: {e}")
                      # Decide how to handle - fail process or continue? Let's fail the analysis for this match.
                      return {"error": f"Failed to send input message {i+1} to Gemini", "details": str(e)}

        else:
            print(f"Warning: Unexpected input_data type: {type(input_data)}. Skipping data sending.")
            # Decide how to handle - fail process or continue? Let's fail the analysis for this match.
            return {"error": f"Unexpected input data type: {type(input_data)}"}

    else:
        print("No input data provided to send for analysis.")
        # Decide how to handle - is no data valid for this prompt/schema? Let's return error if data is expected.
        # Based on prompts, data is expected.
        return {"error": "No input data provided for analysis."}


    # --- Send Final Instruction and Request JSON Output ---
    # The final_instruction string is assumed to be pre-formatted by the caller if needed.
    print("Sending final instruction to Gemini and requesting JSON output...")
    await wait_for_rate_limit(rpm_limit, rpd_limit)
    try:
        response = chat.send_message(
            final_instruction_string, # Use the final instruction string passed in
            generation_config=json_generation_config # Use the generation config with the passed output_schema
        )

        # --- Process the Response ---
        # Check safety ratings and prompt feedback first
        if response and response.prompt_feedback and response.prompt_feedback.block_reason:
             print(f"Prompt blocked: {response.prompt_feedback.block_reason}")
             return {"error": "Prompt blocked by safety filters", "block_reason": response.prompt_feedback.block_reason}
        if response and response.candidates:
            candidate = response.candidates[0] # Get the first candidate
            if candidate and candidate.finish_reason:
                print(f"Gemini finish reason: {candidate.finish_reason}")
                if candidate.finish_reason != 'STOP':
                    # Handle other finish reasons like MAX_TOKENS, SAFETY, etc.
                    print(f"Warning: Analysis may be incomplete due to finish reason: {candidate.finish_reason}")
                    # Decide how to handle - return incomplete, return error? Let's return an error indicating potential issue.
                    return {"error": f"Gemini analysis incomplete or stopped due to finish reason: {candidate.finish_reason}", "raw_response": response}


        # Attempt to get the text response (which should be JSON due to schema)
        gemini_analysis_text = ""
        try:
            gemini_analysis_text = response.text
        except Exception as text_access_error:
             print(f"Warning: Could not access response.text directly: {text_access_error}")
             # Fallback to parts if response.text is not available
             if response and response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                  gemini_analysis_text = "".join([part.text for part in response.candidates[0].content.parts])
             else:
                print("Warning: Received an unusual response format, expected text/JSON.")
                # Decide how to handle - return error or empty? Return error.
                return {"error": "Received an unusual response format, expected text/JSON.", "raw_response": response}

        # Attempt to parse the JSON output
        if not gemini_analysis_text:
             print("Warning: Gemini returned empty response text.")
             return {"error": "Gemini returned empty response text."}

        try:
            analysis_json = json.loads(gemini_analysis_text)
            print("Successfully parsed JSON output from Gemini.")
            return analysis_json # Return the parsed JSON dictionary
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON output from Gemini: {e}")
            print("Raw Gemini output:", gemini_analysis_text)
            # Return error with raw output for debugging
            return {"error": "Failed to parse Gemini JSON output", "raw_output": gemini_analysis_text, "details": str(e)}
        except Exception as e:
             print(f"An unexpected error occurred after receiving Gemini response: {e}")
             print("Raw Gemini output:", gemini_analysis_text)
             # Return error with details and raw output
             return {"error": "An unexpected error occurred after receiving Gemini response", "details": str(e), "raw_output": gemini_analysis_text}

    except Exception as e:
        print(f"An error occurred during the final analysis request: {e}")
        # Return error with details
        return {"error": "Gemini analysis API request failed", "details": str(e)}


# Note: This module does NOT initialize the Gemini client.
# The model instance is initialized in main.py and passed to analyze_with_gemini.
# Rate limiting state variables are global within this module.
# This module does NOT import schema definitions. It receives them as parameters.
# CHUNK_SIZE_CHARS is NOT defined here anymore, it's passed as a parameter.