import pandas as pd
from sqlalchemy import create_engine, text
from .gateways import EBirdGateway, WikipediaEnricher

class ExtractTransformLoad:
    def __init__(self, ebird_key, db_url):
        # Initialize specialized gateways for eBird and Wikipedia
        self.ebird_api = EBirdGateway(ebird_key)
        self.wiki_api = WikipediaEnricher()
        self.engine = create_engine(db_url)
        self.raw_data = None
        self.species_df = None
        self.obs_df = None

    def setup_tables(self):
        """Creates tables with correct datatypes if they don't exist."""
        with self.engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS species (
                    speciescode TEXT PRIMARY KEY,
                    comname     TEXT,
                    sciname     TEXT,
                    wiki_url    TEXT,
                    description TEXT,
                    iucn_status TEXT
                );
            """))
            
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS observations (
                    obs_id      TEXT PRIMARY KEY,
                    speciescode TEXT REFERENCES species(speciescode),
                    howmany     SMALLINT,
                    lat         DOUBLE PRECISION,
                    lng         DOUBLE PRECISION,
                    obsdt       TIMESTAMP
                );
            """))
        print("Tables verified.")    

    def extract(self):
        """Fetches raw observation data from the eBird API."""
        print("Extracting data from eBird...")
        self.raw_data = self.ebird_api.fetch_recent_observations()

    def transform(self):
        """Cleans data and standardizes formats for PostgreSQL."""
        print("Transforming data... \n")
        df = pd.DataFrame(self.raw_data)
        df.columns = [col.lower() for col in df.columns]
        
        # Standardize
        text_cols = ['speciescode', 'comname', 'sciname']
        for col in text_cols:
            df[col] = df[col].astype(str).str.lower()

        # Handle varying eBird timestamp formats
        df['obsdt'] = pd.to_datetime(df['obsdt'], format='mixed')
        
        self.species_df = df[['speciescode', 'comname', 'sciname']].drop_duplicates()
        
        df['obs_id'] = df['subid'] + '_' + df['speciescode']
        self.obs_df = df[['obs_id', 'speciescode', 'howmany', 'lat', 'lng', 'obsdt']]

    def load(self):
        """Enriches new species and saves new observations to PostGIS."""
        print("Loading data into PostGIS...\n")
        with self.engine.connect() as conn:
            # PART A: Find and enrich new species
            try:
                existing_spp = pd.read_sql(text("SELECT speciescode FROM species"), conn)['speciescode'].tolist()
                new_species = self.species_df[~self.species_df['speciescode'].isin(existing_spp)].copy()
            except Exception:
                new_species = self.species_df.copy()

            if not new_species.empty:
                print(f"{len(new_species)} new species found. Starting Wikipedia enrichment...\n")
                for idx, row in new_species.iterrows():
                    meta = self.wiki_api.enrich(row['sciname'])
                    if meta:
                        new_species.at[idx, 'wiki_url'] = meta['wiki_url']
                        new_species.at[idx, 'description'] = meta['description']
                        new_species.at[idx, 'iucn_status'] = meta['iucn_status']
            else:
                print("No new species to enrich.")

            # PART B: Find new observations
            try:
                existing_ids = pd.read_sql(text("SELECT obs_id FROM observations"), conn)['obs_id'].tolist()
                new_obs = self.obs_df[~self.obs_df['obs_id'].isin(existing_ids)].copy()
            except Exception:
                new_obs = self.obs_df.copy()

            # PART C: Write to database
            with self.engine.begin() as transaction_conn:
                if not new_species.empty:
                    new_species.to_sql('species', transaction_conn, if_exists='append', index=False)
                    print(f"Successfully added {len(new_species)} new species.")

                if not new_obs.empty:
                    new_obs.to_sql('observations', transaction_conn, if_exists='append', index=False)
                    print(f"Successfully added {len(new_obs)} new sightings.")
                else:
                    print("No new sightings found in this period.")
    def run(self):
        self.setup_tables()
        self.extract()
        self.transform()
        self.load()