# Check These Birdz

A data pipeline and dashboard for South African bird observations.

**Live App:** [check-these-birdz.streamlit.app](https://check-these-birdz.streamlit.app) 

---

## What It Does

This project collects recent bird sightings from the [eBird API](https://ebird.org/home), enriches each species with descriptions and conservation status from [Wikipedia](https://www.wikipedia.org/), and stores everything in a [Supabase](https://supabase.com/) PostgreSQL (PostGIS) database. A weekly automated pipeline keeps the data fresh, and a Streamlit dashboard makes it explorable.

## How It Works

1. **Extract** — Fetch recent observations from eBird for South Africa
2. **Transform** — Clean and standardise the data, generate unique observation IDs
3. **Enrich** — Look up new species on Wikipedia for descriptions and IUCN conservation status
4. **Load** — Insert only new species and observations into the database (no duplicates)
5. **Automate** — GitHub Actions runs the pipeline weekly every Monday
6. **Display** — Streamlit dashboard for exploring the data

## Tech Stack

| Layer | Tool |
|-------|------|
| Data source | eBird API |
| Enrichment | Wikipedia API |
| Database | Supabase (PostgreSQL) |
| ETL | Python, pandas, SQLAlchemy |
| Automation | GitHub Actions (weekly cron) |
| Frontend | Streamlit |
| Hosting | Streamlit Community Cloud |

## Project Structure

```
check-these-birdz/
├── run_pipeline.py          # ETL entrypoint
├── src/
│   ├── ETL.py               # Extract, Transform, Load logic
│   └── gateways.py          # eBird + Wikipedia API clients
├── Client/
│   └── app.py               # Streamlit dashboard
├── .github/workflows/
│   └── weekly-etl.yml       # Automated weekly pipeline
├── config.yaml              # App settings
├── requirements.txt
└── README.md
```

## Running Locally

```bash
git clone https://github.com/Mr-Morley/check-these-birdz.git
cd check-these-birdz
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```
EBIRD_API_KEY=your_key_here
DATABASE_URL=your_supabase_connection_string
```

Run the pipeline:

```bash
python run_pipeline.py
```

## Author
**William Morley** 