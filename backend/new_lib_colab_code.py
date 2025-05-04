import asyncio
import os
import json
import time
import pandas as pd
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from lxml import etree
from google import genai 
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter
from IPython.display import display, Markdown 
from dotenv import load_dotenv 
load_dotenv()

# --- Configuration ---
# Define the list of competitions to include
target_competitions = [
    "Scotland - Premiership"
]

# --- API Key Loading (Simplified) ---
gemini_api_key = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = 'gemini-2.0-flash'

# Gemini Rate Limits (Requests Per Minute, Tokens Per Minute, Requests Per Day)
GEMINI_RPM = 30
GEMINI_TPM = 1_000_000
GEMINI_RPD = 1500 # Note: This is an example limit, check actual limits

# Approximate tokens per character for basic markdown (rough estimate)
# This is a simplification. A proper tokenizer would be more accurate.
# We'll use a chunk size well below the likely context window (e.g., 25000 characters)
# to be safe and leave room for prompt/response.
# Keep CHUNK_SIZE_CHARS as it's related to input handling, not the AI library itself
CHUNK_SIZE_CHARS = 100000 # Aim for chunks of approx 28k characters/tokens

# Rate Limiting Variables (Keep as is)
request_count_minute = 0
last_request_time = time.time()
request_count_day = 0
last_day_reset = datetime.now().day # Simple daily reset based on day change

# --- Define the JSON Schema as a Python Dictionary ---
# This schema tells the model exactly how the output JSON should be structured.
# Added propertyOrdering for best practice from the documentation
MATCH_PREDICTION_SCHEMA = {
  "type": "object",
  "properties": {
    "match": {
      "type": "string",
      "description": "The names of the home and away teams, e.g., 'Home Team vs Away Team'"
    },
    "match_date": {
      "type": "string",
      "description": "The date of the match in YYYY-MM-DD format." # Clarified format based on scraping output
    },
    "match_time": {
      "type": "string",
      "description": "The time of the match in HH:MM format."
    },
    "match_predictions": {
      "type": "array",
      "description": "A list of individual predictions for the match.",
      "items": { # Schema for each item in the array
        "type": "object",
        "properties": {
          "market_category": {
            "type": "string",
            "description": "The category of the betting market, e.g., 'Popular Markets', 'Goals', 'Corners'."
          },
          "event": {
            "type": "string",
            "description": "The specific prediction event, e.g., 'Over 2.5 Goals', 'Both Teams to Score', 'Home Win'."
          },
          "confidence_score": {
            "type": "number", # Use number for float/integer
            "format": "float", # Use format to hint at floating point
            "description": "A numerical score representing the confidence in this specific prediction (e.g., out of 10)."
          },
          "reason": {
            "type": "string",
            "description": "A brief explanation or reasoning behind this specific prediction."
          }
        },
        "required": [
          "market_category",
          "event",
          "confidence_score",
          "reason"
        ],
        "propertyOrdering": [ # Added ordering for prediction items
            "market_category",
            "event",
            "confidence_score",
            "reason"
        ]
      }
    },
    "overall_match_confidence_score": {
      "type": "number",
      "format": "float",
      "description": "A numerical score representing the overall confidence in the match assessment (e.g., out of 10)."
    },
    "general_assessment": {
      "type": "string",
      "description": "A general commentary or assessment of the match context, team form, table position, etc."
    }
  },
  "required": [ # Top-level required properties
    "match",
    "match_date",
    "match_time",
    "match_predictions",
    "overall_match_confidence_score",
    "general_assessment"
  ],
   "propertyOrdering": [ # Added ordering for top-level properties
    "match",
    "match_date",
    "match_time",
    "general_assessment", # Moved general assessment up for potentially better flow
    "overall_match_confidence_score",
    "match_predictions"
  ]
}


