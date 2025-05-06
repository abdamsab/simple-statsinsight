# test_post_markdown.py

# This script is a temporary tool to test scraping specific post-match
# results markdown from a known URL by experimenting with CSS selectors
# using Crawl4AI's arun() method.

import asyncio
# We need the necessary imports from crawl4ai
from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, BrowserConfig
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

async def fetch_test_markdown_with_crawl4ai(url: str, selector: str):
    """
    Fetches markdown from a URL using Crawl4AI's arun() method
    with a specified CSS selector.
    """
    print(f"Attempting to fetch markdown from {url} using selector: '{selector}'")

    # Configure Crawl4AI's markdown generator and content filter
    prune_filter = PruningContentFilter(
        threshold=0.5,
        threshold_type="fixed",
        min_word_threshold=1
    )

    md_generator = DefaultMarkdownGenerator(
        content_filter=prune_filter,
        options={
            "ignore_links": True, # Set to False to potentially keep the result link formatting
            "ignore_images": True
        }
    )

    # Configure the crawler run, specifying the CSS selector to use
    run_config = CrawlerRunConfig(
        markdown_generator=md_generator,
        css_selector=selector, # <-- The selector we will experiment with
        excluded_tags=["form", "header", "footer", "nav"], # Keep exclusions from original scraper
        exclude_external_links=True,
        exclude_social_media_links=True,
        exclude_external_images=True,
    )

    browser_config = BrowserConfig()

    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            # Run the crawler on the specified URL with the given selector
            result = await crawler.arun(
                url=url,
                config=run_config,
                timeout=60000 # Use a reasonable timeout
            )
        except Exception as e:
             print(f"Error during crawling {url} with selector '{selector}': {e}")
             return f"Error during crawl: {e}"

        if not result or not result.success:
            print(f"Crawl failed for selector '{selector}':", result.error_message if result else "No result object")
            return f"Crawl failed: {result.error_message if result else 'Unknown error'}"

        # Access the generated markdown from the result object
        output_mkdwn = getattr(result.markdown, 'raw_markdown', None)

        if output_mkdwn:
            print(f"Markdown generated successfully for selector '{selector}'.")
        else:
            print(f"Crawl succeeded for selector '{selector}', but no markdown content was generated.")

        return output_mkdwn if output_mkdwn else "No markdown generated."


# --- Main execution block for the test script ---
async def main():
    test_url = "https://www.soccerstats.com/pmatch.asp?league=england&stats=343-15-1-2025"

    # --- Experimentation Area: Change this CSS selector ---
    # Start with a broad selector like ".body-text" or "body" or even "html"
    # Then try more specific selectors based on the HTML structure you inspected.
    # Examples:
    # "div#content" # Get the content div
    # "div#content table" # Get all tables within the content div
    # "div#content table[cellspacing='0'][cellpadding='10']" # Try to target the specific table by attributes
    # You can also use more complex selectors if needed.
    selector_to_test = "td[valign='top'][align='center'][style='padding-left:10px;']" # <-- Start here and change this string

    extracted_markdown = await fetch_test_markdown_with_crawl4ai(test_url, selector_to_test)

    print("\n--- Test Script Result (Extracted Markdown) ---")
    print("Markdown_length: ", len(extracted_markdown))
    print(extracted_markdown)
    print("---------------------------------------------")

if __name__ == "__main__":
    asyncio.run(main())