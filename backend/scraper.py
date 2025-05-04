# backend/scraper.py

import asyncio
import os
from datetime import datetime, timedelta
from playwright.async_api import async_playwright
from lxml import etree
# Need imports from pymongo for working with collection object
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

# Import database module to access database functions like find_many
from . import database # Added import for database module

from typing import Any # Import Any for type hints


# --- Scraping Function: Fetch Fixture List ---
# Updated to accept fixture_url, competitions_collection, and target_match_date_str as parameters
async def fetch_matches_fixtures(fixture_url: str, competitions_collection: Collection, target_match_date_str: str):
    """
    Scrapes match fixtures from a URL for specified competitions,
    filtering by competition status in the database.
    Stamps fetched matches with the provided target_match_date_str.
    """
    print(f"Fetching match fixtures from {fixture_url}...")
    matches_data = []
    active_competitions = []
    browser = None # Initialize browser to None


    # --- Step 1: Get list of active competitions from the database ---
    # We need database.find_many, which requires the database module.
    # Ensure competitions_collection is not None before querying
    if competitions_collection is None:
        print("Error: Competitions collection not initialized. Cannot filter fixtures.")
        # Proceeding without filtering if collection is not available
        # Or you might choose to return [] here
        # In this case, we will return [] if collection is None as we cannot filter
        return []


    try:
        # Find all competition documents where status is True
        print("Querying database for active competitions...")
        # Use asyncio.to_thread as find() is synchronous (preserving your implementation)
        cursor = await asyncio.to_thread(competitions_collection.find, {"status": True})
        # Fetch all results from the cursor
        comp_docs = await asyncio.to_thread(list, cursor)

        if comp_docs:
            active_competitions = [doc.get("name") for doc in comp_docs if doc.get("name")]
            print(f"Found {len(active_competitions)} active competitions in the database: {active_competitions}")
        else:
            print("No active competitions found in the database. Skipping fixture scraping.")
            return [] # Return empty list if no active competitions


    except PyMongoError as e:
        print(f"MongoDB Error fetching active competitions: {e}")
        print("Proceeding with fixture scraping without database filtering due to error.")
        # Clear active_competitions list so no filtering happens in the scraping loop
        # Setting to [] means no filtering will be applied in the loop below.
        active_competitions = [] # Set to empty list to indicate no filtering available
    except Exception as e:
         print(f"An unexpected error occurred while fetching active competitions: {e}")
         print("Proceeding with fixture scraping without database filtering due to error.")
         active_competitions = [] # Set to empty list to indicate no filtering available


    # Return empty list if no active competitions were found and no DB error occurred that allowed proceeding without filtering
    # This check was slightly redundant before, now we check if active_competitions is empty *and* was not set to None by an error.
    # A more robust check is just after the DB query results. Let's keep this for clarity.
    # If active_competitions is [] here, it means the query found none, so we return [].
    # If an error occurred and set active_competitions to [], we will still proceed to scrape but filter nothing.
    if not active_competitions: # Check if the list is empty after the query or error
         print("No active competitions available after database query. Returning empty fixtures list.")
         # Note: If a DB error happened and set active_competitions to [], this will still return [] here.
         # If you want to proceed without filtering on DB error, you'd remove this 'if' block entirely after the try/except.
         # Let's keep the original logic that returns [] if no *active* competitions are found after the query.
         # The error handling above now sets active_competitions to [] on error, so this check still works.
         # However, the original code had `active_competitions = None` on error, let's stick to that logic.
         if active_competitions is None: # If DB query failed and set to None
             print("Database error prevented fetching active competitions. Attempting to scrape without filtering.")
             # Don't return [], continue scraping without filtering.
         elif not active_competitions: # If DB query found no active competitions
             print("No active competitions found in DB query result. Returning empty fixtures list.")
             return []


    # --- Step 2: Scrape fixtures from the URL ---
    print(f"Scraping fixtures from URL: {fixture_url}")
    try:
        async with async_playwright() as p:
            # Use a default headless mode for browser
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                 await page.goto(fixture_url, timeout=60000, wait_until="domcontentloaded") # Add timeout and wait_until
                 page_html = await page.content()
            except Exception as e:
                 print(f"Error navigating to or getting content from {fixture_url}: {e}")
                 # Close browser on navigation/content error
                 if browser:
                      await browser.close()
                 return [] # Return empty list on navigation/content error


            # Browser closing is now in finally block for guaranteed execution


            tree = etree.HTML(page_html)
            rows = tree.xpath('//table//tr')

            current_competition = None
            # --- REMOVED: Hardcoded date calculation ---
            # Assume fixture date is tomorrow unless explicitly stated otherwise on the page # REMOVED
            # tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d') # REMOVED
            # current_date = tomorrow_date # Default date # REMOVED
            # --- END REMOVED ---


            i = 0
            while i < len(rows):
                row = rows[i]
                row_class = row.attrib.get('class', '')

                if row_class == 'parent':
                    comp = row.xpath('.//font[@size="2"]/text()')
                    if comp:
                        current_competition = comp[0].strip()

                elif row_class == 'team1row':
                    # --- Step 3: Filter by active competitions ---
                    # Check if filtering is active (active_competitions is not None)
                    # AND if the current competition is in the active list OR if there was a DB error (active_competitions is None)
                    # This matches your original logic: proceed if filtering is off OR if competition is active.
                    if active_competitions is None or (current_competition and current_competition in active_competitions):
                        # Only process if filtering is off OR if competition is active
                        if i + 1 < len(rows) and rows[i + 1].attrib.get('class') == 'team2row':
                            home_team = row.xpath('.//td[@class="steam"]/text()')
                            home_team = home_team[0].strip() if home_team else None

                            time_str = row.xpath('.//td[@rowspan="2"]//font[@size="1"]/text()')
                            time_str = time_str[0].strip() if time_str else None

                            stats_link = row.xpath('.//td[@rowspan="2"]//a[@class="myButton"]/@href')
                            stats_link = "https://www.soccerstats.com/" + stats_link[0] if stats_link else None

                            away_team_row = rows[i + 1]
                            away_team = away_team_row.xpath('.//td[@class="steam"]/text()')
                            away_team = away_team[0].strip() if away_team else None

                            # Ensure required data is present
                            if home_team and away_team and time_str and stats_link and current_competition:
                                match_data = {
                                    "competition": current_competition,
                                    # --- CORRECTED: Use the target_match_date_str passed to the function ---
                                    "date": target_match_date_str, # Use the date passed from main.py
                                    # --- END CORRECTED ---
                                    "time": time_str,
                                    "home_team": home_team,
                                    "away_team": away_team,
                                    "stats_link": stats_link
                                }
                                matches_data.append(match_data)
                                i += 1 # Skip the next row as it's the team2row we just processed
                            else:
                                 print(f"Warning: Missing data for match at index {i} in competition {current_competition}. Skipping.")
                        else:
                             print(f"Warning: Found 'team1row' without a following 'team2row' at index {i} in competition {current_competition}. Skipping.")
                    # If filtering is active (active_competitions is not None) and competition is NOT in the active list,
                    # check if the next row is 'team2row' and skip it as well.
                    # Only do this if active_competitions is not None (i.e., filtering was attempted).
                    elif active_competitions is not None and i + 1 < len(rows) and rows[i + 1].attrib.get('class') == 'team2row':
                        i += 1


                i += 1 # Move to the next row (or the one after team2row if skipped)


    except Exception as e:
        # Catch any exception during the scraping process (e.g., network errors, parsing issues).
        print(f"An error occurred during fixtures scraping: {e}")
        # Ensure the browser is closed even if an error occurs.
        # Browser closing is handled in the finally block now for all exit paths.
        # await browser.close() # REMOVED this line
        # Return the list of matches scraped so far (might be partial) or an empty list if the error occurred early.
        print("Returning potentially partial or empty fixtures list due to error.")
        return matches_data # Return the list as is up to the error point.


    finally:
        # Ensure the browser is always closed when the function finishes or an error occurs.
        if browser: # Check if browser object was successfully created before trying to close
            await browser.close()
            # print("Browser closed.") # Optional debug print


    # Log the total number of fixtures fetched.
    print(f"Finished scraping. Found {len(matches_data)} fixtures after filtering by database status.")
    return matches_data

