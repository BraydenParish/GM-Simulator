#!/usr/bin/env python3
"""
Alternative NFL roster scraper - try different sources
"""

import pandas as pd
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import Dict, List

def test_nfl_com():
    """Test NFL.com roster scraping"""
    print("Testing NFL.com...")
    url = "https://www.nfl.com/teams/dallas-cowboys/roster/"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"NFL.com Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ NFL.com accessible!")
            return True
        else:
            print(f"❌ NFL.com error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ NFL.com error: {e}")
        return False

def test_ourlads():
    """Test OurLads depth chart scraping"""
    print("Testing OurLads...")
    url = "https://www.ourlads.com/nfldepthcharts/roster/28/2024"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"OurLads Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ OurLads accessible!")
            return True
        else:
            print(f"❌ OurLads error: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ OurLads error: {e}")
        return False

def create_sample_data():
    """Create sample data for testing the simulator"""
    print("Creating sample player data...")
    
    # Sample players for testing
    sample_players = [
        {
            'id': 1, 'name': 'Dak Prescott', 'pos': 'QB', 'team_id': 9, 'age': 31, 'height': 75, 'weight': 238,
            'ovr': 88, 'pot': 90, 'spd': 78, 'acc': 82, 'agi': 80, 'str': 75, 'awr': 92,
            'injury_status': 'OK', 'morale': 85, 'stamina': 90,
            'thp': 92, 'tha_s': 90, 'tha_m': 88, 'tha_d': 85, 'tup': 88,
            'rel': 0, 'rr': 0, 'cth': 0, 'cit': 0,
            'pbk': 0, 'rbk': 0, 'iblk': 0, 'oblk': 0,
            'mcv': 0, 'zcv': 0, 'prs': 0,
            'pmv': 0, 'fmv': 0, 'bsh': 0, 'purs': 0
        },
        {
            'id': 2, 'name': 'CeeDee Lamb', 'pos': 'WR', 'team_id': 9, 'age': 25, 'height': 74, 'weight': 200,
            'ovr': 92, 'pot': 95, 'spd': 89, 'acc': 91, 'agi': 93, 'str': 70, 'awr': 88,
            'injury_status': 'OK', 'morale': 90, 'stamina': 88,
            'thp': 0, 'tha_s': 0, 'tha_m': 0, 'tha_d': 0, 'tup': 0,
            'rel': 90, 'rr': 94, 'cth': 92, 'cit': 89,
            'pbk': 0, 'rbk': 0, 'iblk': 0, 'oblk': 0,
            'mcv': 0, 'zcv': 0, 'prs': 0,
            'pmv': 0, 'fmv': 0, 'bsh': 0, 'purs': 0
        },
        {
            'id': 3, 'name': 'Micah Parsons', 'pos': 'EDGE', 'team_id': 9, 'age': 25, 'height': 75, 'weight': 245,
            'ovr': 95, 'pot': 98, 'spd': 88, 'acc': 92, 'agi': 90, 'str': 85, 'awr': 89,
            'injury_status': 'OK', 'morale': 88, 'stamina': 92,
            'thp': 0, 'tha_s': 0, 'tha_m': 0, 'tha_d': 0, 'tup': 0,
            'rel': 0, 'rr': 0, 'cth': 0, 'cit': 0,
            'pbk': 0, 'rbk': 0, 'iblk': 0, 'oblk': 0,
            'mcv': 0, 'zcv': 0, 'prs': 0,
            'pmv': 98, 'fmv': 95, 'bsh': 88, 'purs': 92
        },
        {
            'id': 4, 'name': 'Trevon Diggs', 'pos': 'CB', 'team_id': 9, 'age': 26, 'height': 74, 'weight': 195,
            'ovr': 89, 'pot': 92, 'spd': 91, 'acc': 93, 'agi': 92, 'str': 70, 'awr': 87,
            'injury_status': 'OK', 'morale': 85, 'stamina': 90,
            'thp': 0, 'tha_s': 0, 'tha_m': 0, 'tha_d': 0, 'tup': 0,
            'rel': 0, 'rr': 0, 'cth': 0, 'cit': 0,
            'pbk': 0, 'rbk': 0, 'iblk': 0, 'oblk': 0,
            'mcv': 92, 'zcv': 88, 'prs': 85,
            'pmv': 0, 'fmv': 0, 'bsh': 0, 'purs': 0
        },
        {
            'id': 5, 'name': 'Zack Martin', 'pos': 'IOL', 'team_id': 9, 'age': 33, 'height': 76, 'weight': 315,
            'ovr': 94, 'pot': 94, 'spd': 65, 'acc': 68, 'agi': 70, 'str': 95, 'awr': 96,
            'injury_status': 'OK', 'morale': 90, 'stamina': 88,
            'thp': 0, 'tha_s': 0, 'tha_m': 0, 'tha_d': 0, 'tup': 0,
            'rel': 0, 'rr': 0, 'cth': 0, 'cit': 0,
            'pbk': 98, 'rbk': 96, 'iblk': 97, 'oblk': 95,
            'mcv': 0, 'zcv': 0, 'prs': 0,
            'pmv': 0, 'fmv': 0, 'bsh': 0, 'purs': 0
        }
    ]
    
    # Convert to DataFrame and save
    df = pd.DataFrame(sample_players)
    df.to_csv('data/seed/players_sample.csv', index=False)
    print(f"✅ Created sample data with {len(sample_players)} players")
    print("Sample players:")
    for player in sample_players:
        print(f"  - {player['name']} ({player['pos']}) - OVR: {player['ovr']}")
    
    return True

def main():
    """Test different data sources"""
    print("Testing alternative NFL data sources...")
    print("=" * 50)
    
    # Test different sources
    nfl_works = test_nfl_com()
    ourlads_works = test_ourlads()
    
    print("\n" + "=" * 50)
    print("RESULTS:")
    print(f"NFL.com: {'✅ Works' if nfl_works else '❌ Blocked'}")
    print(f"OurLads: {'✅ Works' if ourlads_works else '❌ Blocked'}")
    
    if not nfl_works and not ourlads_works:
        print("\n🚨 All scraping sources are blocked!")
        print("📝 RECOMMENDATION: Use sample data to test the simulator")
        print("\nCreating sample data...")
        create_sample_data()
        print("\n✅ Sample data created! You can now test the simulator.")
        print("   - Copy 'players_sample.csv' to 'players.csv'")
        print("   - Run 'make seed' to load the data")
    else:
        print("\n✅ At least one source works! We can proceed with scraping.")

if __name__ == "__main__":
    main()
