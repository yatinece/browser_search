# mcp_browser_api/client.py
import requests
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, Union

class MCPBrowserClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.logger = logging.getLogger("mcp_browser_client")
        self.session = requests.Session()
    
    def search(self, 
               query: str, 
               max_results: int = 10, 
               source_types: Optional[List[str]] = None, 
               search_engine: str = "bing") -> Dict[str, Any]:
        """
        Search the web using the specified search engine.
        
        Args:
            query: The search query string
            max_results: Maximum number of results to return
            source_types: List of source types to filter by (e.g. ["article", "blog"])
            search_engine: The search engine to use (google, bing, or brave)
            
        Returns:
            Dictionary containing search results
        """
        if source_types is None:
            source_types = ["article", "blog"]
            
        payload = {
            "query": query,
            "max_results": max_results,
            "source_types": source_types,
            "search_engine": search_engine
        }
        
        self.logger.info(f"Sending search request: {query} (engine: {search_engine})")
        try:
            response = self.session.post(f"{self.base_url}/search", json=payload, timeout=60)
            
            if response.status_code == 200:
                results = response.json()
                self.logger.info(f"Search completed. Found {len(results.get('results', []))} results.")
                return results
            else:
                self.logger.error(f"Search failed with status code {response.status_code}: {response.text}")
                return {"error": response.text, "status_code": response.status_code}
        except requests.RequestException as e:
            self.logger.error(f"Request exception during search: {str(e)}")
            return {"error": str(e), "status_code": None}
    
    def fetch(self, url: str) -> Dict[str, Any]:
        """
        Fetch the full content from a URL.
        
        Args:
            url: The URL to fetch content from
            
        Returns:
            Dictionary containing the fetched content
        """
        payload = {"url": url}
        
        self.logger.info(f"Sending fetch request for URL: {url}")
        try:
            response = self.session.post(f"{self.base_url}/fetch", json=payload, timeout=90)
            
            if response.status_code == 200:
                content_data = response.json()
                content_length = len(content_data.get("content", ""))
                title = content_data.get("title", "No title")
                self.logger.info(f"Fetch completed. Retrieved {content_length} characters of content with title: {title}")
                return content_data
            else:
                self.logger.error(f"Fetch failed with status code {response.status_code}: {response.text}")
                return {"error": response.text, "status_code": response.status_code}
        except requests.RequestException as e:
            self.logger.error(f"Request exception during fetch: {str(e)}")
            return {"error": str(e), "status_code": None}
    
    def health_check(self) -> Dict[str, Any]:
        """
        Check if the API server is healthy.
        
        Returns:
            Dictionary containing health status info
        """
        try:
            response = self.session.get(f"{self.base_url}/health", timeout=10)
            
            if response.status_code == 200:
                health_data = response.json()
                self.logger.info(f"Health check successful: {health_data}")
                return health_data
            else:
                self.logger.error(f"Health check failed with status code {response.status_code}: {response.text}")
                return {"status": "unhealthy", "error": response.text}
        except requests.RequestException as e:
            self.logger.error(f"Request exception during health check: {str(e)}")
            return {"status": "unreachable", "error": str(e)}
    
    def batch_search(self, queries: List[str], search_engine: str = "bing", max_results: int = 5) -> Dict[str, Any]:
        """
        Perform multiple searches in sequence and aggregate results.
        
        Args:
            queries: List of search queries to perform
            search_engine: Search engine to use for all queries
            max_results: Maximum results per query
            
        Returns:
            Dictionary with results for each query
        """
        self.logger.info(f"Starting batch search for {len(queries)} queries")
        results = {}
        
        for query in queries:
            self.logger.info(f"Processing batch query: {query}")
            search_result = self.search(query, max_results=max_results, search_engine=search_engine)
            results[query] = search_result
        
        self.logger.info(f"Completed batch search for {len(queries)} queries")
        return results
        
    def fetch_search_results(self, query: str, max_results: int = 5, search_engine: str = "bing") -> Dict[str, Any]:
        """
        Search and then fetch content for each search result.
        
        Args:
            query: The search query
            max_results: Maximum number of search results
            search_engine: Search engine to use
            
        Returns:
            Dictionary with search results and their full content
        """
        self.logger.info(f"Starting combined search and fetch for query: {query}")
        
        # First, perform the search
        search_results = self.search(query, max_results=max_results, search_engine=search_engine)
        
        if "error" in search_results:
            self.logger.error(f"Search failed: {search_results.get('error')}")
            return search_results
        
        # Then fetch content for each result
        results_with_content = []
        
        for result in search_results.get("results", []):
            url = result.get("url")
            self.logger.info(f"Fetching content for search result: {url}")
            
            try:
                content_data = self.fetch(url)
                
                # Merge the search result with the fetched content
                full_result = {**result}  # Create a copy of the search result
                
                if "error" not in content_data:
                    full_result["content"] = content_data.get("content", "")
                    full_result["full_title"] = content_data.get("title", result.get("title", ""))
                    full_result["metadata"] = {**full_result.get("metadata", {}), **content_data.get("metadata", {})}
                else:
                    full_result["content"] = ""
                    full_result["fetch_error"] = content_data.get("error")
                
                results_with_content.append(full_result)
            except Exception as e:
                self.logger.error(f"Error processing result {url}: {str(e)}")
                results_with_content.append({
                    **result,
                    "content": "",
                    "fetch_error": str(e)
                })
        
        self.logger.info(f"Completed combined search and fetch, processed {len(results_with_content)} results")
        
        # Return the combined results
        return {
            "query": query,
            "search_engine": search_engine,
            "results": results_with_content,
            "timestamp": search_results.get("timestamp")
        }


if __name__ == "__main__":
    # Example usage
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    client = MCPBrowserClient()
    
    # Check if the server is running
    health = client.health_check()
    print(f"Server health: {health}")
    
    # Example 1: Search with Google
    google_results = client.search("python playwright tutorial", max_results=5)
    print("\nGoogle Search Results:")
    for i, result in enumerate(google_results.get("results", [])):
        print(f"{i+1}. {result['title']} - {result['url']}")
    
    # Example 2: Search with Bing
    bing_results = client.search("machine learning basics", max_results=3, search_engine="bing")
    print("\nBing Search Results:")
    for i, result in enumerate(bing_results.get("results", [])):
        print(f"{i+1}. {result['title']} - {result['url']}")
    
    # Example 3: Fetch content from a URL
    if google_results.get("results"):
        first_url = google_results["results"][0]["url"]
        content_data = client.fetch(first_url)
        print(f"\nFetched content from {first_url}:")
        print(f"Title: {content_data.get('title', 'No title')}")
        print(f"Content length: {len(content_data.get('content', ''))}")
        print(content_data.get("content", "")[:200] + "...")  # Print first 200 chars
    
    # Example 4: Search and fetch content in one call
    search_and_fetch = client.fetch_search_results("web scraping best practices", max_results=2)
    print("\nSearch and Fetch Results:")
    for i, result in enumerate(search_and_fetch.get("results", [])):
        print(f"{i+1}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Content length: {len(result.get('content', ''))}")
        print(f"   Content snippet: {result.get('content', '')[:100]}...")