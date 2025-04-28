from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Any, Optional

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