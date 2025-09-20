#!/usr/bin/env python3
"""
NFL.com Roster Scraper
Scrapes all 32 NFL team rosters from NFL.com
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import Dict, List
import json

# NFL.com team URLs and their corresponding team IDs
TEAMS = {
    'arizona-cardinals': 1, 'atlanta-falcons': 2, 'baltimore-ravens': 3, 'buffalo-bills': 4,
    'carolina-panthers': 5, 'chicago-bears': 6, 'cincinnati-bengals': 7, 'cleveland-browns': 8,
    'dallas-cowboys': 9, 'denver-broncos': 10, 'detroit-lions': 11, 'green-bay-packers': 12,
    'houston-texans': 13, 'indianapolis-colts': 14, 'jacksonville-jaguars': 15, 'kansas-city-chiefs': 16,
    'las-vegas-raiders': 17, 'los-angeles-chargers': 18, 'los-angeles-rams': 19, 'miami-dolphins': 20,
    'minnesota-vikings': 21, 'new-england-patriots': 22, 'new-orleans-saints': 23, 'new-york-giants': 24,
    'new-york-jets': 25, 'philadelphia-eagles': 26, 'pittsburgh-steelers': 27, 'san-francisco-49ers': 28,
    'seattle-seahawks': 29, 'tampa-bay-buccaneers': 30, 'tennessee-titans': 31, 'washington-commanders': 32
}

def clean_name(name: str) -> str:
    """Clean player name"""
    name = re.sub(r'\s+[IV]+$', '', name)  # Remove Roman numerals
    name = re.sub(r'\s+[A-Z]\.$', '', name)  # Remove single letter suffixes
    return name.strip()

def parse_height(height_str: str) -> int:
    """Convert height to inches - NFL.com gives us inches directly"""
    if not height_str or height_str == '-':
        return 0
    try:
        # NFL.com gives us height in inches directly (e.g., "76")
        return int(height_str)
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

def scrape_nfl_roster(team_slug: str, team_id: int) -> List[Dict]:
    """Scrape a single team's roster from NFL.com"""
    url = f"https://www.nfl.com/teams/{team_slug}/roster/"
    
    print(f"Scraping {team_slug}...")
    
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
        print(f"  Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"  Error: Got status code {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find roster table - NFL.com uses different structure
        table = soup.find('table', {'class': 'd3-o-table'})
        if not table:
            # Try alternative table selectors
            table = soup.find('table', {'class': 'nfl-o-roster'})
            if not table:
                table = soup.find('table')
        
        if not table:
            print("  No roster table found")
            return []
        
        players = []
        rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
        
        print(f"  Found {len(rows)} player rows")
        
        for i, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            if len(cells) < 6:  # Need at least 6 columns
                continue
                
            try:
                # NFL.com format: Player, No, Pos, Status, Height, Weight, Experience, College
                name_cell = cells[0].find('a') or cells[0]
                if not name_cell:
                    continue
                    
                name = clean_name(name_cell.get_text().strip())
                
                # Skip header row
                if name.lower() in ['player', 'name']:
                    continue
                
                # Extract data from correct columns
                jersey_no = cells[1].get_text().strip()
                pos = cells[2].get_text().strip()
                status = cells[3].get_text().strip()
                height_str = cells[4].get_text().strip()
                weight_str = cells[5].get_text().strip()
                experience = cells[6].get_text().strip()
                
                # Parse height and weight
                height = parse_height(height_str) if height_str else 0
                weight = parse_weight(weight_str) if weight_str else 0
                
                # Estimate age from experience (rough approximation)
                # Most players start at 22-23, so age = 22 + experience
                exp_years = parse_age(experience) if experience else 0
                age = 22 + exp_years if exp_years > 0 else 25  # Default to 25 if no experience data
                
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
                    'ovr': 0,  # Placeholder - will need to add manually
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
                
                if i < 5:  # Show first 5 players
                    print(f"    {i+1}. {name} - {pos} - Age: {age} - {height}\" - {weight}lbs - Exp: {exp_years}")
                
            except Exception as e:
                print(f"    Error parsing player {i+1}: {e}")
                continue
        
        print(f"  Successfully parsed {len(players)} players")
        return players
        
    except Exception as e:
        print(f"  Error scraping {team_slug}: {e}")
        return []

def main():
    """Main scraping function"""
    print("Starting NFL.com roster scrape...")
    print("=" * 50)
    
    all_players = []
    player_id = 1
    
    for team_slug, team_id in TEAMS.items():
        players = scrape_nfl_roster(team_slug, team_id)
        
        # Add unique IDs to players
        for player in players:
            player['id'] = player_id
            player_id += 1
        
        all_players.extend(players)
        
        # Be nice to NFL.com's servers
        time.sleep(2)
    
    print("=" * 50)
    print(f"Total players scraped: {len(all_players)}")
    
    if all_players:
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
        output_file = 'data/seed/players_nfl.csv'
        df.to_csv(output_file, index=False)
        print(f"Saved to {output_file}")
        
        # Show sample of data
        print("\nSample of scraped data:")
        print(df[['id', 'name', 'pos', 'team_id', 'age', 'height', 'weight']].head(10))
        
        # Show position distribution
        print(f"\nPosition distribution:")
        print(df['pos'].value_counts())
        
        print("\n✅ Scraping complete! Next steps:")
        print("1. Review the data in players_nfl.csv")
        print("2. Add ratings (OVR, speed, etc.) manually or from Madden data")
        print("3. Rename to players.csv when ready")
        print("4. Run 'make seed' to load into simulator")
    else:
        print("❌ No players found. Check the scraping logic.")

if __name__ == "__main__":
    main()
