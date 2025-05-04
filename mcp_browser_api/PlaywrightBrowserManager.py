import asyncio
import json
import logging
import os
import random
from .schema import SearchRequest , SearchResult , SearchResponse, FetchRequest, FetchResponse
import re
from datetime import datetime
from datetime import date
from typing import List, Dict, Any, Optional
from .DocumentHandler import DocumentHandler
from playwright.async_api import (
    async_playwright, Playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError, BrowserContext
)
# Make sure stealth is installed: pip install playwright-stealth
from playwright_stealth import stealth_async
from dotenv import load_dotenv
import urllib
load_dotenv()  # Automatically looks for .env in current dir
# ========================================================================
# Configuration Constants & Environment Variables
# ========================================================================

# --- Timeouts (in milliseconds) ---
# These can be adjusted here if needed.
DEFAULT_PAGE_TIMEOUT = 30 * 1000      # Default timeout for most page operations
FETCH_PAGE_TIMEOUT = 60 * 1000        # Longer timeout specifically for fetching full page content
NETWORK_IDLE_TIMEOUT = 15 * 1000      # Timeout for waiting for network activity to cease
ELEMENT_VISIBLE_TIMEOUT = 20 * 1000   # Max time to wait for an element to become visible
COOKIE_VISIBLE_TIMEOUT = 7 * 1000     # Time to wait specifically for cookie banners to appear
SEARCH_RESULTS_TIMEOUT = 25 * 10000    # Time to wait for search results container/elements

# --- Browser Configuration (via Environment Variables) ---
# Set these environment variables before running the script
# Example: MCP_BROWSER_HEADLESS=false MCP_BROWSER_TYPE=firefox python main.py

# Headless mode: "true" or "false" (defaults to true/headless)
_headless_env = os.getenv("MCP_BROWSER_HEADLESS", "false").lower()
IS_HEADLESS = _headless_env in ["true", "1", "yes"]

# Browser type: "chromium", "firefox", or "webkit" (defaults to chromium)
BROWSER_TYPE = os.getenv("MCP_BROWSER_TYPE", "chromium").lower()
if BROWSER_TYPE not in ["chromium", "firefox", "webkit"]:
    raise ValueError(f"Invalid MCP_BROWSER_TYPE: '{BROWSER_TYPE}'. Choose 'chromium', 'firefox', or 'webkit'.")

logger = logging.getLogger("PlaywrightBrowserManager")
logger.info(f"Configuration: HEADLESS={IS_HEADLESS}, BROWSER_TYPE={BROWSER_TYPE}")
logger.info(f"Timeouts (ms): DEFAULT={DEFAULT_PAGE_TIMEOUT}, FETCH={FETCH_PAGE_TIMEOUT}, VISIBLE={ELEMENT_VISIBLE_TIMEOUT}")


# --- Debug Screenshot Directory ---
DEBUG_SCREENSHOT_DIR = "logs/debug_screenshots"
os.makedirs(DEBUG_SCREENSHOT_DIR, exist_ok=True)



