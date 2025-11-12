import os
import requests
import pandas as pd
import wikipediaapi
import sqlalchemy
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()
API_KEY = os.getenv("EBIRD_API_KEY")
IUCN_TOKEN = os.getenv("IUCN_API_TOKEN")
DB_URL = os.getenv("DB_URL")

TAXONOMY_URL = "https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json"
IUCN_API_URL = "https://apiv3.iucnredlist.org/api/v3/species"

wiki = wikipediaapi.Wikipedia(language="en", user_agent="check-these-birdz")

print("Getting species...")
r = requests.get(TAXONOMY_URL, headers={"X-eBirdApiToken": API_KEY}, timeout=30)
species = [t for t in r.json() if t.get("category") == "species"]
print(f"{len(species)} species found")

records = []
for species in tqdm(species):
    sci_name = species.get("sciName")
    
    wiki_url = None
    try:
        page = wiki.page(sci_name)
        if page.exists():
            wiki_url = page.fullurl
    except:
        pass
    
    iucn_category = None
    population_trend = None
    if IUCN_TOKEN:
        try:
            url = f"{IUCN_API_URL}/{sci_name.replace(' ', '%20')}"
            iucn_r = requests.get(url, params={"token": IUCN_TOKEN}, timeout=10)
            if iucn_r.status_code == 200:
                data = iucn_r.json()
                if data.get("result"):
                    iucn_category = data["result"][0].get("category")
                    population_trend = data["result"][0].get("population_trend")
        except:
            pass
    
    records.append({
        "speciesCode": sp.get("speciesCode"),
        "comName": sp.get("comName"),
        "sciName": sci_name,
        "wikipedia_url": wiki_url,
        "iucn_category": iucn_category,
        "population_trend": population_trend
    })

df = pd.DataFrame(records)
print(f"Saving {len(df)} to DB...")

engine = sqlalchemy.create_engine(DB_URL)
with engine.begin() as conn:
    conn.execute(sqlalchemy.text("DROP TABLE IF EXISTS species"))
    conn.execute(sqlalchemy.text("""
        CREATE TABLE species (
            "speciesCode" VARCHAR(12) PRIMARY KEY,
            "comName" TEXT,
            "sciName" TEXT,
            "wikipedia_url" TEXT,
            "iucn_category" VARCHAR(2),
            "population_trend" VARCHAR(20)
        )
    """))
    df.to_sql("species", conn, if_exists="append", index=False, chunksize=5000)

print("Done")