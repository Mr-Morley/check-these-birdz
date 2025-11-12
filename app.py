import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import pandas as pd
import requests
import sqlalchemy
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()
API_KEY = os.getenv("EBIRD_API_KEY")
DB_URL = os.getenv("DB_URL")

if not API_KEY or not DB_URL:
    st.error("Missing EBIRD_API_KEY or DB_URL in .env file")
    st.stop()

# Database connection
engine = sqlalchemy.create_engine(DB_URL)

@st.cache_data(ttl=3600)
def fetch_recent_sightings(region_code, days=7):
    """Fetch recent bird sightings from eBird API"""
    url = f"https://api.ebird.org/v2/data/obs/{region_code}/recent"
    headers = {"X-eBirdApiToken": API_KEY}
    params = {'back': days}
    
    try:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        
        if not data:
            return pd.DataFrame()
        
        df = pd.DataFrame(data)
        # Select relevant columns
        cols_to_keep = ['comName', 'locName', 'lat', 'lng', 'obsDt', 'howMany', 'speciesCode']
        df = df[[col for col in cols_to_keep if col in df.columns]]
        return df
    except Exception as e:
        st.error(f"Error fetching from eBird: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_species_info(species_codes):
    """Get species info from PostgreSQL encyclopedia"""
    if not species_codes:
        return pd.DataFrame()
    
    try:
        query = f"""
        SELECT "speciesCode", "comName", "sciName", "wikipedia_url"
        FROM species
        WHERE "speciesCode" IN ({','.join([f"'{code}'" for code in species_codes])})
        """
        df = pd.read_sql(query, engine)
        return df
    except Exception as e:
        st.warning(f"Could not load species encyclopedia: {e}")
        return pd.DataFrame()

def create_map(sightings_df, species_df, selected_species=None):
    """Create interactive map with markers"""
    if sightings_df.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    
    # Filter if species selected
    if selected_species and selected_species != "All Species":
        map_df = sightings_df[sightings_df['comName'] == selected_species].copy()
    else:
        map_df = sightings_df.copy()
    
    if map_df.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    
    # Merge with species info for Wikipedia URLs
    map_df = map_df.merge(species_df, on='comName', how='left')
    
    # Center map
    center_lat = map_df['lat'].mean()
    center_lng = map_df['lng'].mean()
    m = folium.Map(location=[center_lat, center_lng], zoom_start=6)
    
    cluster = MarkerCluster().add_to(m)
    
    for idx, row in map_df.iterrows():
        wiki_link = f'<a href="{row["wikipedia_url"]}" target="_blank">View on Wikipedia</a>' if pd.notna(row.get('wikipedia_url')) else "No Wikipedia link"
        
        popup_text = f"""
        <b>{row['comName']}</b><br>
        <i>{row.get('sciName', 'N/A')}</i><br>
        Location: {row['locName']}<br>
        Date: {row['obsDt']}<br>
        Count: {row.get('howMany', 'N/A')}<br>
        {wiki_link}
        """
        
        folium.Marker(
            [row['lat'], row['lng']],
            popup=folium.Popup(popup_text, max_width=300),
            icon=folium.Icon(color='blue', icon='info-sign')
        ).add_to(cluster)
    
    return m

def main():
    st.set_page_config(layout="wide")
    st.title("Check these birdz")
    
    # Sidebar
    st.sidebar.title("Filters")
    regions = {
        'ZA-WC': 'Western Cape',
        'ZA-GP': 'Gauteng',
        'ZA-MP': 'Mpumalanga (Kruger)',
        'ZA-LP': 'Limpopo',
        'ZA-NW': 'North West',
        'ZA-KZ': 'KwaZulu-Natal',
        'ZA-EC': 'Eastern Cape',
        'ZA-FS': 'Free State',
        'ZA-NC': 'Northern Cape'
    }
    
    # Multi-select for regions with "Select all" button
    col1, col2 = st.sidebar.columns([3, 1])
    with col1:
        selected_regions = st.multiselect(
            "Select Region(s)",
            list(regions.values()),
            default=list(regions.values())[0:1]  # Default to first region
        )
    with col2:
        if st.button("Select all", key="select_all_regions"):
            st.session_state.selected_regions = list(regions.values())
            st.rerun()
    
    days = st.sidebar.slider("Days back", 1, 30, 7)
    
    # Check if regions are selected
    if not selected_regions:
        st.warning("Please select at least one region")
        return
    
    # Fetch data from all selected regions
    all_sightings = []
    region_status = st.sidebar.empty()
    
    with st.spinner("Fetching recent sightings..."):
        for selected_region in selected_regions:
            region_code = [k for k, v in regions.items() if v == selected_region][0]
            sightings_df = fetch_recent_sightings(region_code, days)
            
            if not sightings_df.empty:
                sightings_df['region'] = selected_region  # Add region column for tracking
                all_sightings.append(sightings_df)
            else:
                region_status.info(f"ℹ️ No sightings in {selected_region}")
    
    if not all_sightings:
        st.warning(f"No recent sightings found for selected regions in the last {days} days")
        return
    
    # Combine all regions
    sightings_df = pd.concat(all_sightings, ignore_index=True)
    
    # Get species encyclopedia data
    species_codes = sightings_df['speciesCode'].unique().tolist()
    species_df = get_species_info(species_codes)
    
    # Dynamic species list
    all_species = ["All Species"] + sorted(sightings_df['comName'].unique().tolist())
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_species = st.selectbox("Select Species", all_species)
        m = create_map(sightings_df, species_df, selected_species)
        st_folium(m, width=1000, height=600)
    
    with col2:
        st.subheader("Sightings Summary")
        
        if selected_species != "All Species":
            species_data = sightings_df[sightings_df['comName'] == selected_species]
            st.metric("Total sightings", len(species_data))
            st.metric("Locations", species_data['locName'].nunique())
            st.metric("Regions", species_data['region'].nunique())
            
            # Show species info from encyclopedia
            species_info = species_df[species_df['comName'] == selected_species]
            if not species_info.empty:
                st.subheader("📖 Species Info")
                sci_name = species_info.iloc[0].get('sciName', 'N/A')
                wiki_url = species_info.iloc[0].get('wikipedia_url')
                
                st.write(f"**Scientific Name:** {sci_name}")
                if wiki_url:
                    st.markdown(f"[🔗 View on Wikipedia]({wiki_url})")
        else:
            st.metric("Total sightings", len(sightings_df))
            st.metric("Species found", sightings_df['comName'].nunique())
            st.metric("Unique locations", sightings_df['locName'].nunique())
            st.metric("Regions searched", sightings_df['region'].nunique())

if __name__ == "__main__":
    main()