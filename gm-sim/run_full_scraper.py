#!/usr/bin/env python3
"""
Run the full NFL scraper for all 32 teams
"""

import subprocess
import sys
import time
import os

def run_scraper():
    """Run the NFL scraper for all teams"""
    print("Starting full NFL roster scraper for all 32 teams...")
    print("=" * 60)
    
    # Get the directory where this script is located
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    os.chdir(BASE_DIR)
    
    try:
        # Run the scraper
        result = subprocess.run([sys.executable, 'scrape_nfl_quick.py'], 
                              capture_output=True, text=True, timeout=600)
        
        print("Scraper output:")
        print(result.stdout)
        
        if result.stderr:
            print("Errors:")
            print(result.stderr)
        
        if result.returncode == 0:
            print("\n✅ Scraper completed successfully!")
            
            # Check if the file was created
            if os.path.exists('data/seed/players_nfl.csv'):
                file_size = os.path.getsize('data/seed/players_nfl.csv')
                print(f"📁 File created: data/seed/players_nfl.csv ({file_size} bytes)")
            else:
                print("❌ Output file not found")
        else:
            print(f"❌ Scraper failed with return code: {result.returncode}")
            
    except subprocess.TimeoutExpired:
        print("⏰ Scraper timed out after 10 minutes")
    except Exception as e:
        print(f"❌ Error running scraper: {e}")

if __name__ == "__main__":
    run_scraper()
