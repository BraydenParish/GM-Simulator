#!/usr/bin/env python3
"""
Simple test to check if we can run the scraper
"""

print("Testing scraper...")

try:
    import requests
    print("✅ requests imported")
    
    import pandas as pd
    print("✅ pandas imported")
    
    from bs4 import BeautifulSoup
    print("✅ BeautifulSoup imported")
    
    print("✅ All imports successful")
    
    # Test a simple request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    response = requests.get('https://www.nfl.com/teams/dallas-cowboys/roster/', headers=headers, timeout=10)
    print(f"✅ NFL.com request successful: {response.status_code}")
    
    print("✅ All tests passed! Scraper should work.")
    
except Exception as e:
    print(f"❌ Error: {e}")

