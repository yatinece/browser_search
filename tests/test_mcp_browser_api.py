# tests/test_mcp_browser_api.py
import unittest
import requests
import json
import time
import subprocess
import signal
import os
import sys
import logging
from pathlib import Path

# Add the package to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

class TestMCPBrowserAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Start the server in a subprocess
        cls.server_process = subprocess.Popen(
            ["uvicorn", "mcp_browser_api.main:app", "--host", "127.0.0.1", "--port", "8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid if os.name != 'nt' else None
        )
        
        # Wait for the server to start
        time.sleep(5)
        
        cls.base_url = "http://127.0.0.1:8000"
        logging.info("Test server started")
    
    @classmethod
    def tearDownClass(cls):
        # Shut down the server
        if os.name != 'nt':
            os.killpg(os.getpgid(cls.server_process.pid), signal.SIGTERM)
        else:
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(cls.server_process.pid)])
        logging.info("Test server stopped")
    
    def test_google_search(self):
        # Test Google search endpoint
        payload = {
            "query": "python fastapi tutorial",
            "max_results": 5,
            "source_types": ["article", "blog"],
            "search_engine": "google"
        }
        
        response = requests.post(f"{self.base_url}/search", json=payload)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("results", data)
        self.assertTrue(len(data["results"]) > 0)
        
        # Check structure of results
        first_result = data["results"][0]
        self.assertIn("title", first_result)
        self.assertIn("url", first_result)
        self.assertIn("snippet", first_result)
        
        print(f"Google Search Test: Found {len(data['results'])} results")
        print(f"First result: {first_result['title']}")
    
    def test_fetch_content(self):
        # Test fetch endpoint with a stable URL
        payload = {
            "url": "https://python.org"
        }
        
        response = requests.post(f"{self.base_url}/fetch", json=payload)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("content", data)
        self.assertTrue(len(data["content"]) > 0)
        
        print(f"Fetch Test: Retrieved {len(data['content'])} characters of content")
    
    def test_bing_search(self):
        # Test Bing search endpoint
        payload = {
            "query": "machine learning basics",
            "max_results": 3,
            "search_engine": "bing"
        }
        
        response = requests.post(f"{self.base_url}/search", json=payload)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn("results", data)
        
        print(f"Bing Search Test: Found {len(data['results'])} results")
        if data["results"]:
            print(f"First result: {data['results'][0]['title']}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    unittest.main()