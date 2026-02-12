import os
import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()                           # reads .env file
api_key = os.getenv("EBIRD_API_KEY")

if not api_key:
    raise ValueError("EBIRD_API_KEY not found! Check that .env exists and contains EBIRD_API_KEY=yourkey")
# ──────────────────────────────────────────────────────────────

headers = {
    "X-eBirdApiToken": api_key
}

url = "https://api.ebird.org/v2/data/obs/ZA/recent"   # ZA = South Africa

response = requests.get(url, headers=headers)

if response.status_code != 200:
    print("Error:", response.status_code, response.text)
    exit(1)

data = response.json()
df = pd.DataFrame(data)

print(f"Got {len(df)} recent observations")
print(df.head())
print(df.head().shape)
print(df.iloc[0])
