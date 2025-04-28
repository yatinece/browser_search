import asyncio
import random
import os
import argparse
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

# Directory for screenshots
SCREENSHOT_DIR = "stealth_demo_screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

async def run_stealth_demo(query: str, headless: bool = False, proxy: str = None):
    """
    Run a stealthy Google search using Playwright + stealth plugin.
    """
    async with async_playwright() as p:
        # Configure browser launch options
        launch_opts = {
            "headless": headless,
        }
        if proxy:
            # Proxy string: http://user:pass@host:port
            launch_opts["proxy"] = {"server": proxy}

        browser = await p.chromium.launch(**launch_opts)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/112.0.0.0 Safari/537.36" # Consider updating Chrome version if needed
            ),
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
                "DNT": "1", # Do Not Track header
            },
        )
        page = await context.new_page()
        await stealth_async(page)  # Apply stealth to avoid detection

        # Navigate to Google
        print("Navigating to Google...")
        try:
            await page.goto("https://www.google.com/", wait_until="domcontentloaded", timeout=15000) # Increased timeout slightly
            await asyncio.sleep(random.uniform(1.0, 2.0))
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "1_home.png"))
            print("Successfully navigated to Google homepage.")
        except Exception as e:
            print(f"Error navigating to Google: {e}")
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "error_navigation.png"))
            await context.close()
            await browser.close()
            return

        # Accept cookies if present
        print("Checking for cookie consent banner...")
        try:
            # Using get_by_role is generally robust, but Google might change the exact name/role
            btn = page.get_by_role("button", name="Accept all") # Common text, might need adjustment based on region/Google changes
            if await btn.is_visible(timeout=5000): # Increased timeout
                print("Cookie consent banner found. Clicking 'Accept all'.")
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=5000) # Wait briefly after click
                print("Cookie consent accepted.")
            else:
                print("Cookie consent banner not found or not visible within timeout.")
        except Exception as e:
            # It's okay if the button isn't there, might be already accepted or different UI
            print(f"Could not find or click cookie button (might be okay): {e}")
            pass # Continue execution

        # Random mouse movement to mimic user interaction
        await page.mouse.move(random.randint(100, 400), random.randint(100, 400))
        await asyncio.sleep(random.uniform(0.5, 1.5))

        # --- MODIFIED SECTION ---
        # Fill search box and submit
        print(f"Attempting to search for: {query}")
        # Use a more likely current selector for Google's search box
        search_input_selector = 'textarea[name="q"]'
        try:
            # **Explicitly wait for the search input to be visible**
            print(f"Waiting for search input ('{search_input_selector}') to be visible...")
            await page.wait_for_selector(search_input_selector, state='visible', timeout=15000) # Increased timeout
            print("Search input is visible.")

            # Fill the search box
            await page.fill(search_input_selector, query, timeout=10000)
            print("Search input filled.")
            await asyncio.sleep(random.uniform(0.5, 1.0))

            # Press Enter
            await page.keyboard.press("Enter")
            print("Search submitted.")
        except Exception as e:
            print(f"Error finding or filling the search box ('{search_input_selector}'): {e}")
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "error_fill_search.png"))
            await context.close()
            await browser.close()
            return
        # --- END OF MODIFIED SECTION ---

        # Wait for results page to load and results to appear
        print("Waiting for search results...")
        results_selector = 'div#search .g h3' # Selector for result titles within main search area
        try:
            await page.wait_for_selector(results_selector, timeout=20000) # Increased timeout
            await asyncio.sleep(random.uniform(1.0, 2.0)) # Wait a bit for rendering
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "2_results.png"))
            print("Search results page loaded.")
        except Exception as e:
            print(f"Error waiting for search results ('{results_selector}'): {e}")
            # Check for CAPTCHA or unexpected page layout
            await page.screenshot(path=os.path.join(SCREENSHOT_DIR, "error_no_results.png"))
            print("Screenshot taken. Check for CAPTCHAs or unexpected page content.")
            await context.close()
            await browser.close()
            return

        # Extract first 5 results
        print("Extracting search results...")
        items = (await page.query_selector_all('div#search .g'))[:5] # Get result blocks
        results = []
        if not items:
             print("No result items found matching the selector 'div#search .g'.")

        for i, item in enumerate(items):
            title = "N/A"
            url = "#"
            try:
                title_el = await item.query_selector("h3") # Find the title header inside the block
                link_el = await item.query_selector("a") # Find the main link inside the block

                if title_el:
                    title = await title_el.inner_text()
                else:
                     print(f"Warning: Title (h3) not found in result item {i+1}")

                if link_el:
                    url = await link_el.get_attribute("href")
                    if not url:
                         url = "#" # Set default if href is empty
                         print(f"Warning: Link (a) found but 'href' attribute is missing or empty in result item {i+1}")

                else:
                     print(f"Warning: Link (a) not found in result item {i+1}")


                # Only add if we got a title and a valid-looking URL
                if title != "N/A" and url != "#" and url.startswith('http'):
                    results.append({"title": title, "url": url})

                    # Highlight and screenshot (optional)
                    try:
                        await page.evaluate("(el) => el.style.border = '2px solid red'", item)
                        await asyncio.sleep(0.5)
                        await page.screenshot(path=os.path.join(SCREENSHOT_DIR, f"3_result_{i+1}.png"))
                        await page.evaluate("(el) => el.style.border = ''", item) # Remove highlight
                    except Exception as screenshot_err:
                         print(f"Error highlighting/screenshotting result {i+1}: {screenshot_err}")
                else:
                    print(f"Skipping result item {i+1} due to missing title or valid URL (Title: '{title}', URL: '{url}'). Check selectors.")

            except Exception as item_err:
                print(f"Error processing result item {i+1}: {item_err}")
                continue # Move to the next item

        print("\n--- Search Results ---")
        if results:
            for r in results:
                print(f"- {r['title']}")
                print(f"  -> {r['url']}")
        else:
            print("No valid search results extracted.")
        print("----------------------\n")

        print("Closing browser...")
        await context.close()
        await browser.close()
        print("Browser closed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stealth Playwright Google Search Demo")
    parser.add_argument(
        "--query", default="trump ", help="Search query" # Changed default query slightly
    )
    parser.add_argument("--headless", action="store_true", help="Run in headless mode (no browser UI)")
    parser.add_argument(
        "--proxy", help="Proxy server address (e.g., http://user:pass@host:port)"
    )
    args = parser.parse_args()

    print(f"Starting demo with query='{args.query}', headless={args.headless}, proxy={'yes' if args.proxy else 'no'}")
    asyncio.run(run_stealth_demo(query=args.query, headless=args.headless, proxy=args.proxy))
    print("Demo finished.")