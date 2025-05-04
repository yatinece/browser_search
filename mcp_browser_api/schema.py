from pydantic import BaseModel, HttpUrl
from typing import List, Dict, Any, Optional
from datetime import date
from enum import Enum

# --- Pydantic Models (no changes needed from previous version) ---
class SearchRequest(BaseModel):
    query: str
    max_results: int = 10
    source_types: Optional[List[str]] = ["article", "blog"]
    search_engine: str = "bing"

class TimeFilterEnum(str, Enum):
    past_hour = "past_hour"
    past_day = "past_day"
    past_week = "past_week"
    past_month = "past_month"
    past_year = "past_year"
    custom = "custom"

class SearchRequest(BaseModel):
    query: str
    max_results: int = 10
    source_types: Optional[List[str]] = ["article", "blog"]
    search_engine: str = "bing"  # "bing", "google", "brave"
    time_filter: Optional[TimeFilterEnum] = None
    custom_start_date: Optional[date] = None  # Only for time_filter == "custom"
    custom_end_date: Optional[date] = None

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