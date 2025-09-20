#!/usr/bin/env python3
"""
Debug height parsing issue
"""

import requests
from bs4 import BeautifulSoup

def debug_height_parsing():
    """Debug height parsing for different teams"""
    teams = [
        ('dallas-cowboys', 'Dallas Cowboys'),
        ('arizona-cardinals', 'Arizona Cardinals'),
        ('atlanta-falcons', 'Atlanta Falcons')
    ]
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for team_slug, team_name in teams:
        print(f"\n=== {team_name} ===")
        url = f"https://www.nfl.com/teams/{team_slug}/roster/"
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            print(f"Status: {response.status_code}")
            
            if response.status_code != 200:
                print(f"Error: {response.status_code}")
                continue
            
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table', {'class': 'd3-o-table'})
            
            if not table:
                print("No table found")
                continue
            
            rows = table.find_all('tr')[1:4]  # Skip header, get first 3 data rows
            
            for i, row in enumerate(rows):
                cells = row.find_all('td')
                if len(cells) >= 6:
                    name = cells[0].get_text().strip()
                    jersey = cells[1].get_text().strip()
                    pos = cells[2].get_text().strip()
                    status = cells[3].get_text().strip()
                    height = cells[4].get_text().strip()
                    weight = cells[5].get_text().strip()
                    exp = cells[6].get_text().strip()
                    
                    print(f"  Row {i+1}: {name} | {jersey} | {pos} | {status} | Height: '{height}' | Weight: '{weight}' | Exp: '{exp}'")
                    
                    # Test height parsing
                    try:
                        height_int = int(height) if height else 0
                        print(f"    Height parsed as: {height_int}")
                    except:
                        print(f"    Height parsing failed: '{height}'")
            
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    debug_height_parsing()
