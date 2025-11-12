import streamlit as st
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import pandas as pd

conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=3600)
def get_recent_observations(regions=None, days=7):
    if regions:
        region_filter = "AND o.region IN (" + ",".join([f"'{r}'" for r in regions]) + ")"
    else:
        region_filter = ""
    
    query = f"""
    SELECT 
        o.sub_id,
        o.species_code,
        o.com_name,
        o.loc_name,
        o.lat,
        o.lng,
        o.obs_dt,
        o.how_many,
        o.region,
        s.sci_name,
        s.wikipedia_url
    FROM observations o
    LEFT JOIN species s ON o.species_code = s.species_code
    WHERE o.obs_dt >= NOW() - INTERVAL '{days} days'
    {region_filter}
    ORDER BY o.obs_dt DESC
    """
    return conn.query(query, ttl=600)

def create_map(df, selected_species=None):
    if df.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    
    data = df.copy()
    if selected_species and selected_species != "All Species":
        data = data[data['com_name'] == selected_species]
    
    if data.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    
    center = [data['lat'].mean(), data['lng'].mean()]
    m = folium.Map(location=center, zoom_start=6)
    cluster = MarkerCluster().add_to(m)
    
    for _, row in data.iterrows():
        wiki = f'<a href="{row["wikipedia_url"]}" target="_blank">Wikipedia</a>' if pd.notna(row["wikipedia_url"]) else ""
        
        popup = f"""
        <b>{row['com_name']}</b><br>
        <i>{row.get('sci_name', 'N/A')}</i><br>
        {row['loc_name']}<br>
        {row['obs_dt']}<br>
        Count: {row.get('how_many', 'N/A')}<br>
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
    st.title("🐦 Check These Birdz - South Africa")

    regions = {
        'ZA-WC': 'Western Cape', 
        'ZA-GP': 'Gauteng', 
        'ZA-MP': 'Mpumalanga',
        'ZA-LP': 'Limpopo', 
        'ZA-NW': 'North West', 
        'ZA-KZ': 'KwaZulu-Natal',
        'ZA-EC': 'Eastern Cape', 
        'ZA-FS': 'Free State', 
        'ZA-NC': 'Northern Cape'
    }

    st.sidebar.header("Filters")
    
    selected_regions = st.sidebar.multiselect(
        "Select Regions", 
        list(regions.keys()), 
        default=['ZA-WC'],
        format_func=lambda x: regions[x]
    )
    
    days = st.sidebar.slider("Days back", 1, 30, 7)

    if not selected_regions:
        st.warning("Select at least one region")
        return

    with st.spinner("Loading observations..."):
        df = get_recent_observations(selected_regions, days)

    if df.empty:
        st.warning("No observations found")
        return

    all_species = ["All Species"] + sorted(df['com_name'].unique())
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        selected_species = st.selectbox("Filter by Species", all_species)
        m = create_map(df, selected_species)
        st_folium(m, width=1200, height=700)
    
    with col2:
        st.subheader("📊 Summary")
        
        if selected_species != "All Species":
            species_data = df[df['com_name'] == selected_species]
            
            st.metric("Total Sightings", len(species_data))
            st.metric("Unique Locations", species_data['loc_name'].nunique())
            
            if not species_data.empty:
                row = species_data.iloc[0]
                st.write(f"**Scientific Name:**")
                st.write(f"*{row['sci_name']}*")
                
                if pd.notna(row['wikipedia_url']):
                    st.markdown(f"[📖 Learn More on Wikipedia]({row['wikipedia_url']})")
            
            st.subheader("Recent Observations")
            recent = species_data[['obs_dt', 'loc_name', 'how_many']].head(10)
            st.dataframe(recent, hide_index=True)
        
        else:
            st.metric("Total Sightings", len(df))
            st.metric("Unique Species", df['com_name'].nunique())
            st.metric("Regions Covered", df['region'].nunique())
            
            st.subheader("Top Species")
            top_species = df['com_name'].value_counts().head(10)
            st.bar_chart(top_species)

if __name__ == "__main__":
    main()