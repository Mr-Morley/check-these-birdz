import pandas as pd
import requests
import sqlite3
import yaml
from datetime import datetime, timedelta
import io
def load_config(config_file):
    with open(config_file) as f:
        config = yaml.safe_load(f)
    return config

def fetch_ebird_data(region_code, api_key, date_range_days):
    base_url = "https://api.ebird.org/v2"
    sightings_url = f"{base_url}/data/obs/{region_code}/recent/notable"
    headers = {"X-eBirdApiToken": api_key}
    params = {'back': date_range_days}
    resp = requests.get(sightings_url, headers=headers, params=params)
    if resp.status_code != 200:
        print("Error:", resp.status_code, resp.text)
        return None
    data = resp.json()
    df = pd.DataFrame(data)
    cols = ['comName', 'locName', 'lat', 'lng', 'obsDt', 'howMany', 'reviewStatus', 'region']
    df = df.reindex(columns=cols, fill_value=pd.NA)
    df['region'] = region_code
    return df

def main_etl():
    config = load_config('config.yaml')
    api_key = "qrs70k0spauh"  
    conn = sqlite3.connect('data.db')
    
    for i in range(len(config['regions'])):
        reg = config['regions'][i]
        df = fetch_ebird_data(reg['code'], api_key, config['date_range_days'])
        if df is not None:
            df.to_sql('bird_data', conn, if_exists='append', index=False)
    
    conn.close()

if __name__ == "__main__":
    main_etl()
