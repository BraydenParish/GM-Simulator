#!/usr/bin/env python3
"""
Test Pro Football Reference scraper for one team
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import Dict, List

def clean_name(name: str) -> str:
    """Clean player name from PFR format"""
    # Remove common suffixes and clean up
    name = re.sub(r'\s+[IV]+$', '', name)  # Remove Roman numerals
    name = re.sub(r'\s+[A-Z]\.$', '', name)  # Remove single letter suffixes
    return name.strip()

def parse_height(height_str: str) -> int:
    """Convert height from '6-2' format to inches"""
    if not height_str or height_str == '-':
        return 0
    try:
        feet, inches = height_str.split('-')
        return int(feet) * 12 + int(inches)
    except:
        return 0

def parse_weight(weight_str: str) -> int:
    """Convert weight string to integer"""
    if not weight_str or weight_str == '-':
        return 0
    try:
        return int(re.sub(r'[^\d]', '', weight_str))
    except:
        return 0

def parse_age(age_str: str) -> int:
    """Convert age string to integer"""
    if not age_str or weight_str == '-':
        return 0
    try:
        return int(re.sub(r'[^\d]', '', age_str))
    except:
        return 0

def scrape_pfr_roster(team_abbr: str, team_id: int) -> List[Dict]:
    """Scrape a single team's roster from Pro Football Reference"""
    # PFR uses lowercase team abbreviations and 2025 year
    team = team_abbr.lower()
    year = 2025
    url = f"https://www.pro-football-reference.com/teams/{team}/{year}_roster.htm"
    
    print(f"Scraping {team_abbr} from PFR...")
    print(f"URL: {url}")
    
    # Browser-like headers to avoid 403 errors
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: Got status code {response.status_code}")
            print(f"Response text preview: {response.text[:500]}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the roster table - PFR uses different class names
        table = soup.find('table', {'id': 'roster'})
        if not table:
            print("  No roster table found")
            return []
        
        players = []
        rows = table.find('tbody').find_all('tr')
        
        print(f"  Found {len(rows)} player rows")
        
        for i, row in enumerate(rows[:10]):  # Just first 10 for testing
            cells = row.find_all('td')
            if len(cells) < 6:
                continue
                
            try:
                # PFR roster format: number, name, pos, age, height, weight, college, etc.
                number = cells[0].get_text().strip()
                name_cell = cells[1].find('a')
                if not name_cell:
                    continue
                    
                name = clean_name(name_cell.get_text().strip())
                pos = cells[2].get_text().strip()
                age = parse_age(cells[3].get_text().strip())
                height = parse_height(cells[4].get_text().strip())
                weight = parse_weight(cells[5].get_text().strip())
                
                # Skip if essential data is missing
                if not name or not pos:
                    continue
                
                player = {
                    'name': name,
                    'pos': pos,
                    'team_id': team_id,
                    'age': age,
                    'height': height,
                    'weight': weight,
                    'number': number,
                    'ovr': 0,  # Placeholder
                    'pot': 0,  # Placeholder
                    'spd': 0,  # Placeholder
                    'acc': 0,  # Placeholder
                    'agi': 0,  # Placeholder
                    'str': 0,  # Placeholder
                    'awr': 0,  # Placeholder
                    'injury_status': 'OK',
                    'morale': 50,
                    'stamina': 80,
                    # Positional skills (all placeholders)
                    'thp': 0, 'tha_s': 0, 'tha_m': 0, 'tha_d': 0, 'tup': 0,
                    'rel': 0, 'rr': 0, 'cth': 0, 'cit': 0,
                    'pbk': 0, 'rbk': 0, 'iblk': 0, 'oblk': 0,
                    'mcv': 0, 'zcv': 0, 'prs': 0,
                    'pmv': 0, 'fmv': 0, 'bsh': 0, 'purs': 0
                }
                
                players.append(player)
                print(f"    {i+1}. {name} - {pos} - {age} - {height}\" - {weight}lbs")
                
            except Exception as e:
                print(f"    Error parsing player {i+1}: {e}")
                continue
        
        print(f"  Successfully parsed {len(players)} players")
        return players
        
    except Exception as e:
        print(f"  Error scraping {team_abbr}: {e}")
        return []

def main():
    """Test PFR scraper with one team"""
    print("Testing Pro Football Reference scraper...")
    print("=" * 50)
    
    # Test with Dallas Cowboys (DAL)
    team_abbr = "DAL"
    team_id = 9  # Dallas Cowboys ID from teams.csv
    
    players = scrape_pfr_roster(team_abbr, team_id)
    
    if players:
        print(f"\n✅ SUCCESS! Found {len(players)} players")
        print("\nSample data:")
        for i, player in enumerate(players[:5]):
            print(f"  {i+1}. {player['name']} - {player['pos']} - Age: {player['age']} - {player['height']}\" - {player['weight']}lbs")
        
        # Save test data
        df = pd.DataFrame(players)
        df.to_csv('test_pfr_dal.csv', index=False)
        print(f"\nSaved test data to test_pfr_dal.csv")
        
    else:
        print("❌ FAILED - No players found")
        print("\nPossible issues:")
        print("1. PFR changed their HTML structure")
        print("2. Team abbreviation is wrong")
        print("3. URL format is incorrect")

if __name__ == "__main__":
    main()