# --- Rate Limiting Helper Function (Keep as is) ---
async def wait_for_rate_limit():
    """Waits to respect Gemini API rate limits (RPM and RPD)."""
    global request_count_minute, last_request_time, request_count_day, last_day_reset

    current_time = time.time()
    current_day = datetime.now().day

    # Reset minute count if a new minute has started
    if current_time - last_request_time > 60:
        request_count_minute = 0
        last_request_time = current_time

    # Reset daily count if a new day has started
    if current_day != last_day_reset:
        request_count_day = 0
        last_day_reset = current_day

    # Check daily limit
    if request_count_day >= GEMINI_RPD:
        print("Daily request limit reached. Waiting until next day.")
        # This is a simple wait; a real app might schedule for the next day
        # Calculate time until the start of the next day
        # Handle end of month/year edge cases simply by adding a day; datetime will handle rollovers
        # For a robust app, handle datetime additions more carefully near year/month ends
        try:
            # Attempt to get the start of the next day
            tomorrow = datetime.now().replace(day=current_day + 1, hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
             # Handle month/year rollovers if adding a day goes beyond month length
             from dateutil.relativedelta import relativedelta
             tomorrow = datetime.now() + relativedelta(days=1)
             tomorrow = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)

        time_to_wait = (tomorrow - datetime.now()).total_seconds() + 60 # Add a minute for safety
        if time_to_wait > 0:
            print(f"Waiting for approximately {time_to_wait/60:.2f} minutes.")
            await asyncio.sleep(time_to_wait)
        request_count_day = 0 # Reset after waiting
        last_day_reset = datetime.now().day # Update day reset

    # Check minute limit
    if request_count_minute >= GEMINI_RPM:
        sleep_time = 60 - (current_time - last_request_time)
        if sleep_time > 0:
            print(f"Minute request limit reached. Waiting for {sleep_time:.2f} seconds.")
            await asyncio.sleep(sleep_time)
        request_count_minute = 0 # Reset minute count after waiting
        last_request_time = time.time() # Update last request time

    # Increment counts for the current request
    request_count_minute += 1
    request_count_day += 1

# --- Scraping Function (Keep as is) ---
async def fetch_matches_fixtures():
    """Scrapes match fixtures from soccerstats.com for specified competitions."""
    print(f"Fetching match fixtures for specified competitions...")
    matches_data = []

    async with async_playwright() as p:
        # Using headless=True is recommended for servers/notebooks
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.goto("https://www.soccerstats.com/matches.asp?matchday=1&matchdayn=1")

        # Get HTML content
        page_html = await page.content()

        # Parse with lxml
        tree = etree.HTML(page_html)
        rows = tree.xpath('//table//tr')

        current_competition = None
        # Date should likely be tomorrow's date if fetching tomorrow's matches
        # Let's calculate tomorrow's date
        # The error was here: timedelta was used without being imported.
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        current_date = tomorrow_date # Use tomorrow's date for fetched matches

        i = 0

        while i < len(rows):
            row = rows[i]
            row_class = row.attrib.get('class', '')

            if row_class == 'parent':
                # Update competition name if it's in a "parent" row
                comp = row.xpath('.//font[@size="2"]/text()')
                if comp:
                     current_competition = comp[0].strip()

            elif row_class == 'team1row':
                # Only extract if competition is in the target list
                if current_competition in target_competitions:
                     # Ensure the next row exists and is the corresponding away team row
                     if i + 1 < len(rows) and rows[i + 1].attrib.get('class') == 'team2row':
                         home_team = row.xpath('.//td[@class="steam"]/text()')
                         home_team = home_team[0].strip() if home_team else None

                         time_str = row.xpath('.//td[@rowspan="2"]//font[@size="1"]/text()')
                         time_str = time_str[0].strip() if time_str else None

                         stats_link = row.xpath('.//td[@rowspan="2"]//a[@class="myButton"]/@href')
                         stats_link = "https://www.soccerstats.com/" + stats_link[0] if stats_link else None

                         # Get away team from next row
                         away_team_row = rows[i + 1]
                         away_team = away_team_row.xpath('.//td[@class="steam"]/text()')
                         away_team = away_team[0].strip() if away_team else None

                         # Only add the match if essential details are found
                         if home_team and away_team and time_str and stats_link and current_competition:
                             match_data = {
                                 "competition": current_competition,
                                 "date": current_date, # Use the calculated tomorrow's date
                                 "time": time_str,
                                 "home_team": home_team,
                                 "away_team": away_team,
                                 "stats_link": stats_link
                             }

                             matches_data.append(match_data)
                             i += 1 # Skip the team2row
                         else:
                             print(f"Warning: Found 'team1row' without a following 'team2row' at index {i}. Skipping.")

                # If the competition is not in the target list, skip the next row (team2row) as well
                elif i + 1 < len(rows) and rows[i + 1].attrib.get('class') == 'team2row':
                     i += 1 # Skip the away team row for non-target competitions

            i += 1

        await browser.close()
    print(f"Fetched {len(matches_data)} fixtures from target competitions.")
    return matches_data

