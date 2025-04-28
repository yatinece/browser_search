import asyncio
import logging
import random
from typing import List, Dict, Any
from playwright.async_api import async_playwright, Page, Error as PlaywrightError, TimeoutError as PlaywrightTimeoutError
from pydantic import BaseModel

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

SEARCH_RESULTS_TIMEOUT = 20000  # Increased timeout in milliseconds

def get_screenshot_path(filename: str) -> str:
    """Generates a file path for saving screenshots."""
    return f"screenshots/{filename}.png"

class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str
    source_type: str
    metadata: Dict[str, Any]

class BraveSearch:
    def __init__(self):
        self._browser = None
        self._page = None
        self._context = None

    async def initialize(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(headless=False)
        self._context = await self._browser.new_context(user_agent=self.get_random_user_agent())

    async def close(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    async def get_page(self) -> Page:
        if not self._page or self._page.is_closed():
            self._page = await self._context.new_page()
            await self.apply_stealth(self._page)
        return self._page

    async def apply_stealth(self, page: Page):
        await page.evaluate("""() => {
            navigator.webdriver = false;
            Object.defineProperty(navigator, 'plugins', {
                get: () => [{}, {}, {}, {}, {}],
            });
        }""")

    def get_random_user_agent(self) -> str:
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/120.0.2210.144",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Version/17.1.2 Safari/605.1.15",
        ]
        return random.choice(user_agents)

    # async def brave_search(self, query: str, max_results: int) -> List[SearchResult]:
    #     page = await self.get_page()
    #     results = []
    #     logger.info(f"Performing Brave search for: '{query}' (max_results: {max_results})")
    #     try:
    #         encoded_query = query.replace(' ', '+')
    #         search_url = f"https://search.brave.com/search?q={encoded_query}"
    #         logger.debug(f"Navigating to Brave search URL: {search_url}")
    #         await page.goto(search_url, wait_until="domcontentloaded")

    #         # Try to extract LLM snippet
    #         llm_snippet_element = await page.query_selector("#llm-snippet")
    #         if llm_snippet_element:
    #             logger.info("LLM snippet found. Attempting to extract...");
    #             try:
    #                 await page.wait_for_selector("#llm-snippet h1#chatllm-title div", timeout=5000)
    #                 await page.wait_for_selector("#llm-snippet div#chatllm-main-answer-content", timeout=5000)
    #                 llm_title_element = await llm_snippet_element.query_selector("h1#chatllm-title div")
    #                 llm_answer_element = await llm_snippet_element.query_selector("div#chatllm-main-answer-content")
    #                 llm_title = await llm_title_element.inner_text() if llm_title_element else "AI Generated Answer"
    #                 llm_answer = await llm_answer_element.inner_text() if llm_answer_element else "No answer provided."

    #                 results.append(SearchResult(
    #                     title=llm_title.strip(),
    #                     url="brave://ai-generated-answer",
    #                     snippet=llm_answer.strip(),
    #                     source_type="llm_answer",
    #                     metadata={"search_engine": "brave", "query": query}
    #                 ))
    #                 logger.info("Successfully extracted LLM snippet.")
    #             except PlaywrightTimeoutError:
    #                 logger.warning("Timeout waiting for elements within the LLM snippet.")

    #         # Extract regular web results
    #         results_container_selector = "#results"
    #         result_item_selector = "div.snippet[data-type='web']"
    #         link_selector = "a.heading-serpresult"
    #         title_selector = "div.title"
    #         snippet_selector = "div.snippet-description"

    #         logger.debug(f"Waiting for results container: '{results_container_selector}'")
    #         try:
    #             await page.wait_for_selector(results_container_selector, timeout=SEARCH_RESULTS_TIMEOUT)
    #             logger.debug(f"Results container '{results_container_selector}' found.")
    #         except PlaywrightTimeoutError:
    #             logger.error(f"Timeout waiting for Brave results container ('{results_container_selector}'). Page structure might have changed or search failed.")
    #             await page.screenshot(path=get_screenshot_path("brave_results_container_timeout"))
    #             return results # Return any LLM result found

    #         await asyncio.sleep(random.uniform(1.0, 2.5))
    #         await page.screenshot(path=get_screenshot_path("brave_search_results"))

    #         logger.debug(f"Querying for result items using selector: '{result_item_selector}'")
    #         result_elements = await page.query_selector_all(result_item_selector)
    #         logger.info(f"Found {len(result_elements)} raw Brave search result elements matching '{result_item_selector}'.")

    #         count = 0
    #         for i, element in enumerate(result_elements):
    #             if count >= max_results:
    #                 logger.info(f"Reached max_results ({max_results}). Stopping extraction.")
    #                 break
    #             try:
    #                 link_element = await element.query_selector(link_selector)
    #                 if not link_element:
    #                     logger.debug(f"Skipping result {i+1}: Link element ('{link_selector}') not found.")
    #                     continue

    #                 url = await link_element.get_attribute("href")
    #                 title_element = await link_element.query_selector(title_selector)
    #                 title = await title_element.inner_text() if title_element else None

    #                 if not title or not url or not url.startswith("http"):
    #                     logger.debug(f"Skipping result {i+1}: Missing title/URL or invalid URL ({url}). Title: '{title}'")
    #                     continue
    #                 if "brave.com/search" in url:
    #                     logger.debug(f"Skipping result {i+1}: Internal Brave link ({url}).")
    #                     continue

    #                 snippet_element = await element.query_selector(snippet_selector)
    #                 snippet = "No description available"
    #                 if snippet_element:
    #                     raw_snippet = await snippet_element.inner_text()
    #                     snippet = ' '.join(raw_snippet.split()).strip()

    #                 results.append(SearchResult(
    #                     title=title.strip(),
    #                     url=url,
    #                     snippet=snippet,
    #                     source_type="web_search_result",
    #                     metadata={"search_engine": "brave", "position": count + 1, "query": query, "raw_element_index": i + 1}
    #                 ))
    #                 count += 1
    #                 logger.debug(f"Extracted Brave result {count}: {title.strip()} -> {url}")

    #             except Exception as e:
    #                 logger.warning(f"Error parsing Brave search result element index {i}: {str(e)}", exc_info=False)

    #         logger.info(f"Successfully extracted {len(results)} valid Brave search results.")

    #     except PlaywrightError as e:
    #         logger.error(f"Playwright error during Brave search: {e}")
    #         if page:
    #             await page.screenshot(path=get_screenshot_path("brave_error"))
    #     except Exception as e:
    #         logger.error(f"An unexpected error occurred during Brave search: {e}", exc_info=True)
    #     finally:
    #         pass
    #     return results
    async def brave_search(self, query: str, max_results: int) -> List[SearchResult]:
        page = await self.get_page()
        results = []
        logger.info(f"Performing Brave search for: '{query}' (max_results: {max_results})")
        try:
            encoded_query = query.replace(' ', '+')
            search_url = f"https://search.brave.com/search?q={encoded_query}"
            logger.debug(f"Navigating to Brave search URL: {search_url}")
            await page.goto(search_url, wait_until="domcontentloaded")

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
                            #await page.wait_for_selector(answer_content_selector, timeout=5000, state="visible")
                            #await page.wait_for_load_state("networkidle", timeout=1000)
                        except PlaywrightTimeoutError:
                            logger.warning("Timeout waiting for 'More' button to become visible or clicking it.")
                        except Exception as e:
                            logger.warning(f"Error interacting with 'More' button: {e}")

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
                        url="brave://ai-generated-answer",
                        snippet=llm_answer,
                        source_type="llm_answer",
                        metadata={"search_engine": "brave", "query": query}
                    ))
                    logger.info("Successfully extracted LLM snippet.")

                except PlaywrightTimeoutError:
                    logger.warning("Timeout waiting for LLM elements or interacting with 'More' button.")
                except Exception as e:
                    logger.warning(f"Error interacting with LLM snippet: {e}")

            # Extract regular web results (rest of your code remains the same)
            results_container_selector = "#results"
            result_item_selector = "div.snippet[data-type='web']"
            link_selector = "a.heading-serpresult"
            title_selector = "div.title"
            snippet_selector = "div.snippet-description"

            logger.debug(f"Waiting for results container: '{results_container_selector}'")
            try:
                await page.wait_for_selector(results_container_selector, timeout=SEARCH_RESULTS_TIMEOUT)
                logger.debug(f"Results container '{results_container_selector}' found.")
            except PlaywrightTimeoutError:
                logger.error(f"Timeout waiting for Brave results container ('{results_container_selector}'). Page structure might have changed or search failed.")
                await page.screenshot(path=get_screenshot_path("brave_results_container_timeout"))
                return results # Return any LLM result found

            await asyncio.sleep(random.uniform(1.0, 2.5))
            await page.screenshot(path=get_screenshot_path("brave_search_results"))

            logger.debug(f"Querying for result items using selector: '{result_item_selector}'")
            result_elements = await page.query_selector_all(result_item_selector)
            logger.info(f"Found {len(result_elements)} raw Brave search result elements matching '{result_item_selector}'.")

            count = 0
            for i, element in enumerate(result_elements):
                if count >= max_results:
                    logger.info(f"Reached max_results ({max_results}). Stopping extraction.")
                    break
                try:
                    link_element = await element.query_selector(link_selector)
                    if not link_element:
                        logger.debug(f"Skipping result {i+1}: Link element ('{link_selector}') not found.")
                        continue

                    url = await link_element.get_attribute("href")
                    title_element = await link_element.query_selector(title_selector)
                    title = await title_element.inner_text() if title_element else None

                    if not title or not url or not url.startswith("http"):
                        logger.debug(f"Skipping result {i+1}: Missing title/URL or invalid URL ({url}). Title: '{title}'")
                        continue
                    if "brave.com/search" in url:
                        logger.debug(f"Skipping result {i+1}: Internal Brave link ({url}).")
                        continue

                    snippet_element = await element.query_selector(snippet_selector)
                    snippet = "No description available"
                    if snippet_element:
                        raw_snippet = await snippet_element.inner_text()
                        snippet = ' '.join(raw_snippet.split()).strip()

                    results.append(SearchResult(
                        title=title.strip(),
                        url=url,
                        snippet=snippet,
                        source_type="web_search_result",
                        metadata={"search_engine": "brave", "position": count + 1, "query": query, "raw_element_index": i + 1}
                    ))
                    count += 1
                    logger.debug(f"Extracted Brave result {count}: {title.strip()} -> {url}")

                except Exception as e:
                    logger.warning(f"Error parsing Brave search result element index {i}: {str(e)}", exc_info=False)

            logger.info(f"Successfully extracted {len(results)} valid Brave search results.")

        except PlaywrightError as e:
            logger.error(f"Playwright error during Brave search: {e}")
            if page:
                await page.screenshot(path=get_screenshot_path("brave_error"))
        except Exception as e:
            logger.error(f"An unexpected error occurred during Brave search: {e}", exc_info=True)
        finally:
            pass
        return results

async def main():
    brave_search_engine = BraveSearch()
    await brave_search_engine.initialize()
    page = await brave_search_engine.get_page()

    query = "what is india"
    max_results = 10
    results = await brave_search_engine.brave_search(query, max_results)

    logger.info(f"Brave Search Results for '{query}':")
    for result in results:
        logger.info(f"- Title: {result.title}")
        logger.info(f"  URL: {result.url}")
        logger.info(f"  Snippet: {result.snippet}")
        logger.info(f"  Source Type: {result.source_type}")
        logger.info(f"  Metadata: {result.metadata}")
        logger.info("-" * 20)

    await page.close()
    await brave_search_engine.close()

if __name__ == "__main__":
    asyncio.run(main())