# ========================================================================
# Playwright Browser Manager Class
# ========================================================================
class PlaywrightBrowserManager:
    def __init__(self):
        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._context_closed = False  # Track context closed state manually

    @staticmethod
    def get_screenshot_path(prefix: str) -> str:
        """Generates a unique screenshot path."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        return os.path.join(DEBUG_SCREENSHOT_DIR, f"{prefix}_{timestamp}.png")
    
    async def initialize(self):
        """Initialize the Playwright browser instance based on configuration."""
        if self._initialized:
            return

        async with self._lock:
            if not self._initialized:
                # --- Get Configuration ---
                executable_path = os.getenv("MCP_BROWSER_EXECUTABLE_PATH")
                log_browser_info = f"executable path: {executable_path}" if executable_path else f"configured type: {BROWSER_TYPE}"
                logger.info(f"Initializing Playwright with {log_browser_info} (headless: {IS_HEADLESS})...")

                try:
                    self.playwright = await async_playwright().start()

                    # --- Browser Launch Logic ---
                    common_launch_options = {"headless": IS_HEADLESS}
                    chromium_args=[]
                    chromium_args = [
                        "--disable-dev-shm-usage", "--no-sandbox", "--disable-setuid-sandbox",
                        "--disable-gpu",
                        # "--disable-web-security", # Use cautiously
                        # "--disable-features=IsolateOrigins,site-per-process" # Can cause issues
                    ]
                    user_agents = [
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.2210.144",
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Version/17.1.2 Safari/605.1.15",
                    ]

                    browser_launched = False # Flag to check if browser launched successfully

                    # --- Try launching with executable_path first ---
                    if executable_path:
                        try:
                            launch_opts_exec = common_launch_options.copy()
                            # Apply chromium args if using a chromium-based executable (like Chrome/Edge)
                            launch_opts_exec["args"] = chromium_args
                            launch_opts_exec["executable_path"] = executable_path

                            logger.info(f"Attempting to launch browser via executable: {executable_path}")
                            # Use playwright.chromium for Chrome/Edge executables
                            self.browser = await self.playwright.chromium.launch(**launch_opts_exec)
                            browser_launched = True
                            logger.info(f"Successfully launched browser from executable path: {executable_path}")
                        except Exception as exec_err:
                            logger.error(f"Failed to launch browser from executable path '{executable_path}': {exec_err}", exc_info=True)
                            logger.warning("Falling back to default browser type configuration based on BROWSER_TYPE.")
                            # Let the code proceed to the fallback logic by keeping browser_launched = False

                    # --- Fallback or default launch logic ---
                    if not browser_launched:
                        logger.info(f"Launching browser based on BROWSER_TYPE: {BROWSER_TYPE}")
                        if BROWSER_TYPE == "firefox":
                            # Ensure chromium-specific args are not passed to firefox
                            common_launch_options.pop("args", None)
                            self.browser = await self.playwright.firefox.launch(**common_launch_options)
                        elif BROWSER_TYPE == "webkit":
                             # Ensure chromium-specific args are not passed to webkit
                            common_launch_options.pop("args", None)
                            self.browser = await self.playwright.webkit.launch(**common_launch_options)
                        else: # Default to chromium
                            launch_opts_chromium = common_launch_options.copy()
                            launch_opts_chromium["args"] = chromium_args # Apply chromium args
                            self.browser = await self.playwright.chromium.launch(**launch_opts_chromium)
                            ###self.browser = await self.playwright.chromium.launch(headless=False)
                        logger.info(f"Successfully launched default browser type: {BROWSER_TYPE}")
                        browser_launched = True # Mark as launched via default method

                    # --- Check if any browser was launched ---
                    if not self.browser or not browser_launched:
                         raise RuntimeError("Failed to launch any browser instance (executable path and default type).")

                    # --- Context Creation ---
                    logger.info("Creating browser context...")

                    self.context = await self.browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent=random.choice(user_agents),
                        java_script_enabled=True, 
                        extra_http_headers={
                            "Accept-Language": "en-US,en;q=0.9",
                            "DNT": "1", # Do Not Track
                        },
                        # default_navigation_timeout=DEFAULT_PAGE_TIMEOUT, # Option to set here
                        # default_timeout=DEFAULT_PAGE_TIMEOUT # Option to set here
                    )
                    self._context_closed = False  # Mark context as open
                    self._initialized = True
                    final_log_info = f"executable {executable_path}" if executable_path and self.browser.browser_type.name == 'chromium' else f"type {self.browser.browser_type.name}" # Use actual launched type
                    logger.info(f"Playwright browser ({final_log_info}) and context initialized successfully.")

                except Exception as e:
                    logger.exception(f"Failed to initialize Playwright browser: {str(e)}")
                    # Attempt cleanup
                    if hasattr(self, 'context') and self.context:
                        try: await self.context.close()
                        except Exception: pass # Ignore cleanup errors
                    if hasattr(self, 'browser') and self.browser:
                        try: await self.browser.close()
                        except Exception: pass # Ignore cleanup errors
                    if hasattr(self, 'playwright') and self.playwright:
                        try: await self.playwright.stop()
                        except Exception: pass # Ignore cleanup errors
                    # Reset state
                    self.playwright = None
                    self.browser = None
                    self.context = None
                    self._initialized = False
                    self._context_closed = True
                    raise # Re-raise the exception after logging and cleanup attempt
    
    async def close(self):
        """Close all Playwright resources."""
        if self._initialized:
            logger.info("Closing Playwright browser...")
            # Use try/except for each close to ensure cleanup continues if one fails
            try:
                if self.context: 
                    await self.context.close()
                    self._context_closed = True
            except Exception as e_ctx: 
                logger.error(f"Error closing context: {e_ctx}")
                self._context_closed = True  # Force closed state on error
                
            try:
                if self.browser and self.browser.is_connected(): 
                    await self.browser.close()
            except Exception as e_brw: 
                logger.error(f"Error closing browser: {e_brw}")
                
            try:
                if self.playwright: 
                    await self.playwright.stop()
            except Exception as e_pw: 
                logger.error(f"Error stopping playwright: {e_pw}")

            self._initialized = False
            self._context_closed = True
            logger.info("Playwright browser resources closed.")

    async def apply_stealth(self, page: Page):
        await page.evaluate("""() => {
            navigator.webdriver = false;
            Object.defineProperty(navigator, 'plugins', {
                get: () => [{}, {}, {}, {}, {}],
            });
        }""")

    async def get_page(self) -> Page:
        """Get a new page from the browser context and apply stealth."""
        # FIX: Check context status without using is_closed()
        if not self._initialized or not self.context or self._context_closed:
            logger.warning("Browser not initialized or context missing/closed. Re-initializing.")
            self._context_closed = False  # Reset the flag
            await self.initialize() # Re-initialize if needed
            if not self.context:
                logger.error("Failed to get context after re-initialization attempt.")
                raise RuntimeError("Browser context is not available.")

        try:
            page = await self.context.new_page()
            logger.debug(f"Created new browser page (ID likely: {page})") # Page object repr might be useful

            # --- Apply Stealth Globally ---
            # This applies stealth patches to every page created by this manager
            try:
                #await stealth_async(page)
                await self.apply_stealth(page)
                logger.debug("Applied playwright-stealth patches globally to the new page.")
            except Exception as stealth_err:
                logger.error(f"Failed to apply stealth patches: {stealth_err}")
                # Decide if you want to raise an error or continue without stealth

            # Set default timeout for operations on this specific page
            page.set_default_timeout(DEFAULT_PAGE_TIMEOUT)
            return page
            
        except Exception as e:
            logger.error(f"Error creating new page: {e}")
            # If we get an error creating a page, the context might be unusable
            self._context_closed = True
            # Try again with a clean context
            await self.initialize()
            # If this also fails, let the exception propagate
            page = await self.context.new_page()
            await self.apply_stealth(page)
            page.set_default_timeout(DEFAULT_PAGE_TIMEOUT)
            return page


    async def Google_Search(self, query: str, max_results: int, time_filter: Optional[str] = None, custom_start_date: Optional[date] = None, custom_end_date: Optional[date] = None) -> List[SearchResult]:
        page = None
        # --- Selectors based on provided snippet (May need testing/adjustment) ---
        search_input_selector = 'textarea[name="q"]'
        # Main container usually holding organic results
        results_container_selector = "#search"
        # Selector for one individual search result block (derived from snippet)
        result_item_selector = "div.N54PNb.BToiNc"
        # Selector for the link element containing the title and URL within a result item
        link_block_selector = "div.yuRUbf" # Contains the 'a' tag
        link_selector = f"{link_block_selector} a" # The 'a' tag itself
        # Selector for the title text (h3) within the link element
        title_selector = "h3.LC20lb"
        # Selector for the description text block within a result item
        snippet_selector = "div.VwiC3b"
        # Fallback result selector if the primary one fails (e.g., original 'div.g')
        fallback_result_item_selector = "div.g" # Keep the old reliable 'g' class as a fallback
        # --------------------------------------------------------------------------

        logger.info(f"Performing Google search for: '{query}' (max_results: {max_results})")

        try:
            page = await self.get_page() # Stealth applied automatically

            logger.debug("Navigating to https://www.google.com/")
            await page.goto("https://www.google.com/", wait_until="domcontentloaded")
            await asyncio.sleep(random.uniform(0.5, 1.5)) # Short delay after nav

            # --- Cookie Consent Handling ---
            try:
                accept_button = page.get_by_role("button", name="Accept all")
                if await accept_button.is_visible(timeout=COOKIE_VISIBLE_TIMEOUT):
                    logger.info("Cookie consent banner found. Clicking 'Accept all'.")
                    await accept_button.click()
                    await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
                    logger.debug("Cookie consent accepted.")
                else:
                    logger.debug("Cookie consent banner not found or not visible within timeout.")
            except Exception as cookie_err:
                logger.warning(f"Could not find or click cookie button (might be okay): {cookie_err}")
                # Avoid taking screenshot here unless absolutely necessary for debugging cookies

            await page.mouse.move(random.randint(100, 500), random.randint(100, 500)) # Human-like interaction
            await asyncio.sleep(random.uniform(0.2, 0.8))

            # --- Perform Search ---
            try:
                logger.debug(f"Waiting for search input ('{search_input_selector}') to be visible...")
                await page.wait_for_selector(search_input_selector, state='visible', timeout=ELEMENT_VISIBLE_TIMEOUT)
                logger.debug("Search input is visible. Filling query.")
                await page.fill(search_input_selector, query)
                await asyncio.sleep(random.uniform(0.3, 0.7))
                logger.debug("Submitting search query.")
                await page.press(search_input_selector, 'Enter')
            except Exception as search_fill_err:
                logger.error(f"Error finding or filling the search box ('{search_input_selector}'): {search_fill_err}")
                await page.screenshot(path=self.get_screenshot_path("Google Search_fill_error"))
                raise # Re-raise the error to stop execution here

            # Wait for initial search results to load
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(random.uniform(0.5, 1.5))

            # Get the current URL after the search
            current_url = page.url
            logger.debug(f"Current URL after search: {current_url}")
            
            # Now add time filter parameter if needed
            if time_filter:
                logger.info(f"Applying time filter: {time_filter}")
                filter_param = self.get_time_filter_param("google", time_filter, custom_start_date, custom_end_date)
                
                # Parse the current URL and add the time filter
                parsed_url = urllib.parse.urlparse(current_url)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                
                # Create a new query string with the added time parameter
                for key, value in urllib.parse.parse_qs(filter_param.lstrip('&')).items():
                    query_params[key] = value
                
                new_query = urllib.parse.urlencode(query_params, doseq=True)
                new_url = urllib.parse.urlunparse((
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    new_query,
                    parsed_url.fragment
                ))
                
                logger.debug(f"Navigating to URL with time filter: {new_url}")
                await page.goto(new_url, wait_until="domcontentloaded")
                await asyncio.sleep(random.uniform(0.5, 1.5))  # Short delay after navigation

            # --- Wait for Results & Extract ---
            logger.debug(f"Waiting for search results container ('{results_container_selector}')")
            await page.wait_for_selector(results_container_selector, timeout=SEARCH_RESULTS_TIMEOUT)
            # Wait slightly longer for results to potentially render after container appears
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(random.uniform(1.5, 3.0)) # Increased sleep slightly

            await page.screenshot(path=self.get_screenshot_path("Google Search_results"))
            logger.debug("Search results page loaded. Extracting results...")

            results: List[SearchResult] = []
            logger.debug(f"Querying for result items using primary selector: '{result_item_selector}'")
            result_elements = await page.query_selector_all(result_item_selector)

            # --- Fallback Selector Logic ---
            if not result_elements:
                logger.warning(f"Primary result selector ('{result_item_selector}') found 0 elements. Trying fallback ('{fallback_result_item_selector}')...")
                result_elements = await page.query_selector_all(fallback_result_item_selector)
                if result_elements:
                    logger.info(f"Fallback selector ('{fallback_result_item_selector}') found {len(result_elements)} elements.")
                    # Adjust snippet selector if using fallback 'g' - requires re-inspection for 'g' elements
                    # For now, we'll try the same snippet selector, but it might be wrong for 'g' elements.
                    # A more robust solution would check which selector succeeded and use appropriate sub-selectors.
                else:
                    logger.error(f"Both primary and fallback selectors failed to find result elements. Check Google's current HTML structure.")
                    # Optional: Log page content if results aren't found
                    # page_content = await page.content()
                    # logger.debug(f"Page HTML when no results found:\n{page_content[:1000]}...") # Log first 1k chars

            logger.info(f"Found {len(result_elements)} potential search result elements using final selector.")
            count = 0
            for i, element in enumerate(result_elements):
                if count >= max_results:
                    logger.info(f"Reached max_results ({max_results}). Stopping extraction.")
                    break
                try:
                    # Find link and title within the result element
                    link_element = await element.query_selector(link_selector)
                    title_element = await element.query_selector(title_selector) # Title is often inside link, but selector targets h3 directly

                    # Get URL from link element
                    url = await link_element.get_attribute("href") if link_element else None
                    # Get Title text
                    title = await title_element.inner_text() if title_element else None

                    # Basic validation
                    if not title or not url or not url.startswith("http"):
                        # Try finding title directly within the element if not in link (less common structure)
                        if not title:
                            h3_direct = await element.query_selector(title_selector)
                            if h3_direct: title = await h3_direct.inner_text()
                        if not url:
                            a_direct = await element.query_selector("a") # Simplest 'a' tag fallback
                            if a_direct: url = await a_direct.get_attribute("href")

                        # If still invalid, skip
                        if not title or not url or not url.startswith("http"):
                            logger.debug(f"Skipping result {i+1}: Invalid/missing title/URL. Title: '{title}', URL: '{url}'")
                            continue

                    # Find and clean snippet text
                    snippet_element = await element.query_selector(snippet_selector)
                    snippet = "No description available"
                    if snippet_element:
                        raw_snippet = await snippet_element.inner_text()
                        snippet = ' '.join(raw_snippet.split()).strip() # Clean whitespace
                    # Fallback snippet attempt if primary fails (e.g., for 'div.g' structure)
                    elif not snippet_element:
                        snippet_fallback_element = await element.query_selector("div[data-content-feature='1']") # Example old selector
                        if snippet_fallback_element:
                            raw_snippet = await snippet_fallback_element.inner_text()
                            snippet = ' '.join(raw_snippet.split()).strip()


                    results.append(SearchResult(
                        title=title.strip(),
                        url=url,
                        snippet=snippet, # Already stripped
                        source_type="web_search_result",
                        metadata={"search_engine": "google", "position": count + 1, "query": query, "raw_element_index": i + 1}
                    ))
                    count += 1
                    logger.debug(f"Extracted Google result {count}: {title.strip()} -> {url}")

                except Exception as parse_err:
                    logger.warning(f"Error parsing Google search result element index {i}: {parse_err}", exc_info=False) # Set exc_info=True for traceback

            logger.info(f"Successfully extracted {len(results)} valid Google search results.")
            return results

        except PlaywrightTimeoutError as timeout_err:
            logger.error(f"Timeout error during Google search for '{query}': {timeout_err}")
            if page: await page.screenshot(path=self.get_screenshot_path("Google Search_timeout_error"))
            return []
        except Exception as e:
            logger.exception(f"An unexpected error occurred during Google search for '{query}': {e}")
            if page: await page.screenshot(path=self.get_screenshot_path("Google Search_unexpected_error"))
            return []
        finally:
            if page:
                try:
                    await page.close()
                except Exception as page_close_err:
                    logger.warning(f"Error closing page: {page_close_err}")

    async def bing_search(self, query: str, max_results: int, time_filter: Optional[str] = None, custom_start_date: Optional[date] = None, custom_end_date: Optional[date] = None) -> List[SearchResult]:

        page = None
        logger.info(f"Performing Bing search for: '{query}' (max_results: {max_results})")
        try:
            page = await self.get_page() # Stealth applied automatically
            # page.set_default_timeout() already called

            encoded_query = query.replace(' ', '+')
            # Add time filter parameter to URL
            filter_param = self.get_time_filter_param("bing", time_filter, custom_start_date, custom_end_date)
            search_url = f"https://www.bing.com/search?q={encoded_query}{filter_param}"
            
            logger.debug(f"Navigating to Bing search URL: {search_url}")
            await page.goto(search_url, wait_until="domcontentloaded")

            try:
                 accept_button = page.get_by_role("button", name="Accept", exact=True).or_(page.locator("#bnp_btn_accept"))
                 if await accept_button.is_visible(timeout=COOKIE_VISIBLE_TIMEOUT): # Use constant
                     logger.info("Bing cookie consent found. Clicking 'Accept'.")
                     await accept_button.click()
                     await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT) # Use constant
            except Exception:
                 logger.debug("Bing cookie consent not found or error clicking.")

            await page.wait_for_selector("#b_results", timeout=SEARCH_RESULTS_TIMEOUT) # Use constant
            await asyncio.sleep(random.uniform(1.0, 2.5))

            await page.screenshot(path=self.get_screenshot_path("bing_search_results"))

            results = []
            result_elements = await page.query_selector_all("#b_results > li.b_algo")
            logger.info(f"Found {len(result_elements)} raw Bing search result elements.")

            for i, element in enumerate(result_elements):
                if len(results) >= max_results: break
                try:
                    title_element = await element.query_selector("h2 a")
                    title = await title_element.inner_text() if title_element else None
                    url = await title_element.get_attribute("href") if title_element else None
                    if not title or not url or not url.startswith("http"): continue

                    snippet_element = await element.query_selector(".b_caption p")
                    snippet = await snippet_element.inner_text() if snippet_element else "No description available"

                    results.append(SearchResult(
                        title=title.strip(), url=url, snippet=snippet.strip(), source_type="web_search_result",
                        metadata={"search_engine": "bing", "position": len(results) + 1, "query": query}
                    ))
                    logger.debug(f"Extracted Bing result {len(results)}: {title.strip()}")
                except Exception as e:
                    logger.warning(f"Error parsing Bing search result {i}: {str(e)}")

            logger.info(f"Successfully extracted {len(results)} Bing search results.")
            return results
        except Exception as e:
            logger.exception(f"Bing search error for '{query}': {str(e)}")
            if page: await page.screenshot(path=self.get_screenshot_path("bing_search_error"))
            return []
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")

    async def brave_search(self, query: str, max_results: int, time_filter: Optional[str] = None, custom_start_date: Optional[date] = None, custom_end_date: Optional[date] = None) -> List[SearchResult]:
  
        page = None
        # --- Updated Selectors ---
        # ASSUMPTION: Verify this selector holds all the result snippets using Inspect Element
        results_container_selector = "#results" 
        # Selector for one individual web search result block
        result_item_selector = "div.snippet[data-type='web']"
        # Selector for the main link within a result item
        link_selector = "a.heading-serpresult"
        # Selector for the title text within the link element
        title_selector = "div.title"
        # Selector for the description text within a result item
        snippet_selector = "div.snippet-description"
        # -------------------------

        logger.info(f"Performing Brave search for: '{query}' (max_results: {max_results})")
        try:
            page = await self.get_page() # Stealth applied automatically

            encoded_query = query.replace(' ', '+')
            # Add time filter parameter to URL
            filter_param = self.get_time_filter_param("brave", time_filter, custom_start_date, custom_end_date)
            search_url = f"https://search.brave.com/search?q={encoded_query}{filter_param}"
            
            logger.debug(f"Navigating to Brave search URL: {search_url}")
            await page.goto(search_url, wait_until="domcontentloaded")

            results = []
            
            # Try to extract LLM snippet
            llm_snippet_element = await page.query_selector("#llm-snippet")
            if llm_snippet_element:
                logger.info("LLM snippet found. Attempting to expand and extract...");
                more_button_selector = "#llm-show-more-button"
                answer_content_selector = "#chatllm-main-answer-content"

                try:
                    more_button = await llm_snippet_element.query_selector(more_button_selector)
                    if more_button:
                        try:
                            await asyncio.sleep(0.5)  # Small initial delay
                            await more_button.wait_for_element_state('visible', timeout=5000)
                            await more_button.click(timeout=5000)
                            logger.info("Clicked 'More' button on LLM snippet.")
                        except PlaywrightTimeoutError:
                            logger.warning("Timeout waiting for 'More' button to become visible or clicking it.")
                        except Exception as e:
                            logger.warning(f"Error interacting with 'More' button: {e}")
                    await asyncio.sleep(random.uniform(2.0, 5.5))
                    llm_title = "AI Generated Answer"  # Default title
                    llm_title_container = await llm_snippet_element.query_selector("#chatllm-title")
                    if llm_title_container:
                        title_div = await llm_title_container.query_selector("div")
                        if title_div:
                            llm_title = await title_div.inner_text()
                        else:
                            llm_title = await llm_title_container.inner_text()
                    else:
                        logger.warning("Could not find the title container (#chatllm-title) within the LLM snippet.")

                    llm_answer = "No answer provided."
                    llm_answer_element = await llm_snippet_element.query_selector(answer_content_selector)
                    if llm_answer_element:
                        try:
                            llm_answer = await page.evaluate(f'document.querySelector("{answer_content_selector}").textContent')
                            llm_answer = ' '.join(llm_answer.split()).strip()
                            logger.debug(f"Extracted LLM answer using JavaScript: '{llm_answer}'")
                        except Exception as e:
                            logger.warning(f"Error evaluating JavaScript to get LLM answer: {e}")

                    results.append(SearchResult(
                        title=llm_title.strip(),
                        url="ai://ai-generated-answer",
                        snippet=llm_answer,
                        source_type="llm_answer",
                        metadata={"search_engine": "brave", "query": query}
                    ))
                    logger.info("Successfully extracted LLM snippet.")

                except PlaywrightTimeoutError:
                    logger.warning("Timeout waiting for LLM elements or interacting with 'More' button.")
                except Exception as e:
                    logger.warning(f"Error interacting with LLM snippet: {e}")

            logger.debug(f"Waiting for results container: '{results_container_selector}'")
            try:
                # Wait for the container that holds all results
                await page.wait_for_selector(results_container_selector, timeout=SEARCH_RESULTS_TIMEOUT)
                logger.debug(f"Results container '{results_container_selector}' found.")
            except PlaywrightTimeoutError:
                logger.error(f"Timeout waiting for Brave results container ('{results_container_selector}'). Page structure might have changed or search failed.")
                await page.screenshot(path=self.get_screenshot_path("brave_results_container_timeout"))
                return results  # Return any LLM result found, even if regular results couldn't be loaded

            # Optional: Wait a bit longer for JS rendering if needed
            await asyncio.sleep(random.uniform(1.0, 2.5))

            await page.screenshot(path=self.get_screenshot_path("brave_search_results"))

            logger.debug(f"Querying for result items using selector: '{result_item_selector}'")
            # Get all individual result elements based on the new selector
            result_elements = await page.query_selector_all(result_item_selector)

            logger.info(f"Found {len(result_elements)} raw Brave search result elements matching '{result_item_selector}'.")

            count = 0
            for i, element in enumerate(result_elements):
                if count >= max_results:
                    logger.info(f"Reached max_results ({max_results}). Stopping extraction.")
                    break
                try:
                    # Find the main link element within the current result item
                    link_element = await element.query_selector(link_selector)
                    if not link_element:
                        logger.debug(f"Skipping result {i+1}: Link element ('{link_selector}') not found.")
                        continue

                    # Extract URL from the link element's href attribute
                    url = await link_element.get_attribute("href")

                    # Find the title element within the link element
                    title_element = await link_element.query_selector(title_selector)
                    title = await title_element.inner_text() if title_element else None

                    # Basic validation for title and URL
                    if not title or not url or not url.startswith("http"):
                        logger.debug(f"Skipping result {i+1}: Missing title/URL or invalid URL ({url}). Title: '{title}'")
                        continue
                    # Skip if it's an internal Brave search link (unlikely with data-type='web' but good check)
                    if "brave.com/search" in url:
                        logger.debug(f"Skipping result {i+1}: Internal Brave link ({url}).")
                        continue

                    # Find the snippet element within the current result item
                    snippet_element = await element.query_selector(snippet_selector)
                    # Clean up snippet text, provide default if not found
                    snippet = "No description available"
                    if snippet_element:
                        raw_snippet = await snippet_element.inner_text()
                        snippet = ' '.join(raw_snippet.split()).strip() # Clean whitespace

                    results.append(SearchResult(
                        title=title.strip(),
                        url=url,
                        snippet=snippet, # Already stripped
                        source_type="web_search_result",
                        metadata={"search_engine": "brave", "position": count + 1, "query": query, "raw_element_index": i + 1}
                    ))
                    count += 1
                    logger.debug(f"Extracted Brave result {count}: {title.strip()} -> {url}")

                except Exception as e:
                    logger.warning(f"Error parsing Brave search result element index {i}: {str(e)}", exc_info=False) # Set exc_info=True for full traceback during deep debug

            logger.info(f"Successfully extracted {len(results)} valid Brave search results.")
            return results
                
        except PlaywrightTimeoutError as timeout_err:
            logger.error(f"Timeout error during Brave search for '{query}': {timeout_err}")
            if page: await page.screenshot(path=self.get_screenshot_path("brave_search_timeout_error"))
            return results if 'results' in locals() else []  # Return any results found so far
        except Exception as e:
            logger.exception(f"An unexpected error occurred during Brave search for '{query}': {e}")
            if page: await page.screenshot(path=self.get_screenshot_path("brave_search_unexpected_error"))
            return results if 'results' in locals() else []
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")



    async def fetch_content(self, url: str) -> Dict[str, Any]:
        page = None
        logger.info(f"Fetching content from URL: {url}")

                # Handle documents with specific extensions using the DocumentHandler

        #file_extension = url.split(".")[-1].lower()
        document_extensions = ['pdf', 'docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls']
        ext = url.strip("/").split("/")[-1].split(".")[-1].lower()
        file_extension = ext if ext in document_extensions else None
        document_extensions = ['pdf', 'docx', 'doc', 'pptx', 'ppt', 'xlsx', 'xls']
        
        if file_extension in document_extensions:
            logger.info(f"Detected document URL with extension '{file_extension}'. Using DocumentHandler.")
            try:
                document_handler = DocumentHandler()
                return await document_handler.extract_content(url)
            except Exception as e:
                logger.exception(f"DocumentHandler failed to extract content from {url}: {e}")
                return {
                    "content": f"Document handling error: {str(e)}",
                    "title": "Document Extraction Error",
                    "metadata": {"error": True, "reason": str(e), "url": url}
                }
        try:
            page = await self.get_page() # Stealth applied automatically
            # Use the longer fetch timeout for this specific page
            page.set_default_timeout(FETCH_PAGE_TIMEOUT) # Override default for fetch

            response = await page.goto(url, wait_until="domcontentloaded")

            if not response:
                 logger.error(f"Failed to get response object for URL: {url}")
                 raise ConnectionError(f"Could not get response from {url}")
            elif response.status >= 400:
                 logger.error(f"Failed to load page {url}: HTTP {response.status}")
                 await page.screenshot(path=self.get_screenshot_path(f"fetch_http_error_{response.status}"))
                 return {
                     "content": f"Failed to load page. HTTP status: {response.status}", "title": f"Error {response.status}",
                     "metadata": {"error": True, "status": response.status, "url": url}
                 }

            try:
                # Use network idle constant, but don't fail hard if it times out
                await page.wait_for_load_state("networkidle", timeout=NETWORK_IDLE_TIMEOUT)
            except PlaywrightTimeoutError:
                 logger.warning(f"Network idle timeout for {url}. Content might be incomplete.")

            title = await page.title()
            metadata = {
                "url": url, "fetch_time": datetime.now().isoformat(), "final_url": page.url,
                "http_status": response.status, "content_type": response.headers.get("content-type", "unknown"),
            }

            # --- Content Extraction Logic (using simplified approach for brevity) ---
            content = ""
            content_selectors = ["article", "main", "[role='main']", ".entry-content", ".post-content", ".article-content", "#content", ".content"]
            logger.debug(f"Attempting content extraction using selectors for {url}")
            best_content = ""
            for selector in content_selectors:
                 try:
                     element = await page.query_selector(selector) # Try finding the first best match
                     if element and await element.is_visible():
                          element_text = await element.inner_text()
                          if len(element_text) > len(best_content):
                               best_content = element_text
                               logger.debug(f"Found candidate content ({len(best_content)} chars) with selector: {selector}")
                 except Exception: pass # Ignore errors on individual selectors

            if len(best_content) > 200: # Threshold for using selected content
                 content = best_content
            else: # Fallback to body if specific selectors failed or content too short
                 logger.warning(f"Specific content selectors yielded short/no content for {url}. Falling back to body.")
                 try:
                      body = await page.query_selector("body")
                      if body: content = await body.inner_text()
                 except Exception as body_err:
                      logger.error(f"Failed to get body content: {body_err}")
                      content = "Failed to extract content from the page."

            # --- Clean up content ---
            if content:
                content = re.sub(r'\s+', ' ', content).strip()
                content = re.sub(r'(\n\s*){3,}', '\n\n', content)

            logger.info(f"Successfully fetched content ({len(content)} chars) for URL: {url}")
            await page.screenshot(path=self.get_screenshot_path("fetch_content_success"))

            return {"content": content, "title": title.strip() if title else "No Title Found", "metadata": metadata}

        except PlaywrightTimeoutError:
            logger.warning(f"Timeout while fetching content from {url}")
            if page: await page.screenshot(path=self.get_screenshot_path("fetch_content_timeout"))
            return {"content": "Content fetch timed out", "title": "Timeout Error", "metadata": {"error": True, "reason": "timeout", "url": url}}
        except Exception as e:
            logger.exception(f"Error fetching content from {url}: {e}")
            if page: await page.screenshot(path=self.get_screenshot_path("fetch_content_error"))
            return {"content": f"Error fetching content: {str(e)}", "title": "Fetch Error", "metadata": {"error": True, "reason": str(e), "url": url}}
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")

    def get_time_filter_param(self, engine: str, time_filter: Optional[str], 
                            start_date: Optional[date], end_date: Optional[date]) -> str:
        """Generate time filter query parameter based on the search engine and filter settings.
        
        Args:
            engine: The search engine to use ('brave', 'bing', or 'google')
            time_filter: Time filter option ('past_hour', 'past_day', 'past_week', 'past_month', 'past_year', 'custom')
            start_date: Start date for custom date range
            end_date: End date for custom date range
            
        Returns:
            String containing the appropriate query parameter for the specified search engine and time filter
        """
        logger.debug(f"Time filter for search: '{time_filter}'")
        logger.debug(f"Start date for search: '{start_date}'")
        logger.debug(f"End date for search: '{end_date}'")
        
        # Handle custom date range consistently
        if time_filter == "custom":
            if not (start_date and end_date):
                logger.warning("Custom time filter specified but missing start_date or end_date")
                return ""
            
            if engine == "brave":
                param = f"&tf={start_date.isoformat()}to{end_date.isoformat()}"
            elif engine == "bing":
                param = f'&filters=ex1%3a"ez5_{self.bing_date_index(start_date)}_{self.bing_date_index(end_date)}"'
            elif engine == "google":
                start = start_date.strftime("%m/%d/%Y")
                end = end_date.strftime("%m/%d/%Y")
                param = f"&tbs=cdr:1,cd_min:{start},cd_max:{end}"
            else:
                logger.warning(f"Unsupported search engine: {engine}")
                return ""
                
            logger.debug(f"Return for custom date search: {param}")
            return param
        
        # Handle predefined time filters
        if engine == "brave":
            mapping = {
                "past_day": "&tf=pd",
                "past_week": "&tf=pw",
                "past_month": "&tf=pm",
                "past_year": "&tf=py",
            }
        elif engine == "bing":
            mapping = {
                "past_day": '&filters=ex1%3a"ez1"',
                "past_week": '&filters=ex1%3a"ez2"',
                "past_month": '&filters=ex1%3a"ez3"',
                "past_year": '&filters=ex1%3a"ez4"',
            }
        elif engine == "google":
            mapping = {
                "past_hour": "&tbs=qdr:h",
                "past_day": "&tbs=qdr:d",
                "past_week": "&tbs=qdr:w",
                "past_month": "&tbs=qdr:m",
                "past_year": "&tbs=qdr:y",
            }
        else:
            logger.warning(f"Unsupported search engine: {engine}")
            return ""
        
        param = mapping.get(time_filter, "")
        logger.debug(f"Return for search: {param}")
        return param
    
    def bing_date_index(self,d: date) -> int:
        return (d - date(1960, 1, 1)).days