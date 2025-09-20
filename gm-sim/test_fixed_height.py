#!/usr/bin/env python3
"""
Test the fixed height parsing
"""

import requests
from bs4 import BeautifulSoup
import re

def parse_height(height_str: str) -> int:
    """Convert height to inches - NFL.com gives us inches directly"""
    if not height_str or height_str == '-':
        return 0
    try:
        # NFL.com gives us height in inches directly (e.g., "76")
        return int(height_str)
    except:
        return 0

def test_fixed_height():
    """Test the fixed height parsing"""
    url = "https://www.nfl.com/teams/dallas-cowboys/roster/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            return
        
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', {'class': 'd3-o-table'})
        
        if not table:
            print("No table found")
            return
        
        rows = table.find_all('tr')[1:6]  # Skip header, get first 5 data rows
        
        print("Testing fixed height parsing:")
        for i, row in enumerate(rows):
            cells = row.find_all('td')
            if len(cells) >= 6:
                name = cells[0].get_text().strip()
                height_str = cells[4].get_text().strip()
                weight_str = cells[5].get_text().strip()
                
                height = parse_height(height_str)
                weight = int(weight_str) if weight_str else 0
                
                print(f"  {i+1}. {name} - Height: '{height_str}' -> {height}\" - Weight: '{weight_str}' -> {weight}lbs")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_fixed_height()
