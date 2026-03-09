"""
run_pipeline.py — CLI wrapper for the Check These Birdz ETL pipeline.

Calls individual methods on SetupExtractTransformLoad so GitHub Actions
can run each stage as a separate step.

Usage:
    python run_pipeline.py setup
    python run_pipeline.py extract
    python run_pipeline.py transform
    python run_pipeline.py load
    python run_pipeline.py all        # Local dev shortcut
"""

import os
import sys
import json
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv
from src.gateways import EBirdGateway, WikipediaEnricher
from src.ETL import SetupExtractTransformLoad

# Loads .env locally, does nothing in GitHub Actions (no .env file there)
load_dotenv()

# ── Intermediate files (passed between workflow steps) ────────────
DATA_DIR = Path("pipeline_data")
RAW_JSON = DATA_DIR / "raw_observations.json"
SPECIES_CSV = DATA_DIR / "species.csv"
OBS_CSV = DATA_DIR / "observations.csv"


def build_pipeline():
    """Builds the pipeline object from environment variables."""
    ebird_key = os.environ.get("EBIRD_API_KEY", "")
 #   db_url = os.environ.get("DATABASE_URL", "")
    return SetupExtractTransformLoad(ebird_key, db_url)


def setup():
    pipeline = build_pipeline()
    pipeline.setup_tables()


def extract():
    pipeline = build_pipeline()
    pipeline.extract()

    # Save raw data to disk for the next step
    DATA_DIR.mkdir(exist_ok=True)
    RAW_JSON.write_text(json.dumps(pipeline.raw_data))
    print(f"Saved {len(pipeline.raw_data)} observations -> {RAW_JSON}")


def transform():
    if not RAW_JSON.exists():
        print(f"ERROR: {RAW_JSON} not found. Run 'extract' first.")
        sys.exit(1)

    pipeline = build_pipeline()
    pipeline.raw_data = json.loads(RAW_JSON.read_text())
    pipeline.transform()

    # Save transformed dataframes to disk for the next step
    pipeline.species_df.to_csv(SPECIES_CSV, index=False)
    pipeline.obs_df.to_csv(OBS_CSV, index=False)
    print(f"Saved transformed data -> {SPECIES_CSV}, {OBS_CSV}")


def load():
    if not SPECIES_CSV.exists() or not OBS_CSV.exists():
        print(f"ERROR: CSV files not found. Run 'transform' first.")
        sys.exit(1)

    pipeline = build_pipeline()
    pipeline.species_df = pd.read_csv(SPECIES_CSV)
    pipeline.obs_df = pd.read_csv(OBS_CSV)
    pipeline.load()


# ── CLI entry point ───────────────────────────────────────────────
STAGES = {
    "setup":     setup,
    "extract":   extract,
    "transform": transform,
    "load":      load,
}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: python run_pipeline.py <{'|'.join(STAGES.keys())}|all>")
        sys.exit(1)

    stage = sys.argv[1].lower()

    if stage == "all":
        pipeline = build_pipeline()
        pipeline.run()
    elif stage in STAGES:
        STAGES[stage]()
    else:
        print(f"Unknown stage: '{stage}'")
        print(f"Valid stages: {', '.join(STAGES.keys())}, all")
        sys.exit(1)