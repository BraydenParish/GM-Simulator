#!/usr/bin/env python3
"""
Test the fixed NFL.com scraper with one team
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
from typing import Dict, List

def clean_name(name: str) -> str:
    """Clean player name"""
    name = re.sub(r'\s+[IV]+$', '', name)  # Remove Roman numerals
    name = re.sub(r'\s+[A-Z]\.$', '', name)  # Remove single letter suffixes
    return name.strip()

def parse_height(height_str: str) -> int:
    """Convert height from '76' format to inches"""
    if not height_str or height_str == '-':
        return 0
    try:
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

def test_dallas_cowboys():
    """Test parsing Dallas Cowboys roster"""
    url = "https://www.nfl.com/teams/dallas-cowboys/roster/"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        print(f"Status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"Error: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find roster table
        table = soup.find('table', {'class': 'd3-o-table'})
        if not table:
            print("No roster table found")
            return []
        
        players = []
        rows = table.find('tbody').find_all('tr') if table.find('tbody') else table.find_all('tr')
        
        print(f"Found {len(rows)} player rows")
        
        for i, row in enumerate(rows):
            cells = row.find_all(['td', 'th'])
            if len(cells) < 6:
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
                
                # Estimate age from experience
                exp_years = parse_age(experience) if experience else 0
                age = 22 + exp_years if exp_years > 0 else 25
                
                # Skip if essential data is missing
                if not name or not pos:
                    continue
                
                player = {
                    'name': name,
                    'pos': pos,
                    'team_id': 9,  # Dallas Cowboys
                    'age': age,
                    'height': height,
                    'weight': weight,
                    'jersey_no': jersey_no,
                    'status': status,
                    'experience': exp_years
                }
                
                players.append(player)
                
                # Show first 10 players
                if i < 10:
                    print(f"  {i+1}. {name} - {pos} - Age: {age} - {height}\" - {weight}lbs - Exp: {exp_years} - Status: {status}")
                
            except Exception as e:
                print(f"  Error parsing player {i+1}: {e}")
                continue
        
        print(f"\nSuccessfully parsed {len(players)} players")
        return players
        
    except Exception as e:
        print(f"Error: {e}")
        return []

def main():
    """Test the fixed scraper"""
    print("Testing fixed NFL.com scraper with Dallas Cowboys...")
    print("=" * 60)
    
    players = test_dallas_cowboys()
    
    if players:
        print(f"\n✅ SUCCESS! Found {len(players)} players")
        
        # Show position distribution
        pos_counts = {}
        for player in players:
            pos = player['pos']
            pos_counts[pos] = pos_counts.get(pos, 0) + 1
        
        print("\nPosition distribution:")
        for pos, count in sorted(pos_counts.items()):
            print(f"  {pos}: {count}")
        
        # Save test data
        df = pd.DataFrame(players)
        df.to_csv('test_dallas_fixed.csv', index=False)
        print(f"\nSaved test data to test_dallas_fixed.csv")
        
    else:
        print("❌ FAILED - No players found")

if __name__ == "__main__":
    main()
