import asyncio
import json
import logging
import os
import random
import time
import re
from datetime import datetime
from typing import List, Dict, Any, Optional
from .PlaywrightBrowserManager import PlaywrightBrowserManager
from .schema import SearchRequest , SearchResult , SearchResponse, FetchRequest, FetchResponse
import uvicorn
from fastapi import FastAPI, HTTPException, Depends  # Removed BackgroundTasks unless needed
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()  # Automatically looks for .env in current dir
# ========================================================================
# Configuration Constants & Environment Variables
# ========================================================================

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
    format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s - %(message)s",
    handlers=[
        logging.FileHandler(log_filename),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("mcp_browser_api")
logger.info(f"Configuration: HEADLESS={IS_HEADLESS}, BROWSER_TYPE={BROWSER_TYPE}")


# ========================================================================
# Application Lifespan Context
# ========================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handles startup and shutdown using FastAPI's lifespan context."""
    logger.info("Lifespan startup: initializing browser manager...")
    # Instantiate without passing browser_type/headless; manager reads its own config
    app.state.browser_manager = PlaywrightBrowserManager()
    try:
        await app.state.browser_manager.initialize()
        logger.info("Browser manager initialized successfully.")
    except Exception as e:
        logger.error(f"Fatal error during browser initialization: {e}")

    yield  # Startup complete; serve requests

    logger.info("Lifespan shutdown: closing browser manager...")
    try:
        await app.state.browser_manager.close()
        logger.info("Browser manager closed cleanly.")
    except Exception as e:
        logger.error(f"Error during browser shutdown: {e}")
    logger.info("Lifespan shutdown complete.")


# ========================================================================
# FastAPI App Definition
# ========================================================================
app = FastAPI(
    title="MCP Browser API",
    description="API using Playwright for stealthy web scraping tasks like search and content fetching.",
    version="1.1.0",
    lifespan=lifespan
)

# ========================================================================
# Dependency
# ========================================================================
async def get_browser_manager() -> PlaywrightBrowserManager:
    manager = getattr(app.state, "browser_manager", None)
    if not manager or not getattr(manager, "_initialized", False):
        logger.error("Browser manager unavailable or not initialized.")
        raise HTTPException(status_code=503, detail="Browser service is unavailable or not initialized")
    return manager
# ========================================================================
# FastAPI App Setup, Endpoints, and Lifecycle
# ========================================================================
# browser_manager: Optional[PlaywrightBrowserManager] = None

# # Replace deprecated @app.on_event with lifespan context manager
# @app.on_event("startup")
# async def startup_event():
#     global browser_manager
#     logger.info("FastAPI application startup...")
#     browser_manager = PlaywrightBrowserManager()
#     # Initialize eagerly at startup
#     try:
#         await browser_manager.initialize()
#     except Exception as e:
#         logger.error(f"FATAL: Browser manager failed to initialize on startup: {e}. API may not function correctly.")
#         # Depending on desired behavior, you might want the app to exit here if the browser is critical
#     logger.info("MCP Browser API startup sequence complete.")

# @app.on_event("shutdown")
# async def shutdown_event():
#     global browser_manager
#     logger.info("FastAPI application shutdown...")
#     if browser_manager:
#         await browser_manager.close()
#     logger.info("MCP Browser API shutdown sequence complete.")

# async def get_browser_manager() -> PlaywrightBrowserManager:
#     """Dependency to get the initialized browser manager instance."""
#     if not browser_manager or not browser_manager._initialized:
#          logger.error("Browser manager requested but not available or not initialized.")
#          raise HTTPException(status_code=503, detail="Browser service is unavailable or not initialized")
#     return browser_manager

# --- API Endpoints ---

@app.post("/search", response_model=SearchResponse, tags=["Search"])
async def search(request: SearchRequest, manager: PlaywrightBrowserManager = Depends(get_browser_manager)):
    """Performs search on Google, Bing, or Brave."""
    # Endpoint implementation remains largely the same, relies on manager methods
    try:
        if request.search_engine not in ["google", "bing", "brave"]:
            raise HTTPException(status_code=400, detail="Invalid search engine. Use 'google', 'bing', or 'brave'")
    
        if request.time_filter == "custom" and (not request.custom_start_date or not request.custom_end_date):
            raise HTTPException(status_code=400, detail="Custom time filter requires both start and end dates")
        start_time = time.time()
        logger.info(f"Received search request: Engine='{request.search_engine}', Query='{request.query}', Max Results='{request.max_results}'")
        search_engine = request.search_engine.lower()
        results = []

        # Call the appropriate search method based on the engine
        if request.search_engine == "google":
            results = await manager.Google_Search(
                query=request.query,
                max_results=request.max_results,
                time_filter=request.time_filter,
                custom_start_date=request.custom_start_date,
                custom_end_date=request.custom_end_date
            )
        elif request.search_engine == "bing":
            results = await manager.bing_search(
                query=request.query,
                max_results=request.max_results,
                time_filter=request.time_filter,
                custom_start_date=request.custom_start_date,
                custom_end_date=request.custom_end_date
            )
        elif request.search_engine == "brave":
            results = await manager.brave_search(
                query=request.query,
                max_results=request.max_results,
                time_filter=request.time_filter,
                custom_start_date=request.custom_start_date,
                custom_end_date=request.custom_end_date
            )
        else:
            logger.warning(f"Unsupported search engine requested: {request.search_engine}")
            raise HTTPException(status_code=400, detail=f"Unsupported search engine: {request.search_engine}. Use 'google', 'bing', or 'brave'.")

        elapsed = time.time() - start_time
        logger.info(f"Search completed in {elapsed:.2f} seconds. Found {len(results)} results.")
        return SearchResponse(results=results, query=request.query, search_engine=request.search_engine, timestamp=datetime.now().isoformat())
    except Exception as e:
        logger.exception(f"Critical error in /search endpoint for query '{request.query}': {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error during search: {str(e)}")




@app.post("/fetch", response_model=FetchResponse, tags=["Content Fetching"])
async def fetch(request: FetchRequest, manager: PlaywrightBrowserManager = Depends(get_browser_manager)):
    """Fetches main content and title from a given URL."""
    # Endpoint implementation remains largely the same
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
    manager = getattr(app.state, "browser_manager", None)
    status = "healthy"
    connected = False
    context_ok = False

    if manager:
        connected = manager.browser.is_connected() if manager.browser else False
        context_ok = not manager.context.is_closed() if manager.context else False
        if not (manager._initialized and connected and context_ok):
            status = "degraded"
    else:
        status = "degraded"

    return {
        "status": status,
        "time": datetime.now().isoformat(),
        "browser_manager_initialized": getattr(manager, "_initialized", False),
        "browser_type": BROWSER_TYPE,
        "headless": IS_HEADLESS,
        "browser_connected": connected,
        "context_available": context_ok
    }
# --- Main Execution ---
if __name__ == "__main__":
    # Make sure necessary browser binaries are installed:
    # playwright install # Installs chromium by default
    # playwright install firefox # If using firefox
    # playwright install webkit # If using webkit
    logger.info(f"Starting MCP Browser API server on host 0.0.0.0, port 8000...")
    uvicorn.run("mcp_browser_api.main:app", host="0.0.0.0", port=8000, reload=False) # reload=False for production