# --- Scraping Function: Fetch Match Stats/Results Markdown ---
# Remains largely the same, accepts a URL parameter
async def fetch_match_stats_markdown(url: str):
    """Fetches match stats from a given URL and returns as markdown."""
    print(f"Fetching stats/results markdown from: {url}")
    prune_filter = PruningContentFilter(
        threshold=0.5,
        threshold_type="fixed",
        min_word_threshold=1
    )

    md_generator = DefaultMarkdownGenerator(
        content_filter=prune_filter,
        options={
            "ignore_links": True,
            "ignore_images": True
        }
    )

    run_config = CrawlerRunConfig(
        markdown_generator=md_generator,
        css_selector=".body-text",  # Target content within the .body-text div
        excluded_tags=["form", "header", "footer", "nav"],  # Remove unwanted HTML tags
        exclude_external_links=True,       # Link filtering to remove external and social media links
        exclude_social_media_links=True,
        exclude_external_images=True,  # Media filtering: remove external images
    )

    browser_config = BrowserConfig()

    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            # Add a timeout for the crawl run
            result = await crawler.arun(
                url=url,
                config=run_config,
                timeout=60000 # 60 second timeout for the crawl run
            )
        except Exception as e:
             print(f"Error during crawling {url}: {e}")
             return None

        if not result or not result.success: # Check result existence and success status
            print("Crawl failed:", result.error_message if result else "No result object")
            return None
        output_mkdwn = getattr(result.markdown, 'raw_markdown', None)
        if output_mkdwn:
            print("Stats/results fetched and converted to markdown.")
        else:
            print("Stats fetched, but no markdown content was generated.")
        return output_mkdwn

# --- End of scraper.py ---