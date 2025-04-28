import asyncio
import json
import logging
import os
import random
import time
import re
from datetime import datetime
from typing import List, Dict, Any, Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, HttpUrl
from playwright.async_api import (
    async_playwright, Playwright, Browser, Page, TimeoutError as PlaywrightTimeoutError, BrowserContext
)
# Make sure stealth is installed: pip install playwright-stealth
from playwright_stealth import stealth_async

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
SEARCH_RESULTS_TIMEOUT = 25 * 1000    # Time to wait for search results container/elements

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

# --- Logging Setup ---
os.makedirs("logs", exist_ok=True)
log_filename = f"logs/mcp_browser_api_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("mcp_browser_api")
logger.info(f"Configuration: HEADLESS={IS_HEADLESS}, BROWSER_TYPE={BROWSER_TYPE}")
logger.info(f"Timeouts (ms): DEFAULT={DEFAULT_PAGE_TIMEOUT}, FETCH={FETCH_PAGE_TIMEOUT}, VISIBLE={ELEMENT_VISIBLE_TIMEOUT}")


# --- FastAPI App ---
app = FastAPI(
    title="MCP Browser API",
    description="API using Playwright for stealthy web scraping tasks like search and content fetching.",
    version="1.2.0" # Updated version
)

# --- Pydantic Models (no changes needed from previous version) ---
class SearchRequest(BaseModel):
    query: str
    max_results: int = 10
    source_types: Optional[List[str]] = ["article", "blog"]
    search_engine: str = "bing"

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    content: str = ""
    source_type: str
    metadata: Dict[str, Any]

class SearchResponse(BaseModel):
    results: List[SearchResult]
    query: str
    search_engine: str
    timestamp: str

class FetchRequest(BaseModel):
    url: HttpUrl

class FetchResponse(BaseModel):
    url: str
    content: str
    title: str
    metadata: Dict[str, Any]
    timestamp: str

# --- Debug Screenshot Directory ---
DEBUG_SCREENSHOT_DIR = "logs/debug_screenshots"
os.makedirs(DEBUG_SCREENSHOT_DIR, exist_ok=True)

