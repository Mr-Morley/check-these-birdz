# scripts/update_observations.py
import os
import requests
import pandas as pd
import sqlalchemy
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("EBIRD_API_KEY")
DB_URL = os.getenv("DB_URL")

REGIONS = ['ZA-WC', 'ZA-GP', 'ZA-MP', 'ZA-LP', 'ZA-NW', 'ZA-KZ', 'ZA-EC', 'ZA-FS', 'ZA-NC']
DAYS_BACK = 7

engine = sqlalchemy.create_engine(DB_URL)

def fetch_observations(region):
    url = f"https://api.ebird.org/v2/data/obs/{region}/recent"
    r = requests.get(url, headers={"X-eBirdApiToken": API_KEY}, params={"back": DAYS_BACK})
    r.raise_for_status()
    df = pd.DataFrame(r.json())
    df['region'] = region
    return df

def main():
    print("Fetching observations from all regions...")
    all_df = pd.concat([fetch_observations(r) for r in REGIONS], ignore_index=True)
    
    cols = ['subId', 'speciesCode', 'comName', 'locName', 'lat', 'lng', 'obsDt', 'howMany', 'region']
    df = all_df[cols].copy()
    df.columns = ['sub_id', 'species_code', 'com_name', 'loc_name', 'lat', 'lng', 'obs_dt', 'how_many', 'region']
    
    df['obs_dt'] = pd.to_datetime(df['obs_dt'], format='mixed')
    df['obs_dt'] = df['obs_dt'].dt.strftime('%d-%m-%Y %H:%M')
    
    df['how_many'] = df['how_many'].fillna(0).astype(int)  # Fix NaN issue
    
    df = df.drop_duplicates(subset=['sub_id'])
    
    print(f"Inserting {len(df)} observations...")
    
    with engine.begin() as conn:
        for _, row in df.iterrows():
            conn.execute(sqlalchemy.text("""
                INSERT INTO observations (sub_id, species_code, com_name, loc_name, lat, lng, obs_dt, how_many, region)
                VALUES (:sub_id, :species_code, :com_name, :loc_name, :lat, :lng, :obs_dt, :how_many, :region)
                ON CONFLICT (sub_id) DO NOTHING
            """), row.to_dict())
    
    print("Done")

if __name__ == "__main__":
    main()