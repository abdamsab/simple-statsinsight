# backend/features/football_analytics/services/scraper.py

# This file implements the scraping of external websites for football data.

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

# Import database module from its new location
from ....db import mongo_client as database # Adjusted import path (up three levels, then into db)

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
    # We need database.find_many, which requires the database module from db/.
    # Ensure competitions_collection is not None before querying
    if competitions_collection is None:
        print("Error: Competitions collection not initialized. Cannot filter fixtures.")
        return []


    try:
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
            return []


    except PyMongoError as e:
        print(f"MongoDB Error fetching active competitions: {e}")
        print("Proceeding with fixture scraping without database filtering due to error.")
        # Clear active_competitions list so no filtering happens in the scraping loop
        active_competitions = []
    except Exception as e:
         print(f"An unexpected error occurred while fetching active competitions: {e}")
         print("Proceeding with fixture scraping without database filtering due to error.")
         active_competitions = []


    # Return empty list if no active competitions were found after a successful query.
    # If a DB error occurred and set active_competitions to [], we still proceed without filtering.
    if not active_competitions and active_competitions is not None: # Check if the list is empty AND was not set to None by an error
         print("No active competitions found in DB query result. Returning empty fixtures list.")
         return []
    elif active_competitions is None: # If DB query failed and set to None
         print("Database error prevented fetching active competitions. Attempting to scrape without filtering.")
         # Don't return [], continue scraping without filtering.


    # --- Step 2: Scrape fixtures from the URL ---
    print(f"Scraping fixtures from URL: {fixture_url}")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                 await page.goto(fixture_url, timeout=60000, wait_until="domcontentloaded") # Add timeout and wait_until
                 page_html = await page.content()
            except Exception as e:
                 print(f"Error navigating to or getting content from {fixture_url}: {e}")
                 if browser:
                      await browser.close()
                 return []


            tree = etree.HTML(page_html)
            rows = tree.xpath('//table//tr')

            current_competition = None


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
                    if active_competitions is None or (current_competition and current_competition in active_competitions):
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

                            if home_team and away_team and time_str and stats_link and current_competition:
                                match_data = {
                                    "competition": current_competition,
                                    "date": target_match_date_str, # Use the date passed from main.py/services.py
                                    "time": time_str,
                                    "home_team": home_team,
                                    "away_team": away_team,
                                    "stats_link": stats_link
                                }
                                matches_data.append(match_data)
                                i += 1
                            else:
                                 print(f"Warning: Missing data for match at index {i} in competition {current_competition}. Skipping.")
                        else:
                             print(f"Warning: Found 'team1row' without a following 'team2row' at index {i} in competition {current_competition}. Skipping.")
                    elif active_competitions is not None and i + 1 < len(rows) and rows[i + 1].attrib.get('class') == 'team2row':
                        i += 1


                i += 1


    except Exception as e:
        print(f"An error occurred during fixtures scraping: {e}")
        print("Returning potentially partial or empty fixtures list due to error.")
        return matches_data


    finally:
        if browser:
            await browser.close()


    print(f"Finished scraping. Found {len(matches_data)} fixtures after filtering by database status.")
    return matches_data

# --- Scraping Function: Fetch Match Stats/Results Markdown ---
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
        css_selector=".body-text",
        excluded_tags=["form", "header", "footer", "nav"],
        exclude_external_links=True,
        exclude_social_media_links=True,
        exclude_external_images=True,
    )

    browser_config = BrowserConfig()

    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            result = await crawler.arun(
                url=url,
                config=run_config,
                timeout=60000
            )
        except Exception as e:
             print(f"Error during crawling {url}: {e}")
             return None

        if not result or not result.success:
            print("Crawl failed:", result.error_message if result else "No result object")
            return None
        output_mkdwn = getattr(result.markdown, 'raw_markdown', None)
        if output_mkdwn:
            print("Stats/results fetched and converted to markdown.")
        else:
            print("Stats fetched, but no markdown content was generated.")
        return output_mkdwn