# --- Stats Scraping Function (Keep as is) ---
async def fetch_match_stats_markdown(url):
    """Fetches match stats from a given URL and returns as markdown."""
    print(f"Fetching stats from: {url}")
    # crawl4ai requires installation: !pip install crawl4ai
    # Define a content filter (using PruningContentFilter) to clean the content
    prune_filter = PruningContentFilter(
        threshold=0.5, # Adjust this threshold to be more or less aggressive in pruning
        threshold_type="fixed", # Or "dynamic" for adaptive filtering
        min_word_threshold=1 # Ignore blocks with fewer than 1 words
    )

    # Create a Markdown generator and attach the content filter
    md_generator = DefaultMarkdownGenerator(
        content_filter=prune_filter,
        options={
            "ignore_links": True, # Ignore links in the markdown output
            "ignore_images": True # Ignore images in the markdown output
        }
    )


    # Configure the crawl run to use this markdown generator
    run_config = CrawlerRunConfig(
        markdown_generator=md_generator,

        css_selector=".body-text", # Target content within the .body-text div
        excluded_tags=["form", "header", "footer", "nav"], # Remove unwanted HTML tags
        exclude_external_links=True, # Link filtering to remove external and social media links
        exclude_social_media_links=True,
        exclude_external_images=True, # Media filtering: remove external images
    )

    browser_config = BrowserConfig()

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(
            url=url,
            config=run_config
        )
        if not result.success:
            print("Crawl failed:", result.error_message)
            return None
        # crawl4ai returns markdown in result.markdown.raw_markdown
        output_mkdwn = getattr(result.markdown, 'raw_markdown', None)
        if output_mkdwn:
            print("Stats fetched and converted to markdown.")
        else:
            print("Stats fetched, but no markdown content was generated.")
        #print(output_mkdwn)
        return output_mkdwn

