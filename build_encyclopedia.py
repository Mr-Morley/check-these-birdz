import os
import time
import requests
import pandas as pd
import wikipediaapi
import sqlalchemy
from dotenv import load_dotenv
from tqdm import tqdm

# --- 1. CONFIGURATION ---
print("Starting Pillar 1: Build Encyclopedia...")

# Load environment variables from .env file
load_dotenv()
API_KEY = os.getenv("EBIRD_API_KEY")
DB_URL = os.getenv("DB_URL")
REGION_CODE = "ZA" 

# Setup for Wikipedia API
wiki_wiki = wikipediaapi.Wikipedia(
    language='en',
    user_agent="check-these-birdz (my-project)" # Good practice
)
# Setup for eBird API
ebird_headers = {'X-eBirdApiToken': API_KEY}


def fetch_wikipedia_url(sci_name: str) -> str | None:
    """Fetches a Wikipedia URL for a given scientific name."""
    try:
        page = wiki_wiki.page(sci_name)
        if page.exists():
            return page.fullurl
    except Exception as e:
        print(f"  Warning: Error fetching wiki for {sci_name}: {e}")
    return None

def main():
    """Main ETL function to build the species 'encyclopedia' table."""
    
    if not API_KEY or not DB_URL:
        print("Please check your .env file and add your credentials.")
        return

    #  1. EXTRACT 
    print(f"Fetching full species list for region: {REGION_CODE}...")
    try:
        spplist_url = f"https://api.eBird.org/v2/product/spplist/{REGION_CODE}"
        response = requests.get(spplist_url, headers=ebird_headers)
        response.raise_for_status()  # This will raise an error if the request failed
        all_species_codes = response.json()
        print(f"Found {len(all_species_codes)} total species codes.")
    except Exception as e:
        print(f"ERROR: Failed to get species list from eBird. Check API key?")
        print(f"Details: {e}")
        return

    #  2. TRANSFORM ---
    print("Batch-fetching taxonomy and enriching with Wikipedia...")
    batch_size = 100 
    all_species_data = []
    for i in tqdm(range(0, len(all_species_codes), batch_size), desc="Enriching Species"):
        
        batch_codes = all_species_codes[i:i + batch_size]
        species_param = ",".join(batch_codes)
        
        # Call the taxonomy API for the batch
        tax_url = f"https://api.eBird.org/v2/ref/taxonomy/ebird?species={species_param}&fmt=json"
        
        try:
            tax_response = requests.get(tax_url, headers=ebird_headers)
            tax_response.raise_for_status()
            batch_data = tax_response.json()
        except Exception as e:
            print(f"\nWarning: Failed to fetch taxonomy for batch {i}. {e}")
            continue # Skip this batch if it fails

        # Enrich this batch with Wikipedia data
        for species in batch_data:
            if species.get('category') == 'species':
                sci_name = species.get('sciName')
                wiki_url = fetch_wikipedia_url(sci_name)
                
                all_species_data.append({
                    'speciesCode': species.get('speciesCode'),
                    'comName': species.get('comName'),
                    'sciName': sci_name,
                    'wikipedia_url': wiki_url
                })
        
        time.sleep(0.5) 

    species_df = pd.DataFrame(all_species_data)
    print(f"Successfully scraped {len(species_df)} species.")


    #  3. LOAD 
    print("Connecting to PostgreSQL and loading data...")
    try:
        engine = sqlalchemy.create_engine(DB_URL)
        with engine.connect() as conn:
            species_df.to_sql(
                'species', 
                conn, 
                if_exists='replace', 
                index=False,
                dtype={
                    'speciesCode': sqlalchemy.types.String(10),
                    'comName': sqlalchemy.types.Text(),
                    'sciName': sqlalchemy.types.Text(),
                    'wikipedia_url': sqlalchemy.types.Text()
                }
            )
            
            print("Setting Primary Key...")
            conn.execute(sqlalchemy.text('ALTER TABLE species ADD PRIMARY KEY ("speciesCode");'))
            
        print("--- 🏁 PILLAR 1 COMPLETE! ---")
        print("Your 'species' table is built. Go check pgAdmin!")

    except Exception as e:
        print(f"Please check your DB_URL in .env and that Docker is running.")
        print(f"Details: {e}")

if __name__ == "__main__":
    main()