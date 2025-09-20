#!/usr/bin/env python3
"""
ESPN NFL Roster Scraper
Scrapes all 32 NFL team rosters from ESPN and exports to CSV
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import Dict, List
import csv

# ESPN team abbreviations and their corresponding team IDs
TEAMS = {
    'ARI': 1, 'ATL': 2, 'BAL': 3, 'BUF': 4, 'CAR': 5, 'CHI': 6,
    'CIN': 7, 'CLE': 8, 'DAL': 9, 'DEN': 10, 'DET': 11, 'GB': 12,
    'HOU': 13, 'IND': 14, 'JAX': 15, 'KC': 16, 'LV': 17, 'LAC': 18,
    'LAR': 19, 'MIA': 20, 'MIN': 21, 'NE': 22, 'NO': 23, 'NYG': 24,
    'NYJ': 25, 'PHI': 26, 'PIT': 27, 'SF': 28, 'SEA': 29, 'TB': 30,
    'TEN': 31, 'WAS': 32
}

def clean_name(name: str) -> str:
    """Clean player name from ESPN format"""
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
    if not age_str or age_str == '-':
        return 0
    try:
        return int(re.sub(r'[^\d]', '', age_str))
    except:
        return 0

def scrape_team_roster(team_abbr: str, team_id: int) -> List[Dict]:
    """Scrape a single team's roster from ESPN"""
    url = f"https://www.espn.com/nfl/team/roster/_/name/{team_abbr.lower()}"
    
    print(f"Scraping {team_abbr}...")
    
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
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find the roster table
        table = soup.find('table', class_='Table')
        if not table:
            print(f"  No roster table found for {team_abbr}")
            return []
        
        players = []
        rows = table.find('tbody').find_all('tr')
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 6:
                continue
                
            try:
                # Extract player data from table cells
                name_cell = cells[0].find('a')
                if not name_cell:
                    continue
                    
                name = clean_name(name_cell.get_text().strip())
                pos = cells[1].get_text().strip()
                age = parse_age(cells[2].get_text().strip())
                height = parse_height(cells[3].get_text().strip())
                weight = parse_weight(cells[4].get_text().strip())
                
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
                    'ovr': 0,  # Placeholder - will need to fill manually
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
                
            except Exception as e:
                print(f"  Error parsing player in {team_abbr}: {e}")
                continue
        
        print(f"  Found {len(players)} players for {team_abbr}")
        return players
        
    except Exception as e:
        print(f"  Error scraping {team_abbr}: {e}")
        return []

def main():
    """Main scraping function"""
    print("Starting ESPN NFL roster scrape...")
    print("=" * 50)
    
    all_players = []
    player_id = 1
    
    for team_abbr, team_id in TEAMS.items():
        players = scrape_team_roster(team_abbr, team_id)
        
        # Add unique IDs to players
        for player in players:
            player['id'] = player_id
            player_id += 1
        
        all_players.extend(players)
        
        # Be nice to ESPN's servers (longer delay to avoid rate limiting)
        time.sleep(2)
    
    print("=" * 50)
    print(f"Total players scraped: {len(all_players)}")
    
    # Convert to DataFrame and save
    df = pd.DataFrame(all_players)
    
    # Reorder columns to match the expected format
    columns = [
        'id', 'name', 'pos', 'team_id', 'age', 'height', 'weight',
        'ovr', 'pot', 'spd', 'acc', 'agi', 'str', 'awr',
        'injury_status', 'morale', 'stamina',
        'thp', 'tha_s', 'tha_m', 'tha_d', 'tup',
        'rel', 'rr', 'cth', 'cit',
        'pbk', 'rbk', 'iblk', 'oblk',
        'mcv', 'zcv', 'prs',
        'pmv', 'fmv', 'bsh', 'purs'
    ]
    
    df = df[columns]
    
    # Save to CSV
    output_file = 'data/seed/players_espn.csv'
    df.to_csv(output_file, index=False)
    print(f"Saved to {output_file}")
    
    # Show sample of data
    print("\nSample of scraped data:")
    print(df[['id', 'name', 'pos', 'team_id', 'age', 'height', 'weight']].head(10))
    
    # Show position distribution
    print(f"\nPosition distribution:")
    print(df['pos'].value_counts())
    
    print("\nScraping complete! Next steps:")
    print("1. Review the data in players_espn.csv")
    print("2. Add ratings (OVR, speed, etc.) manually or from Madden data")
    print("3. Rename to players.csv when ready")

if __name__ == "__main__":
    main()
