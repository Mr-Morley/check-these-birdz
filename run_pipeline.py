"""
run_pipeline.py — Calls individual ETL steps.

Usage:
    python run_pipeline.py --step setup
    python run_pipeline.py --step extract
    python run_pipeline.py --step transform
    python run_pipeline.py --step load
    python run_pipeline.py              # runs all four in order
"""

import os
import sys
import argparse
from dotenv import load_dotenv

from src.ETL import SetupExtractTransformLoad

load_dotenv()


def main(step=None):
    ebird_key = os.getenv("EBIRD_API_KEY", "").strip()
    db_url = os.getenv("DATABASE_URL", "").strip()

    if not ebird_key or not db_url:
        print("ERROR: Missing EBIRD_API_KEY or DATABASE_URL")
        sys.exit(1)

    etl = SetupExtractTransformLoad(ebird_key=ebird_key, db_url=db_url)

    steps = {
        "setup":     etl.setup,
        "extract":   etl.extract,
        "transform": etl.transform,
        "load":      etl.load,
    }

    # Single step mode (called by GitHub Actions)
    if step:
        try:
            steps[step]()
        except Exception as e:
            print(f"ERROR in {step}: {e}")
            sys.exit(1)
        return

    # Full run (local development)
    for name, fn in steps.items():
        try:
            print(f"\n--- {name.upper()} ---")
            fn()
        except Exception as e:
            print(f"ERROR in {name}: {e}")
            sys.exit(1)

    print("\nPipeline complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--step", choices=["setup", "extract", "transform", "load"])
    args = parser.parse_args()
    main(step=args.step)