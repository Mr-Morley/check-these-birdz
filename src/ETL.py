import json
import pandas as pd
from pathlib import Path
from sqlalchemy import create_engine, text
from .gateways import EBirdGateway, WikipediaEnricher

# Intermediate files (written between pipeline steps)
DATA_DIR     = Path("data")
RAW_PATH     = DATA_DIR / "raw_observations.json"
SPECIES_PATH = DATA_DIR / "species.parquet"
OBS_PATH     = DATA_DIR / "observations.parquet"


class SetupExtractTransformLoad:
    def __init__(self, ebird_key, db_url):
        self.ebird_api = EBirdGateway(ebird_key)
        self.wiki_api = WikipediaEnricher()
        self.engine = create_engine(db_url)
        self.raw_data = None
        self.species_df = None
        self.obs_df = None

    # ------------------------------------------------------------------
    # SETUP
    # ------------------------------------------------------------------

    def setup(self):
        """Creates tables, indexes, trigger, and views if they don't exist."""
        with self.engine.begin() as conn:

            # --- Extensions ---
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

            # --- Tables ---
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS species (
                    speciescode  TEXT PRIMARY KEY,
                    comname      TEXT NOT NULL,
                    sciname      TEXT NOT NULL,
                    wiki_url     TEXT,
                    description  TEXT,
                    iucn_status  TEXT DEFAULT 'Unknown'
                        CHECK (iucn_status IN (
                            'Least Concern', 'Near Threatened', 'Vulnerable',
                            'Endangered', 'Critically Endangered',
                            'Extinct in the Wild', 'Extinct', 'Data Deficient', 'Unknown'
                        ))
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS observations (
                    obs_id       TEXT PRIMARY KEY,
                    speciescode  TEXT REFERENCES species(speciescode),
                    howmany      DOUBLE PRECISION CHECK (howmany IS NULL OR howmany > 0),
                    lat          DOUBLE PRECISION CHECK (lat BETWEEN -90 AND 90),
                    lng          DOUBLE PRECISION CHECK (lng BETWEEN -180 AND 180),
                    obsdt        TIMESTAMP CHECK (obsdt <= NOW()),
                    geom         geometry(Point, 4326)
                );
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS etl_runs (
                    run_id         SERIAL PRIMARY KEY,
                    started_at     TIMESTAMPTZ DEFAULT NOW(),
                    completed_at   TIMESTAMPTZ,
                    status         TEXT NOT NULL CHECK (status IN ('running', 'success', 'failed')),
                    species_count  INTEGER DEFAULT 0,
                    obs_count      INTEGER DEFAULT 0,
                    duration_secs  FLOAT,
                    error_message  TEXT,
                    triggered_by   TEXT DEFAULT 'github_actions'
                );
            """))

            # --- Indexes ---
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_obs_geom ON observations USING GIST(geom);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_obs_date ON observations(obsdt DESC);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_obs_species ON observations(speciescode);"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS idx_obs_date_species ON observations(obsdt DESC, speciescode);"))

            # --- Trigger: auto-generate geometry from lat/lng ---
            conn.execute(text("""
                CREATE OR REPLACE FUNCTION set_geom_from_latlng()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.lat IS NOT NULL AND NEW.lng IS NOT NULL THEN
                        NEW.geom := ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326);
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """))
            conn.execute(text("DROP TRIGGER IF EXISTS trg_set_geom ON observations;"))
            conn.execute(text("""
                CREATE TRIGGER trg_set_geom
                    BEFORE INSERT OR UPDATE OF lat, lng ON observations
                    FOR EACH ROW EXECUTE FUNCTION set_geom_from_latlng();
            """))

            # --- Views ---
            conn.execute(text("""
                CREATE OR REPLACE VIEW v_dashboard_stats AS
                SELECT
                    COUNT(*)                                                    AS total_sightings,
                    COUNT(DISTINCT speciescode)                                 AS unique_species,
                    COALESCE(SUM(howmany), 0)::INT                              AS total_individuals,
                    MAX(obsdt)                                                  AS latest_observation,
                    COUNT(*) FILTER (WHERE obsdt >= CURRENT_DATE - 7)           AS obs_last_7_days,
                    COUNT(DISTINCT speciescode) FILTER (WHERE obsdt >= CURRENT_DATE - 7) AS species_last_7_days
                FROM observations;
            """))

            conn.execute(text("""
                CREATE OR REPLACE VIEW v_iucn_summary AS
                SELECT
                    s.iucn_status,
                    COUNT(DISTINCT s.speciescode) AS species_count,
                    COUNT(o.obs_id)               AS observation_count
                FROM species s
                LEFT JOIN observations o ON s.speciescode = o.speciescode
                GROUP BY s.iucn_status
                ORDER BY observation_count DESC;
            """))

            conn.execute(text("""
                CREATE OR REPLACE VIEW v_species_leaderboard AS
                SELECT
                    s.speciescode, s.comname, s.sciname, s.iucn_status,
                    COUNT(*)                                  AS total_observations,
                    COALESCE(SUM(o.howmany), 0)::INT          AS total_individuals,
                    MAX(o.obsdt)                              AS last_seen,
                    MIN(o.obsdt)                              AS first_seen,
                    COUNT(DISTINCT DATE(o.obsdt))             AS days_observed
                FROM species s
                JOIN observations o ON s.speciescode = o.speciescode
                GROUP BY s.speciescode, s.comname, s.sciname, s.iucn_status
                ORDER BY total_observations DESC;
            """))

        print("Tables, indexes, trigger, and views verified.")

    # ------------------------------------------------------------------
    # EXTRACT
    # ------------------------------------------------------------------

    def extract(self):
        """Fetches raw observation data from eBird and saves to disk."""
        print("Extracting data from eBird...")
        self.raw_data = self.ebird_api.fetch_recent_observations()

        # Save to disk so transform (separate process) can read it
        DATA_DIR.mkdir(exist_ok=True)
        RAW_PATH.write_text(json.dumps(self.raw_data))

        print(f"Extracted {len(self.raw_data)} observations -> {RAW_PATH}")

    # ------------------------------------------------------------------
    # TRANSFORM
    # ------------------------------------------------------------------

    def transform(self):
        """Cleans data and standardizes formats for PostgreSQL."""
        print("Transforming data...\n")

        # STEP 1: Load raw data from disk if needed (separate process)
        if self.raw_data is None:
            if not RAW_PATH.exists():
                raise FileNotFoundError(f"No raw data at {RAW_PATH}. Did extract run?")
            self.raw_data = json.loads(RAW_PATH.read_text())

        df = pd.DataFrame(self.raw_data)

        # STEP 2: Rename eBird camelCase to our lowercase DB columns
        column_map = {
            'speciesCode': 'speciescode',
            'comName':     'comname',
            'sciName':     'sciname',
            'subId':       'subid',
            'howMany':     'howmany',
            'lat':         'lat',
            'lng':         'lng',
            'obsDt':       'obsdt',
        }
        df = df.rename(columns=column_map)

        # STEP 3: Check required columns exist
        required = ['speciescode', 'comname', 'sciname', 'subid', 'lat', 'lng', 'obsdt']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"Missing required column from eBird API: {col}")

        # STEP 4: Add howmany if missing (eBird omits when count unknown)
        if 'howmany' not in df.columns:
            df['howmany'] = None

        # STEP 5: Standardize text to lowercase
        for col in ['speciescode', 'comname', 'sciname']:
            df[col] = df[col].astype(str).str.lower().str.strip()

        # STEP 6: Parse timestamps
        df['obsdt'] = pd.to_datetime(df['obsdt'], format='mixed')

        # STEP 7: Build species and observations DataFrames
        self.species_df = df[['speciescode', 'comname', 'sciname']].drop_duplicates()

        df['obs_id'] = df['subid'] + '_' + df['speciescode']
        self.obs_df = df[['obs_id', 'speciescode', 'howmany', 'lat', 'lng', 'obsdt']]

        # STEP 8: Save to disk so load (separate process) can read them
        self.species_df.to_parquet(SPECIES_PATH, index=False)
        self.obs_df.to_parquet(OBS_PATH, index=False)

        print(f"Transformed: {len(self.species_df)} species, {len(self.obs_df)} observations.")

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------

    def load(self):
        """Enriches new species and saves new observations to PostGIS."""
        print("Loading data into PostGIS...\n")

        # STEP 1: Load from disk if needed (separate process)
        if self.species_df is None:
            if not SPECIES_PATH.exists():
                raise FileNotFoundError(f"No data at {SPECIES_PATH}. Did transform run?")
            self.species_df = pd.read_parquet(SPECIES_PATH)
            self.obs_df = pd.read_parquet(OBS_PATH)

        with self.engine.connect() as conn:
            # PART A: Find and enrich new species
            try:
                existing_spp = pd.read_sql(
                    text("SELECT speciescode FROM species"), conn
                )['speciescode'].tolist()
                new_species = self.species_df[
                    ~self.species_df['speciescode'].isin(existing_spp)
                ].copy()
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
                existing_ids = pd.read_sql(
                    text("SELECT obs_id FROM observations"), conn
                )['obs_id'].tolist()
                new_obs = self.obs_df[
                    ~self.obs_df['obs_id'].isin(existing_ids)
                ].copy()
            except Exception:
                new_obs = self.obs_df.copy()

            # PART C: Write to database (single transaction — both or neither)
            with self.engine.begin() as transaction_conn:
                if not new_species.empty:
                    new_species.to_sql('species', transaction_conn, if_exists='append', index=False)
                    print(f"Successfully added {len(new_species)} new species.")

                if not new_obs.empty:
                    new_obs.to_sql('observations', transaction_conn, if_exists='append', index=False)
                    print(f"Successfully added {len(new_obs)} new sightings.")
                else:
                    print("No new sightings found in this period.")

    # ------------------------------------------------------------------
    # RUN ALL (for local development)
    # ------------------------------------------------------------------

    def run(self):
        self.setup()
        self.extract()
        self.transform()
        self.load()