# backend/scraper.py

# This module contains functions for scraping match data.

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


# --- Scraping Function: Fetch Fixture List ---
# Updated to accept fixture_url and competitions_collection as parameters
async def fetch_matches_fixtures(fixture_url: str, competitions_collection: Collection):
    """
    Scrapes match fixtures from a URL for specified competitions,
    filtering by competition status in the database.
    """
    print(f"Fetching match fixtures from {fixture_url}...")
    matches_data = []
    active_competitions = []

    # --- Step 1: Get list of active competitions from the database ---
    if competitions_collection is None:
        print("Error: Competitions collection not initialized. Cannot filter fixtures.")
        # Proceeding without filtering if collection is not available
        # Or you might choose to return [] here
        pass
    else:
        try:
            # Find all competition documents where status is True
            print("Querying database for active competitions...")
            # Use asyncio.to_thread as find() is synchronous
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
            print("Proceeding with fixture scraping without database filtering.")
            # Clear active_competitions list so no filtering happens
            active_competitions = None # Use None to indicate no filtering could be done
        except Exception as e:
             print(f"An unexpected error occurred while fetching active competitions: {e}")
             print("Proceeding with fixture scraping without database filtering.")
             active_competitions = None # Use None to indicate no filtering could be done


    # Return empty list if no active competitions were found and no DB error occurred
    if active_competitions is not None and not active_competitions:
         return []


    # --- Step 2: Scrape fixtures from the URL ---
    print(f"Scraping fixtures from URL: {fixture_url}")
    async with async_playwright() as p:
        # Use a default headless mode for browser
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
             await page.goto(fixture_url, timeout=60000) # Add timeout
             page_html = await page.content()
        except Exception as e:
             print(f"Error navigating to or getting content from {fixture_url}: {e}")
             await browser.close()
             return []


        await browser.close()

        tree = etree.HTML(page_html)
        rows = tree.xpath('//table//tr')

        current_competition = None
        # Assume fixture date is tomorrow unless explicitly stated otherwise on the page
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        current_date = tomorrow_date # Default date

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
                # Check if filtering is active and if the current competition is in the active list
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
                                "date": current_date, # Using default tomorrow_date for now
                                "time": time_str,
                                "home_team": home_team,
                                "away_team": away_team,
                                "stats_link": stats_link
                            }
                            matches_data.append(match_data)
                            i += 1 # Skip the next row as it's the team2row we just processed
                        else:
                             print(f"Warning: Missing data for match at index {i}. Skipping.")
                    else:
                         print(f"Warning: Found 'team1row' without a following 'team2row' at index {i}. Skipping.")
                elif i + 1 < len(rows) and rows[i + 1].attrib.get('class') == 'team2row':
                    # If filtering is active and competition is NOT active, skip the next row as well
                    i += 1


            i += 1

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
            result = await crawler.arun(
                url=url,
                config=run_config
            )
        except Exception as e:
             print(f"Error during crawling {url}: {e}")
             return None

        if not result.success:
            print("Crawl failed:", result.error_message)
            return None
        output_mkdwn = getattr(result.markdown, 'raw_markdown', None)
        if output_mkdwn:
            print("Stats/results fetched and converted to markdown.")
        else:
            print("Stats/results fetched, but no markdown content was generated.")
        return output_mkdwn