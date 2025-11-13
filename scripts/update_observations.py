"""
update_observations.py
Fetches recent eBird observations for South African regions
and upserts them into the Postgres 'observations' table.

Designed for automated weekly runs (e.g., via GitHub Actions).
"""

import os
import time
import requests
import pandas as pd
import sqlalchemy

load_dotenv()

API_KEY = os.getenv("EBIRD_API_KEY")
DB_URL = os.getenv("DB_URL")

REGIONS = [
    "ZA-WC", "ZA-GP", "ZA-MP", "ZA-LP", "ZA-NW",
    "ZA-KZ", "ZA-EC", "ZA-FS", "ZA-NC"
]
DAYS_BACK = 7  # how many days back to fetch
RETRY_DELAY = 5  # seconds between retries
MAX_RETRIES = 3

engine = sqlalchemy.create_engine(DB_URL, pool_pre_ping=True)

def fetch_observations(region: str) -> pd.DataFrame:
    """Fetch recent observations for one region from eBird API."""
    url = f"https://api.ebird.org/v2/data/obs/{region}/recent"
    params = {"back": DAYS_BACK}
    headers = {"X-eBirdApiToken": API_KEY}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            df = pd.DataFrame(data)
            if not df.empty:
                df["region"] = region
            return df
        except Exception as e:
            print(f"[WARN] Attempt {attempt}/{MAX_RETRIES} failed for {region}: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)
            else:
                print(f"[ERROR] Skipping region {region} after repeated failures.")
                return pd.DataFrame()


def insert_observations(df: pd.DataFrame):
    """Insert or skip existing observations (idempotent)."""
    if df.empty:
        print("No new data to insert.")
        return

    insert_sql = """
        INSERT INTO observations 
        (sub_id, species_code, com_name, loc_name, lat, lng, obs_dt, how_many, region)
        VALUES (:sub_id, :species_code, :com_name, :loc_name, :lat, :lng, :obs_dt, :how_many, :region)
        ON CONFLICT (sub_id) DO NOTHING
    """

    with engine.begin() as conn:
        conn.execute(sqlalchemy.text(insert_sql), df.to_dict(orient="records"))
    print(f"Inserted {len(df)} new rows (duplicates ignored).")

def main():
    print("=== Weekly eBird Observations ETL ===")
    all_data = []

    for region in REGIONS:
        print(f"Fetching region {region}...")
        df = fetch_observations(region)
        if not df.empty:
            all_data.append(df)

    if not all_data:
        print("No data fetched from any region.")
        return

    df = pd.concat(all_data, ignore_index=True)

    expected_cols = [
        "subId", "speciesCode", "comName", "locName",
        "lat", "lng", "obsDt", "howMany", "region"
    ]
    df = df[[c for c in expected_cols if c in df.columns]].copy()

    df.columns = [
        "sub_id", "species_code", "com_name", "loc_name",
        "lat", "lng", "obs_dt", "how_many", "region"
    ]

    # Clean up
    df["obs_dt"] = pd.to_datetime(df["obs_dt"], errors="coerce")
    df["obs_dt"] = df["obs_dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["how_many"] = df["how_many"].fillna(0).astype(int)
    df = df.drop_duplicates(subset=["sub_id"])

    print(f"Fetched {len(df)} total unique observations.")
    insert_observations(df)

    print("ETL completed successfully.")


if __name__ == "__main__":
    main()

