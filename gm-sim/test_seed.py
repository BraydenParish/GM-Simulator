#!/usr/bin/env python3
"""
Test script to debug the seed process
"""

import asyncio
import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def check_imports():
    """Test if we can import all the required modules"""
    try:
        print("Testing imports...")
        from app.db import engine, AsyncSessionLocal
        print("✅ Database imports successful")
        
        from app.models import Team, Player, Contract, DepthChart, DraftPick
        print("✅ Model imports successful")
        
        return True
    except Exception as e:
        print(f"❌ Import error: {e}")
        return False

async def check_database_connection():
    """Test database connection"""
    try:
        print("Testing database connection...")
        from app.db import engine, AsyncSessionLocal
        
        async with engine.begin() as conn:
            print("✅ Database connection successful")
            return True
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

async def check_csv_files():
    """Test if CSV files exist and are readable"""
    try:
        print("Testing CSV files...")
        data_dir = os.path.join(os.path.dirname(__file__), "data", "seed")
        
        csv_files = ["teams.csv", "players.csv", "contracts.csv", "depth_chart.csv", "picks.csv"]
        
        for csv_file in csv_files:
            file_path = os.path.join(data_dir, csv_file)
            if os.path.exists(file_path):
                print(f"✅ {csv_file} exists")
            else:
                print(f"❌ {csv_file} missing")
                return False
                
        return True
    except Exception as e:
        print(f"❌ CSV file error: {e}")
        return False

async def main():
    print("=== Testing Seed Script Components ===")
    
    # Test imports
    if not await check_imports():
        return
    
    # Test database connection
    if not await check_database_connection():
        return
    
    # Test CSV files
    if not await check_csv_files():
        return
    
    print("\n✅ All tests passed! The seed script should work.")
    print("Try running: python -m app.seed")

if __name__ == "__main__":
    asyncio.run(main())
