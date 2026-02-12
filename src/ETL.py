from sqlalchemy import create_engine, text
import requests
import pandas as pd
class ExtractTransformLoad:
    def __init__(self, api_key, db_url):
        self.headers={
            "X-eBirdApiToken": api_key
        }
        self.url="https://api.ebird.org/v2/data/obs/ZA/recent" 
        #database link
        self.db_url = db_url
        #SQL engine
        self.engine = create_engine(self.db_url)
        # Data from API and subsequent Tables
        self.data=None
        self.species_df=None
        self.obs_df=None

    def extract(self):
        response = requests.get(self.url, headers=self.headers)

        if response.status_code != 200:
            print("Error:", response.status_code, response.text)
            exit(1)

        self.data = response.json()
        print(f"Extracted data from {self.url}")

    def transform(self):
        df = pd.DataFrame(self.data)
        print("Transforming data")
        df.columns = [col.lower() for col in df.columns]
        text_cols = ['speciescode', 'comname', 'sciname', 'locname']
        for col in text_cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.lower()

        df['obsdt'] = pd.to_datetime(df['obsdt'])
        
        self.species_df = df[['speciescode', 'comname', 'sciname']].drop_duplicates()
        self.obs_df = df[['subid', 'speciescode', 'howmany', 'lat', 'lng', 'obsdt']]
        print(f"Standardized {len(self.obs_df)} observations and {len(self.species_df)} unique species.")

    def load(self):
        print(f"Loading data into PostgreSQL...")
        new_species = pd.DataFrame(self.species_df)
        with self.engine.connect() as conn:
            # Species Encyclopedia
            # Only get NEW species observed
            try:
                existing_species = pd.read_sql(text("SELECT speciescode FROM species"), conn)['speciescode'].tolist()
                new_species = self.species_df[~self.species_df['speciescode'].isin(existing_species)]
            except:
                existing_species = []


            # Observations 
            # Only get new sightings        
            query_obs = text("SELECT subid FROM observations")
            # Handle the case where the table is empty (Day 1)
            try:
                existing_obs = pd.read_sql(query_obs, conn)['subid'].tolist()
            except:
                existing_obs = [] # Table doesn't exist yet
                
            new_obs = self.obs_df[~self.obs_df['subid'].isin(existing_obs)]
            
            #Updating the PostGres databse
            with self.engine.begin() as transaction_conn:
                new_species.to_sql('species', transaction_conn, if_exists='append', index=False)
                new_obs.to_sql('observations', transaction_conn, if_exists='append', index=False)
                
                print(f"Added {len(new_species)} new species and {len(new_obs)} new sightings.")

    def process(self):
        self.extract()
        self.transform()
        self.load()