# --- AI Interaction Function (MODIFIED for new library and schema approach) ---
# Pass the genai client instance to this function
async def analyze_match_stats_with_gemini(match_data, stats_markdown, genai_client):
    """Sends stats markdown to Gemini for analysis and prediction, requesting JSON output via schema."""
    print(f"Analyzing match: {match_data['home_team']} vs {match_data['away_team']}")

    # --- Define Generation Configuration with Schema ---
    # This config tells the model to output JSON according to the defined schema
    # This structure is correct for the new library as per documentation examples
    json_generation_config = {
        "response_mime_type": "application/json",
        "response_schema": MATCH_PREDICTION_SCHEMA # Pass the schema dictionary here
        # You might also add temperature, top_p, etc., here if needed
        # "temperature": 0.7,
        # "top_p": 0.9,
    }

    # Refined Prompt Strategy (Keep the multi-turn approach):
    # 1. Send the main instruction prompt, clearly stating to generate JSON.
    # 2. Send the markdown content in chunks.
    # 3. Send a final instruction to perform the analysis and generate the JSON, applying the schema config here.

    initial_prompt = f"""
You are an expert MatchStatsBot, a structured data assistant for football analytics.

Your role is to analyze detailed match statistics and forecast a variety of possible events in the match.

I will provide you with the detailed match statistics in one or more parts. Please wait until I indicate that I have sent all the data before performing the analysis.

When I tell you I have sent all the data, you will:

1. Digest and perform a deep analytical breakdown of the match data provided across all parts for the match: {match_data['home_team']} vs {match_data['away_team']}.

2. Predict at least 15 key match events, drawing on a broad spectrum of betting event markets, based on your analysis. Organize your response by market category (see list below). Strongly consider the possibility of draw for every match.

> Market Categories & Options:
i. Popular Markets:
- 1X2
- Double Chance
- Over/Under – Goal
- Both Teams to Score (Yes/No)
- Odd/Even – Goal
- Half Time/Full Time (1/1, 1/X, 1/2, X/1, X/X, X/2, 2/1, 2/X, 2/2)
- Correct Score
- Handicap (1X2)
- Draw No Bet
- Multi Correct Score
-Score in first 5 / 10 / 15 / 20 / 30 minutes
-Both Teams to Score (2+ goals)
-Total Goals (Exact)
-First Team to Score
-Over/Under Asian
-Asian Handicap

ii. First Half Markets:
-1st Half – 1X2
-1st Half – Double Chance
-1st Half – Over/Under
-1st Half – Both Teams to Score
-1st Half – Correct Score
-1st Half – Total Goals
-1st Half – Multi Goal
-1st Half – Odd/Even
-1st Half – Draw No Bet
-Away Score 1st Half
-Home Score 1st Half
-Home/Away Win to Nil 1st Half
-European Handicap 1st Half

iii. Second Half Markets:
-2nd Half – 1X2
-2nd Half – Double Chance
-2nd Half – Over/Under
-2nd Half – Both Teams to Score
-2nd Half – Correct Score
-2nd Half – Total Goals
-2nd Half – Multi Goal
-2nd Half – Odd/Even
-2nd Half – Draw No Bet
-Away Score 2nd Half
-Home Score 2nd Half
-Home/Away Win to Nil 2nd Half
-European Handicap 2nd Half

iv. Goal Markets:
-Multi Goal
-Home Goals Exact
-Away Goals Exact
-Highest Scoring Half
-Multi Goal Home / Away
-Last Team to Score
-Goal/No Goal HT & 2nd HT (GG/GG, GG/NG, NG/GG, NG/NG)
-Total Goals 1st + 2nd Half

v. Home / Away Markets:
- Home/Away – Over/Under – Goal
-Home No Bet / Away No Bet
-Home/Away Win to Nil
-Home/Away Score Both Halves
-Home/Away Win Either Half / Both Halves
-Odd/Even – Goal Home / Away
-Highest Scoring Half – Home / Away Team
-1st & 2nd Half – Home/Away Over/Under – Goal
-Home To Score / Away To Score
-Clean Sheet – Home / Away
-Half‑1st‑Goal – Home / Away (1st half / no goal / 2nd half)
-Team To Score number of goals in a row”

vi. Combined Markets:
-1X2 & Over/Under
-1X2 & Goal/No Goal (GG/NG)
-Double Chance & Over/Under
-Double Chance & Goal/No Goal
-1X2 or Over/Under variants (e.g. Over 1.5/Under 1.5)
-HT/FT & Over/Under
-Chance Mix (various HT/FT or GG combos)
- First Goal & 1X2

vii. Corner Markets
-1X2 Corner
-Corner Over/Under (full & per half)
-Corner Odd/Even
-First / Last Corner (full & half)
-Corners HT/FT
-Corner Handicap / Asian Handicap (full & half)
-Multi Corner (full & half)
-Number of Corners
-Corners in 10 Minutes

viii. Other Markets:
-Minute to First Goal (0–15, 16–30, 31–45+, etc.)
-Short‑term 1X2 (5, 10, 15, 20, 30, 60 minutes)
-HT/FT Correct Score
-Winning Margin
-Penalty / Penalty Scored or Missed
-Goal in Injury Time
-“At Least a Half” X
-Team To Score: GG / Only Home / Only Away / No Goal
-Half‑1st‑Goal: First Half / No Goal / Second Half

3. Assign a confidence score out of 10 (as a floating-point number) and provide a clear, concise reason for each predicted event, grounded in your analysis. the confidence score should be highly correlate with the event possibility, and also reason should be supported by stats.

4. Generate an overall match confidence score and a general assessment of the match.

**IMPORTANT:** Your FINAL output MUST be a single JSON object, structured exactly according to the schema provided via the API configuration. Do NOT include any other text, explanations, or formatting before or after the JSON object. Populate the JSON fields using the match data (like teams, date, time) and your analysis results.
"""


    # Start a new chat session for this analysis using the new client
    try:
        # NEW: Create the chat session using the client instance and specifying the model
        chat = genai_client.chats.create(model=GEMINI_MODEL, history=[])
        print("New Gemini chat started for analysis.")
    except Exception as e:
        print(f"Error starting Gemini chat session: {e}")
        return None

    # Send the initial prompt
    print("Sending initial prompt to Gemini...")
    await wait_for_rate_limit() # Wait before sending prompt
    try:
        # Send the initial prompt in the chat
        response = chat.send_message(initial_prompt)
        # print("Gemini response to prompt:", response.text) # Optional print
    except Exception as e:
        print(f"Error sending initial prompt to Gemini: {e}")
        return None

    # Send the markdown in chunks
    if stats_markdown:
        chunks = [stats_markdown[i:i + CHUNK_SIZE_CHARS] for i in range(0, len(stats_markdown), CHUNK_SIZE_CHARS)]
        print(f"Markdown split into {len(chunks)} chunks.")
        for i, chunk in enumerate(chunks):
            chunk_message = f"Match Stats Data Part {i + 1}/{len(chunks)}:\n\n{chunk}"
            print(f"Sending chunk {i + 1}...")
            await wait_for_rate_limit() # Wait before sending each chunk
            try:
                # Send the chunk in the chat
                response = chat.send_message(chunk_message)
                # print(f"Gemini response to chunk {i+1}:", response.text) # Optional print
            except Exception as e:
                print(f"Error sending chunk {i + 1} to Gemini: {e}")
                # Decide how to handle errors here - maybe try resending or skip?
                pass # For now, just print and continue

        # Send the final instruction to analyze and generate the JSON output
        final_instruction = f"""
I have now sent all parts of the match statistics for the match: {match_data['home_team']} vs {match_data['away_team']}.

Please perform the analysis based on ALL the data provided in the previous messages and generate the match prediction JSON object as requested in the initial prompt, adhering strictly to the API's configured schema.

**AGAIN, your FINAL output MUST be ONLY the JSON object.** Do NOT include any other text, explanations, or formatting before or after the JSON object.
"""
        print("Sending final instruction to Gemini and requesting JSON output...")
        await wait_for_rate_limit() # Wait before sending final instruction
        try:
            # This is where we apply the generation_config for JSON output using the new library
            # Apply the config to the final message that triggers the JSON generation
            response = chat.send_message(
                final_instruction,
                config=json_generation_config # Apply the JSON schema config here
            )

            # Get the final analysis from Gemini. Since we requested JSON with schema,
            # response.text should contain the JSON string.
            gemini_analysis = ""
            try:
                 # Access the text attribute of the response from the new library
                 gemini_analysis = response.text
            except Exception as text_access_error:
                 print(f"Warning: Could not access response.text directly: {text_access_error}")
                 # Fallback if .text is not available as expected (structure might slightly differ in new library)
                 # This fallback might need adjustment based on actual new library response structure
                 # Inspect the response object if this error occurs
                 if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                      # Assuming parts still exist and have text attribute
                      part_texts = [part.text for part in response.candidates[0].content.parts if hasattr(part, 'text')]
                      gemini_analysis = "".join(part_texts)
                 else:
                     gemini_analysis = "Received an unusual response format for the final analysis, expected JSON."
                     print("Warning: ", gemini_analysis)


            return gemini_analysis

        except Exception as e:
            print(f"An error occurred during the final analysis request: {e}")
            # Depending on the error, you might want to inspect response.prompt_feedback
            # print("Prompt Feedback:", response.prompt_feedback) # Uncomment to debug if needed
            return None
    else:
        print("No stats markdown available to send for analysis.")
        return "No stats data available for analysis."


