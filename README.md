# MCP Browser API

This package implements a Multi-Context Processing (MCP) server that uses your Chrome browser to perform web searches and fetch content from URLs. It provides a FastAPI-based interface that conforms to the MCP API specification.

## Features

- Search the web using Google, Bing, or Brave through your Chrome browser
- Fetch full content from URLs
- FastAPI endpoints compatible with MCP specifications
- Comprehensive logging of all operations
- Simple client for easy integration

## Installation

1. Clone this repository or download the package
2. Install the package:

```bash
pip install -e .
```

## Requirements

- Python 3.8+
- Chrome browser installed
- ChromeDriver (installed automatically via webdriver-manager)

## Usage

### Starting the server

```bash
uvicorn mcp_browser_api.main:app --host 0.0.0.0 --port 8000
```

### Using the API

#### Search endpoint

```
POST /search
```

Request body:

```json
{
  "query": "python fastapi tutorial",
  "max_results": 10,
  "source_types": ["article", "blog"],
  "search_engine": "google"
}
```

Response:

```json
{
  "results": [
    {
      "title": "Result Title",
      "url": "https://example.com/article",
      "snippet": "Result snippet text...",
      "content": "",
      "source_type": "article",
      "metadata": {
        "search_engine": "google"
      }
    },
    // More results...
  ]
}
```

#### Fetch endpoint

```
POST /fetch
```

Request body:

```json
{
  "url": "https://example.com/article"
}
```

Response:

```json
{
  "content": "Full text content of the page..."
}
```

### Using the client

```python
from mcp_browser_api.client import MCPBrowserClient

# Initialize the client
client = MCPBrowserClient(base_url="http://localhost:8000")

# Search with Google
results = client.search("python fastapi tutorial", max_results=5)
print(results)

# Search with Bing
results = client.search("machine learning basics", search_engine="bing")
print(results)

# Fetch content from a URL
content = client.fetch("https://python.org")
print(content)
```

## MCP Compatibility

This implementation follows the MCP API specification, providing the required `/search` and `/fetch` endpoints with the expected request and response formats. It can be used as a drop-in replacement for any system expecting an MCP-compatible server.

## Browser Visibility

By default, the browser runs in headless mode, meaning you won't see it opening and performing searches. If you want to see the browser in action:

1. Open `mcp_browser_api/main.py`
2. Find the line `options.add_argument("--headless")` in the `setup_browser` method
3. Comment out or remove that line
4. Restart the server

## Logs

Logs are stored in the `logs` directory with timestamps in the filename. Each log entry includes:
- Timestamp
- Log level (INFO, WARNING, ERROR)
- Source component
- Message details

You can monitor the logs in real-time using:

```bash
tail -f logs/mcp_browser_api_*.log
```

## Running Tests

```bash
python -m tests.test_mcp_browser_api
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.
=======
