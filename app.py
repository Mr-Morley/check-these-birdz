import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import pandas as pd
import requests

# --- NO dotenv, NO SQLAlchemy, NO local DB ---
conn = st.connection("postgresql", type="sql")

API_KEY = st.secrets["EBIRD_API_KEY"]

@st.cache_data(ttl=3600)
def fetch_recent_sightings(region_code, days=7):
    url = f"https://api.ebird.org/v2/data/obs/{region_code}/recent"
    headers = {"X-eBirdApiToken": API_KEY}
    params = {'back': days}
    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        df = pd.DataFrame(resp.json())
        cols = ['comName', 'locName', 'lat', 'lng', 'obsDt', 'howMany', 'speciesCode']
        return df[[c for c in cols if c in df.columns]]
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_species_info(species_codes):
    if not species_codes:
        return pd.DataFrame()
    codes = ",".join([f"'{c}'" for c in species_codes])
    query = f"""
    SELECT "speciesCode", "comName", "sciName", "wikipedia_url"
    FROM species
    WHERE "speciesCode" IN ({codes})
    """
    return conn.query(query, ttl=3600)

def create_map(sightings_df, species_df, selected_species=None):
    if sightings_df.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    df = sightings_df.copy()
    if selected_species and selected_species != "All Species":
        df = df[df['comName'] == selected_species]
    if df.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    df = df.merge(species_df, on='comName', how='left')
    center = [df['lat'].mean(), df['lng'].mean()]
    m = folium.Map(location=center, zoom_start=6)
    cluster = MarkerCluster().add_to(m)
    for _, row in df.iterrows():
        wiki = f'<a href="{row["wikipedia_url"]}" target="_blank">Wikipedia</a>' if pd.notna(row["wikipedia_url"]) else "No link"
        popup = f"""
        <b>{row['comName']}</b><br>
        <i>{row.get('sciName', 'N/A')}</i><br>
        {row['locName']}<br>
        {row['obsDt']}<br>
        Count: {row.get('howMany', 'N/A')}<br>
        {wiki}
        """
        folium.Marker(
            [row['lat'], row['lng']],
            popup=folium.Popup(popup, max_width=300),
            icon=folium.Icon(color='blue', icon='info-sign')
        ).add_to(cluster)
    return m

def main():
    st.set_page_config(layout="wide")
    st.title("Check these birdz")

    regions = {
        'ZA-WC': 'Western Cape', 'ZA-GP': 'Gauteng', 'ZA-MP': 'Mpumalanga',
        'ZA-LP': 'Limpopo', 'ZA-NW': 'North West', 'ZA-KZ': 'KwaZulu-Natal',
        'ZA-EC': 'Eastern Cape', 'ZA-FS': 'Free State', 'ZA-NC': 'Northern Cape'
    }

    col1, col2 = st.sidebar.columns([3, 1])
    with col1:
        selected_regions = st.multiselect("Regions", list(regions.values()), default=["Western Cape"])
    with col2:
        if st.button("All"):
            st.session_state.selected_regions = list(regions.values())
            st.rerun()

    days = st.sidebar.slider("Days back", 1, 30, 7)

    if not selected_regions:
        st.warning("Select a region")
        return

    all_sightings = []
    with st.spinner("Fetching..."):
        for region in selected_regions:
            code = [k for k, v in regions.items() if v == region][0]
            df = fetch_recent_sightings(code, days)
            if not df.empty:
                df['region'] = region
                all_sightings.append(df)

    if not all_sightings:
        st.warning("No sightings")
        return

    sightings_df = pd.concat(all_sightings, ignore_index=True)
    species_codes = sightings_df['speciesCode'].unique().tolist()
    species_df = get_species_info(species_codes)

    all_species = ["All Species"] + sorted(sightings_df['comName'].unique())
    col1, col2 = st.columns([2, 1])
    with col1:
        species = st.selectbox("Species", all_species)
        m = create_map(sightings_df, species_df, species)
        st_folium(m, width=1000, height=600)
    with col2:
        st.subheader("Summary")
        if species != "All Species":
            data = sightings_df[sightings_df['comName'] == species]
            st.metric("Sightings", len(data))
            st.metric("Locations", data['locName'].nunique())
            info = species_df[species_df['comName'] == species]
            if not info.empty:
                st.write(f"**Sci:** {info.iloc[0]['sciName']}")
                if info.iloc[0]['wikipedia_url']:
                    st.markdown(f"[Wikipedia]({info.iloc[0]['wikipedia_url']})")
        else:
            st.metric("Sightings", len(sightings_df))
            st.metric("Species", sightings_df['comName'].nunique())

if __name__ == "__main__":
    main()