# --- Main Execution Flow (MODIFIED for new client initialization and key check) ---
async def main():
    """Main function to orchestrate the scraping and analysis."""

    # --- Initialize Gemini Client (MODIFIED) ---
    # Check if the API key was loaded successfully from the environment
    global gemini_api_key
    if not gemini_api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        print("Please set your API key in a .env file or your system's environment variables.")
        return # Exit if API key is not available

    try:
        # NEW: Initialize the client directly with the API key
        genai_client = genai.Client(api_key=gemini_api_key)
        print(f"Gemini client initialized for model: {GEMINI_MODEL}.")
        # No longer need to create a separate model instance here to pass to the analysis function
        # The analysis function will create the chat session using the client and specify the model

    except Exception as e:
        print(f"Error initializing Gemini client: {e}")
        return

    # --- Fetch Fixtures (Keep as is) ---
    fixtures = await fetch_matches_fixtures()

    if not fixtures:
        print("No fixtures found to process.")
        return

    print(f"\nProcessing {len(fixtures)} matches...")

    # --- Process Each Match (MODIFIED to pass the client) ---
    for i, match in enumerate(fixtures):
        print(f"\n--- Processing Match {i + 1}/{len(fixtures)} ---")
        print(f"Match: {match['home_team']} vs {match['away_team']}")

        # Fetch Stats Markdown (Keep as is)
        stats_markdown = await fetch_match_stats_markdown(match['stats_link'])
        print('markdown_length: ',len(stats_markdown))

        if stats_markdown:
            # Analyze Stats with Gemini (MODIFIED to pass the client instance)
            analysis_result = await analyze_match_stats_with_gemini(match, stats_markdown, genai_client) # Pass the client here

            if analysis_result:
                print("\n--- Analysis Result ---")
                # Attempt to parse the JSON output (Keep as is, assumes response.text is JSON)
                try:
                    analysis_json = json.loads(analysis_result)
                    # You can now work with the parsed JSON data
                    # For example, print it or process it further
                    print(json.dumps(analysis_json, indent=2)) # Pretty print the JSON
                except json.JSONDecodeError as e:
                     print(f"Failed to parse JSON output from Gemini: {e}")
                     print("Raw Gemini output:")
                     print(analysis_result) # Print raw output for debugging
                except Exception as e:
                     print(f"An unexpected error occurred while processing analysis result: {e}")
                     print("Raw Gemini output:")
                     print(analysis_result) # Print raw output for debugging

                print("-----------------------")
            else:
                print("\nAnalysis failed for this match.")
        else:
            print("Skipping analysis due to failed stats fetch.")

        # Implement a delay between processing matches to help manage rate limits (Keep as is)
        if i < len(fixtures) - 1: # Don't wait after the last match
            delay_between_matches = 15 # seconds, increased slightly for safety
            print(f"Waiting for {delay_between_matches} seconds before next match...")
            await asyncio.sleep(delay_between_matches)


    print("\n--- Processing Complete ---")

# --- Main Execution Block (Simplified) ---
if __name__ == "__main__":
    # The API key is loaded at the top using load_dotenv and os.environ.get
    # We just need to check if it was successfully loaded before running main.
    if gemini_api_key:
         asyncio.run(main()) # Use asyncio.run to execute the main async function
    else:
         print("Cannot run main function: API key is not set.")