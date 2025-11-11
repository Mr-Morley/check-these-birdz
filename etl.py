import pandas as pd
import requests
import sqlite3
import yaml
from datetime import datetime, timedelta

def load_config(config_file):
    with open(config_file) as f:
        config = yaml.safe_load(f)
    return config

def fetch_ebird_data(region_code, api_key, date_range_days):
    base_url = "https://api.ebird.org/v2"
    sightings_url = f"{base_url}/data/obs/{region_code}/recent"
    hotspots_url = f"{base_url}/ref/hotspot/{region_code}"
    
    headers = {"X-eBirdApiToken": api_key}
    params = {'back': date_range_days}
    
    response_sightings = requests.get(sightings_url, headers=headers, params=params)
    if response_sightings.status_code != 200:
        print("Error fetching sightings")
        return None
    
    response_hotspots = requests.get(hotspots_url, headers=headers)
    if response_hotspots.status_code != 200:
        print("Error fetching hotspots")
        return None
    
    sightings = response_sightings.json()
    hotspots = response_hotspots.json()
    
    df_sightings = pd.DataFrame(sightings)
    df_hotspots = pd.DataFrame(hotspots)
    df = pd.merge(df_sightings, df_hotspots, how='left', on='locId')
    df['region'] = region_code
    return df

def main_etl():
    config = load_config('config.yaml')
    api_key = "YOUR_KEY"  # Replace
    conn = sqlite3.connect('data.db')
    
    for i in range(len(config['regions'])):
        reg = config['regions'][i]
        df = fetch_ebird_data(reg['code'], api_key, config['date_range_days'])
        if df is not None:
            df.to_sql('bird_data', conn, if_exists='append', index=False)
    
    conn.close()

if __name__ == "__main__":
    main_etl()
