import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in .env file")
    exit(1)

print("Connecting to Supabase...")
engine = create_engine(DATABASE_URL)

with engine.connect() as conn:
    # 1. Basic connection test
    result = conn.execute(text("SELECT 1"))
    print(f"1. Basic connection:  OK")

    # 2. Check PostGIS extension
    result = conn.execute(text("SELECT PostGIS_Version();"))
    print(f"2. PostGIS version:   {result.scalar()}")

    # 3. Check current database and user
    result = conn.execute(text("SELECT current_database(), current_user;"))
    db, user = result.fetchone()
    print(f"3. Database: {db}, User: {user}")

print("\nAll checks passed! You're connected to Supabase.")