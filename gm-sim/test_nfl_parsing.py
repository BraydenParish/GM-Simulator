#!/usr/bin/env python3
"""
Test NFL.com parsing to understand the table structure
"""

import requests
from bs4 import BeautifulSoup
import re

def test_nfl_parsing():
    """Test parsing one team to understand the structure"""
    url = "https://www.nfl.com/teams/dallas-cowboys/roster/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            return
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all tables
        tables = soup.find_all('table')
        print(f"Found {len(tables)} tables")
        
        for i, table in enumerate(tables):
            print(f"\nTable {i+1}:")
            print(f"  Classes: {table.get('class', [])}")
            print(f"  ID: {table.get('id', 'None')}")
            
            # Get table headers
            headers_row = table.find('thead')
            if headers_row:
                headers = headers_row.find_all(['th', 'td'])
                header_texts = [h.get_text().strip() for h in headers]
                print(f"  Headers: {header_texts}")
            
            # Get first few rows
            rows = table.find_all('tr')[:3]
            print(f"  Sample rows:")
            for j, row in enumerate(rows):
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text().strip() for cell in cells]
                print(f"    Row {j+1}: {cell_texts}")
            
            print("-" * 50)
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_nfl_parsing()