def get_screenshot_path(prefix: str) -> str:
    """Generates a unique screenshot path."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    return os.path.join(DEBUG_SCREENSHOT_DIR, f"{prefix}_{timestamp}.png")

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

    async def initialize(self):
        """Initialize the Playwright browser instance based on configuration."""
        if self._initialized:
            return

        async with self._lock:
            if not self._initialized:
                logger.info(f"Initializing Playwright with {BROWSER_TYPE} (headless: {IS_HEADLESS})...")
                try:
                    self.playwright = await async_playwright().start()

                    # --- Browser Launch Logic ---
                    common_launch_options = {"headless": IS_HEADLESS}
                    chromium_args = [
                        "--disable-dev-shm-usage", "--no-sandbox", "--disable-setuid-sandbox",
                        "--disable-gpu",
                        # "--disable-web-security", # Use cautiously
                        # "--disable-features=IsolateOrigins,site-per-process" # Can cause issues
                    ]

                    if BROWSER_TYPE == "firefox":
                        # Note: Firefox might have different arg requirements or incompatibilities
                        self.browser = await self.playwright.firefox.launch(**common_launch_options)
                    elif BROWSER_TYPE == "webkit":
                        # Note: WebKit might have different arg requirements or incompatibilities
                        self.browser = await self.playwright.webkit.launch(**common_launch_options)
                    else: # Default to chromium
                        # Only pass chromium-specific args for chromium
                        common_launch_options["args"] = chromium_args
                        self.browser = await self.playwright.chromium.launch(**common_launch_options)

                    # --- Context Creation ---
                    self.context = await self.browser.new_context(
                        viewport={"width": 1920, "height": 1080},
                        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
                        java_script_enabled=True,
                        extra_http_headers={
                            "Accept-Language": "en-US,en;q=0.9",
                            "DNT": "1",
                        },
                        # Set default navigation timeout for the context
                        # default_navigation_timeout=DEFAULT_PAGE_TIMEOUT, # Option to set here
                        # default_timeout=DEFAULT_PAGE_TIMEOUT # Option to set here
                    )
                    self._context_closed = False  # Set initial state
                    self._initialized = True
                    logger.info(f"Playwright browser ({BROWSER_TYPE}) initialized successfully.")
                except Exception as e:
                    logger.exception(f"Failed to initialize Playwright browser: {str(e)}")
                    raise

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
                await stealth_async(page)
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
            await stealth_async(page)
            page.set_default_timeout(DEFAULT_PAGE_TIMEOUT)
            return page

    # ========================================================================
    # Search & Fetch Methods (Updated to remove Google search and fix Brave search)
    # ========================================================================

    async def bing_search(self, query: str, max_results: int) -> List[SearchResult]:
        page = None
        logger.info(f"Performing Bing search for: '{query}' (max_results: {max_results})")
        try:
            page = await self.get_page() # Stealth applied automatically
            # page.set_default_timeout() already called

            encoded_query = query.replace(' ', '+')
            await page.goto(f"https://www.bing.com/search?q={encoded_query}", wait_until="domcontentloaded")

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

            await page.screenshot(path=get_screenshot_path("bing_search_results"))

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
            if page: await page.screenshot(path=get_screenshot_path("bing_search_error"))
            return []
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")


    async def brave_search(self, query: str, max_results: int) -> List[SearchResult]:
        page = None
        logger.info(f"Performing Brave search for: '{query}' (max_results: {max_results})")
        try:
            page = await self.get_page() # Stealth applied automatically
            # page.set_default_timeout() already called

            encoded_query = query.replace(' ', '+')
            await page.goto(f"https://search.brave.com/search?q={encoded_query}", wait_until="domcontentloaded")
            await page.wait_for_selector(".results", timeout=SEARCH_RESULTS_TIMEOUT)
            # Wait longer for JavaScript to execute
            await asyncio.sleep(3.0)  # Increase from 1.0-2.5 range

            # Wait for results to load - using updated selectors
            await page.wait_for_selector(".results", timeout=SEARCH_RESULTS_TIMEOUT)
            await asyncio.sleep(random.uniform(1.0, 2.5))

            await page.screenshot(path=get_screenshot_path("brave_search_results"))

            # Try a series of selectors to find results - Brave's HTML may have changed
            selectors_to_try = [
                "div.snippet[data-type='web']",        # Original selector
                ".fdb",                                # Original fallback
                ".result-container .organic-result",   # New potential selector
                "[data-results] .result",              # Another potential selector
                ".results .organic-result",            # More generic selector
                ".results .result",                    # Most generic selector
                "article", 
                "div > h3",
                  "div.snippet",
                    ".result"

            ]
            
            result_elements = []
            for selector in selectors_to_try:
                result_elements = await page.query_selector_all(selector)
                if result_elements:
                    logger.info(f"Found {len(result_elements)} results using selector: {selector}")
                    break
            
            if not result_elements:
                # If no elements found with specific selectors, try to debug the page structure
                logger.warning("No results found with standard selectors, saving the page for debugging")
                await page.screenshot(path=get_screenshot_path("brave_search_debug_full"))
                
                # Get all container elements that might contain results
                containers = await page.query_selector_all(".results, [data-results], main, .main-results")
                logger.info(f"Found {len(containers)} potential result containers")
                
                # Take screenshot of the potential containers area
                if containers:
                    await containers[0].screenshot(path=get_screenshot_path("brave_search_container"))
                
                # Try a very generic approach as last resort
                result_elements = await page.query_selector_all("a[href^='http']:has(h3), a[href^='http']:has(.title)")
                logger.info(f"Fallback: Found {len(result_elements)} elements with generic a[href] selector")

            results = []
            for i, element in enumerate(result_elements):
                if len(results) >= max_results: break
                try:
                    # Try different potential title selectors
                    title_element = None
                    title_selectors = [".snippet-title", ".title a", ".title", "h3", "[role='heading']"]
                    for title_selector in title_selectors:
                        title_element = await element.query_selector(title_selector)
                        if title_element: break
                    
                    # If we found a title element, extract its text
                    title = await title_element.inner_text() if title_element else None
                    
                    # Get URL directly from element if it's an anchor, or try to find anchor element
                    url = None
                    if await element.get_attribute("tagName") == "A":
                        url = await element.get_attribute("href")
                    else:
                        link_element = await element.query_selector("a[href^='http']")
                        url = await link_element.get_attribute("href") if link_element else None
                    
                    # Skip if we didn't get both title and URL or if URL is a Brave search URL
                    if not title or not url or not url.startswith("http") or "brave.com/search" in url: 
                        continue

                    # Try different potential snippet selectors
                    snippet_element = None
                    snippet_selectors = [".snippet-description", ".description", ".snippet", ".body", "p"]
                    for snippet_selector in snippet_selectors:
                        snippet_element = await element.query_selector(snippet_selector)
                        if snippet_element: break
                    
                    snippet = await snippet_element.inner_text() if snippet_element else "No description available"

                    results.append(SearchResult(
                        title=title.strip(), 
                        url=url, 
                        snippet=snippet.strip(), 
                        source_type="web_search_result",
                        metadata={"search_engine": "brave", "position": len(results) + 1, "query": query}
                    ))
                    logger.debug(f"Extracted Brave result {len(results)}: {title.strip()}")
                except Exception as e:
                    logger.warning(f"Error parsing Brave search result {i}: {str(e)}")

            logger.info(f"Successfully extracted {len(results)} Brave search results.")
            return results
        except Exception as e:
            logger.exception(f"Brave search error for '{query}': {str(e)}")
            if page: await page.screenshot(path=get_screenshot_path("brave_search_error"))
            return []
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")


    async def fetch_content(self, url: str) -> Dict[str, Any]:
        page = None
        logger.info(f"Fetching content from URL: {url}")
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
                 await page.screenshot(path=get_screenshot_path(f"fetch_http_error_{response.status}"))
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
            await page.screenshot(path=get_screenshot_path("fetch_content_success"))

            return {"content": content, "title": title.strip() if title else "No Title Found", "metadata": metadata}

        except PlaywrightTimeoutError:
            logger.warning(f"Timeout while fetching content from {url}")
            if page: await page.screenshot(path=get_screenshot_path("fetch_content_timeout"))
            return {"content": "Content fetch timed out", "title": "Timeout Error", "metadata": {"error": True, "reason": "timeout", "url": url}}
        except Exception as e:
            logger.exception(f"Error fetching content from {url}: {e}")
            if page: await page.screenshot(path=get_screenshot_path("fetch_content_error"))
            return {"content": f"Error fetching content: {str(e)}", "title": "Fetch Error", "metadata": {"error": True, "reason": str(e), "url": url}}
        finally:
            if page:
                try:
                    await page.close()
                except Exception as e:
                    logger.warning(f"Error closing page: {e}")

# ========================================================================
# FastAPI App Setup, Endpoints, and Lifecycle
# ========================================================================
browser_manager: Optional[PlaywrightBrowserManager] = None

# Replace deprecated @app.on_event with lifespan context manager
@app.on_event("startup")
async def startup_event():
    global browser_manager
    logger.info("FastAPI application startup...")
    browser_manager = PlaywrightBrowserManager()
    # Initialize eagerly at startup
    try:
        await browser_manager.initialize()
    except Exception as e:
        logger.error(f"FATAL: Browser manager failed to initialize on startup: {e}. API may not function correctly.")
        # Depending on desired behavior, you might want the app to exit here if the browser is critical
    logger.info("MCP Browser API startup sequence complete.")

@app.on_event("shutdown")
async def shutdown_event():
    global browser_manager
    logger.info("FastAPI application shutdown...")
    if browser_manager:
        await browser_manager.close()
    logger.info("MCP Browser API shutdown sequence complete.")

async def get_browser_manager() -> PlaywrightBrowserManager:
    """Dependency to get the initialized browser manager instance."""
    if not browser_manager or not browser_manager._initialized:
         logger.error("Browser manager requested but not available or not initialized.")
         raise HTTPException(status_code=503, detail="Browser service is unavailable or not initialized")
    return browser_manager

# --- API Endpoints ---

@app.post("/search", response_model=SearchResponse, tags=["Search"])
async def search(request: SearchRequest, manager: PlaywrightBrowserManager = Depends(get_browser_manager)):
    """Performs search on Bing or Brave."""
    try:
        start_time = time.time()
        logger.info(f"Received search request: Engine='{request.search_engine}', Query='{request.query}', Max Results='{request.max_results}'")
        search_engine = request.search_engine.lower()
        results = []

        if search_engine == "bing": 
            results = await manager.bing_search(request.query, request.max_results)
        elif search_engine == "brave": 
            results = await manager.brave_search(request.query, request.max_results)
        else:
            logger.warning(f"Unsupported search engine requested: {request.search_engine}")
            raise HTTPException(status_code=400, detail=f"Unsupported search engine: {request.search_engine}. Use 'bing' or 'brave'.")

        elapsed = time.time() - start_time
        logger.info(f"Search completed in {elapsed:.2f} seconds. Found {len(results)} results.")
        return SearchResponse(results=results, query=request.query, search_engine=request.search_engine, timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.exception(f"Critical error in /search endpoint for query '{request.query}': {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error during search: {str(e)}")

@app.post("/fetch", response_model=FetchResponse, tags=["Content Fetching"])
async def fetch(request: FetchRequest, manager: PlaywrightBrowserManager = Depends(get_browser_manager)):
    """Fetches main content and title from a given URL."""
    try:
        start_time = time.time()
        url_str = str(request.url)
        logger.info(f"Received fetch request for URL: {url_str}")
        content_data = await manager.fetch_content(url_str)
        elapsed = time.time() - start_time
        logger.info(f"Fetch completed in {elapsed:.2f} seconds for URL: {url_str}. Content length: {len(content_data.get('content', ''))}")

        if content_data.get("metadata", {}).get("error"):
             status = content_data["metadata"].get("status", 500)
             reason = content_data["metadata"].get("reason", "Unknown fetch error")
             detail = f"Failed to fetch content from {url_str}. Reason: {reason}"
             if status and status >= 400:
                 # If we have a specific HTTP error status from the target site
                 raise HTTPException(status_code=status, detail=detail)
             else:
                 # Otherwise, treat as a general server error from our side
                 raise HTTPException(status_code=500, detail=detail)

        return FetchResponse(url=url_str, content=content_data["content"], title=content_data["title"], metadata=content_data["metadata"], timestamp=datetime.now().isoformat())
    except HTTPException as http_exc:
         raise http_exc # Re-raise exceptions we created deliberately
    except Exception as e:
        logger.exception(f"Critical error in /fetch endpoint for URL '{request.url}': {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error during fetch: {str(e)}")


@app.get("/health", tags=["Meta"])
async def health_check():
    """Health check endpoint for API status and browser connectivity."""
    manager_status = "not_created"
    browser_connected = False
    context_available = False
    if browser_manager:
        manager_status = "initialized" if browser_manager._initialized else "created_not_initialized"
        if browser_manager.browser: browser_connected = browser_manager.browser.is_connected()
        if browser_manager.context: context_available = not browser_manager._context_closed  # Use our manually tracked state

    api_status = "healthy"
    if not browser_manager or not browser_manager._initialized or not browser_connected or not context_available:
         api_status = "degraded" # Degraded if browser components are down

    return {
        "status": api_status, "time": datetime.now().isoformat(),
        "browser_manager_status": manager_status, "browser_type_configured": BROWSER_TYPE,
        "headless_configured": IS_HEADLESS, "browser_connected": browser_connected,
        "browser_context_available": context_available,
        "supported_search_engines": ["bing", "brave"]  # Updated list of supported engines
    }

# --- Main Execution ---
if __name__ == "__main__":
    # Make sure necessary browser binaries are installed:
    # playwright install # Installs chromium by default
    # playwright install firefox # If using firefox
    # playwright install webkit # If using webkit
    logger.info(f"Starting MCP Browser API server on host 0.0.0.0, port 8000...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False) # reload=False for production