import streamlit as st
import geopandas as gpd
import pandas as pd
import numpy as np
import yaml
from sqlalchemy import create_engine
import pydeck as pdk
import os
from dotenv import load_dotenv

# --- 1. SETUP & CONFIG ---
with open("config.yaml", "r") as f:
    config = yaml.safe_load(f)

load_dotenv(dotenv_path=".env") 

DB_USER = os.getenv("POSTGRES_USER")
DB_PASS = os.getenv("POSTGRES_PASSWORD")
DB_HOST = os.getenv("POSTGRES_HOST")
DB_PORT = os.getenv("POSTGRES_PORT")
DB_NAME = os.getenv("POSTGRES_DB")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

# --- 2. UI FILTERS ---
st.set_page_config(layout="wide", page_title="check-these-birdz")
st.sidebar.title("🐦 check-these-birdz")
province = st.sidebar.selectbox("Region Filter", ["All"] + list(config['spatial_filters'].keys()))
days = st.sidebar.slider("Historical Window (Days)", 1, 14, 7)

# --- 3. SPATIAL QUERY ---
if province != "All":
    bounds = config['spatial_filters'][province]
    spatial_sql = f"""
        AND o.lat BETWEEN {bounds['lat'][0]} AND {bounds['lat'][1]}
        AND o.lng BETWEEN {bounds['lng'][0]} AND {bounds['lng'][1]}
    """
else:
    spatial_sql = ""

sql = f"""
    SELECT o.speciescode, s.comname, o.geom, s.iucn_status, s.wiki_url
    FROM public.observations o
    JOIN public.species s ON o.speciescode = s.speciescode
    WHERE o.obsdt >= NOW() - INTERVAL '{days} days' {spatial_sql}
"""

# --- 4. DATA PROCESSING ---
gdf = gpd.read_postgis(sql, engine, geom_col='geom')

if not gdf.empty:

    # Ensure WGS84 for deck.gl
    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    # Extract longitude & latitude columns
    gdf["lon"] = gdf.geometry.x
    gdf["lat"] = gdf.geometry.y

    # Color mapping
    color_list = [
        config['iucn_colors'].get(s, config['iucn_colors']['default'])
        for s in gdf['iucn_status']
    ]
    gdf["color"] = color_list

# --- 5. RENDER ---
    st.title(f"📍 Sightings: {province}")

    layer = pdk.Layer(
        "ScatterplotLayer",
        data=gdf,
        get_position='[lon, lat]',
        get_fill_color="color",
        get_radius=config['map_settings']['default_radius'],
        pickable=True,
        auto_highlight=True,
    )

    view_state = pdk.ViewState(
        longitude=gdf["lon"].mean(),
        latitude=gdf["lat"].mean(),
        zoom=6,
        pitch=0,
    )

    tooltip = {
        "html": """
        <b>Species:</b> {comname} <br/>
        <b>IUCN:</b> {iucn_status} <br/>
        <a href="{wiki_url}" target="_blank">Wikipedia</a>
        """,
        "style": {"backgroundColor": "black", "color": "white"}
    }

    deck = pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip=tooltip,
    )

    st.pydeck_chart(deck)

    st.write(f"Showing **{len(gdf)}** sightings.")
else:
    st.info("No sightings found in this region.")
