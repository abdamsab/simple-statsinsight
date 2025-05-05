# backend/shared/utils.py

# This file contains common utility functions used across the backend.

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional

# --- Rate Limiting Variables (Moved here from backend/features/football_analytics/services/analyzer.py) ---
# Keep these module-level variables to maintain state across calls.
# They track the number of requests within the current minute and day.
# These are global within this module (shared within the same process).
request_count_minute = 0
last_request_time = time.time() # Timestamp of the last request initiation or minute reset
request_count_day = 0
last_day_reset = datetime.now().day # Stores the day number when the daily count was last reset (simple approach)


# --- Rate Limiting Helper Function (Moved here from backend/features/football_analytics/services/analyzer.py) ---
# This asynchronous function is called before each API request to manage rate limits.
# It takes rate limits (RPM, RPD) and the model name for conditional sleep.
async def wait_for_rate_limit(
    rpm_limit: Optional[int] = None, # Pass RPM limit from parameters_config
    rpd_limit: Optional[int] = None, # Pass RPD limit from parameters_config
    model_name: Optional[str] = None # Pass model_name
):
    """
    Waits if necessary to respect Rate Per Minute (RPM) and Rate Per Day (RPD) limits.
    Limits are passed from the parameters configuration.
    Applies a conditional sleep based on the model name (e.g., longer for pro models).
    Assumes this function is called before each AI API request.
    """
    global request_count_minute, last_request_time, request_count_day, last_day_reset

    current_time = time.time()
    current_day = datetime.now().day

    # --- Daily Limit Reset ---
    if current_day != last_day_reset:
        print("Daily rate limit reset.")
        request_count_day = 0
        last_day_reset = current_day

    # --- Minute Limit Reset ---
    if current_time - last_request_time >= 60:
        # print("Minute rate limit window reset.")
        request_count_minute = 0
        last_request_time = current_time

    # --- Check Limits and Wait if Necessary ---
    if rpd_limit is not None and rpd_limit > 0:
        if request_count_day >= rpd_limit:
            print(f"Daily rate limit ({rpd_limit}) reached. Waiting for next day...")
            sleep_time = 3600
            print(f"Sleeping for {sleep_time} seconds due to daily limit.")
            await asyncio.sleep(sleep_time)

    if rpm_limit is not None and rpm_limit > 0:
        if request_count_minute >= rpm_limit:
            print(f"Minute rate limit ({rpm_limit}) reached. Waiting for next minute...")
            elapsed_time = current_time - last_request_time
            sleep_time = 60 - elapsed_time if elapsed_time < 60 else 0
            if sleep_time > 0:
                print(f"Sleeping for {sleep_time:.2f} seconds due to minute limit.")
                await asyncio.sleep(sleep_time)
            request_count_minute = 0
            last_request_time = time.time()

    # --- Apply Conditional Delay based on Model ---
    if model_name:
         model_delays = {
             "gemini-1.0-pro": 0.5,
             "gemini-1.5-pro-latest": 0.7,
             "gemini-2.0-flash": 0.2
         }
         delay = model_delays.get(model_name.lower(), 0)

         if delay > 0:
             await asyncio.sleep(delay)

    # --- Increment Counts AFTER waiting ---
    request_count_minute += 1
    request_count_day += 1

# --- Other potential utility functions can be added here ---