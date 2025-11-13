import streamlit as st
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import pandas as pd

conn = st.connection("postgresql", type="sql")

@st.cache_data(ttl=600)
def get_recent_observations(regions=None):
    if regions:
        region_filter = "WHERE o.region IN (" + ",".join([f"'{r}'" for r in regions]) + ")"
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
        s."sciName" as sci_name,
        s.wikipedia_url
    FROM observations o
    LEFT JOIN species s ON o.species_code = s."speciesCode"
    {region_filter}
    ORDER BY o.obs_dt DESC
    LIMIT 5000
    """
    return conn.query(query, ttl=0)

@st.cache_data(ttl=3600)
def get_db_schema():
    """Fetch table info for dev panel (read-only)"""
    query = """
    SELECT 
        table_name,
        (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as column_count
    FROM information_schema.tables t
    WHERE table_schema = 'public'
    ORDER BY table_name
    """
    return conn.query(query, ttl=0)

@st.cache_data(ttl=600)
def get_table_stats():
    """Get row counts for each table"""
    observations_count = conn.query("SELECT COUNT(*) as count FROM observations", ttl=0)['count'][0]
    species_count = conn.query("SELECT COUNT(*) as count FROM species", ttl=0)['count'][0]
    
    return {
        'observations': observations_count,
        'species': species_count
    }

def create_map(df, selected_species=None, use_heatmap=False):
    if df.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    
    data = df.copy()
    if selected_species and selected_species != "All Species":
        data = data[data['com_name'] == selected_species]
    
    if data.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    
    center = [data['lat'].mean(), data['lng'].mean()]
    m = folium.Map(location=center, zoom_start=6)
    
    if use_heatmap:
        heat_data = [[row['lat'], row['lng'], row.get('how_many', 1)] for _, row in data.iterrows()]
        HeatMap(heat_data, radius=15, blur=25, max_zoom=1).add_to(m)
    else:
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
    
    # PASSWORD CHECK FIRST - BLOCKS EVERYTHING ELSE
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    
    if not st.session_state.password_correct:
        st.title("Check These Birdz - Dev Access Required")
        password = st.text_input("Enter dev password", type="password")
        
        if password:
            if password == st.secrets.get("dev_password"):
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("Incorrect password")
                st.stop()
        else:
            st.info("Password required to access this app")
            st.stop()
    
    # NOW render the main app - only authenticated users get here
    st.title("Check These Birdz")

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

    use_heatmap = st.sidebar.checkbox("Use Heatmap", value=False)

    if not selected_regions:
        st.warning("Select at least one region")
        return

    with st.spinner("Loading observations..."):
        df = get_recent_observations(selected_regions)

    if df.empty:
        st.warning("No observations found")
        return

    all_species = ["All Species"] + sorted(df['com_name'].unique())
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        selected_species = st.selectbox("Filter by Species", all_species)
        m = create_map(df, selected_species, use_heatmap=use_heatmap)
        st_folium(m, width=1200, height=700, returned_objects=[])
    
    with col2:
        st.subheader("Summary")
        
        if selected_species != "All Species":
            species_data = df[df['com_name'] == selected_species]
            
            st.metric("Total Sightings", len(species_data))
            st.metric("Unique Locations", species_data['loc_name'].nunique())
            
            if not species_data.empty:
                row = species_data.iloc[0]
                st.write(f"**Scientific Name:**")
                st.write(f"*{row['sci_name']}*")
                
                if pd.notna(row['wikipedia_url']):
                    st.markdown(f"Wikipedia ({row['wikipedia_url']})")
            
            st.subheader("Recent Observations")
            recent = species_data[['obs_dt', 'loc_name', 'how_many']].head(10)
            st.dataframe(recent, hide_index=True)
        
        else:
            st.metric("Total Sightings", len(df))
            st.metric("Unique Species", df['com_name'].nunique())
            st.metric("Regions Covered", df['region'].nunique())
    
    # Developer info panel
    with st.sidebar:
        st.divider()
        if st.checkbox("Dev Info", value=False):
            st.subheader("Database Info")
            
            try:
                stats = get_table_stats()
                st.metric("Observations", f"{stats['observations']:,}")
                st.metric("Species", f"{stats['species']:,}")
                
                st.subheader("Tables")
                schema = get_db_schema()
                for _, row in schema.iterrows():
                    st.write(f"**{row['table_name']}** ({row['column_count']} columns)")
                
                st.caption("Last updated: cached (1h)")
            except Exception as e:
                st.error(f"Could not fetch schema: {str(e)}")
    
    # SQL Query Editor (Dev Only)
    with st.expander("SQL Query Editor (Dev)"):
        st.warning("Read and write access to database. Use carefully.")
        
        query_type = st.radio("Query Type", ["SELECT (Read-Only)", "DELETE/UPDATE (Cleanup)"], key="query_type")
        
        if query_type == "SELECT (Read-Only)":
            sql_query = st.text_area("Enter SELECT query", height=200, placeholder="SELECT * FROM observations LIMIT 10;")
            
            if st.button("Execute Query"):
                try:
                    result = conn.query(sql_query, ttl=0)
                    st.write(f"Rows returned: {len(result)}")
                    st.dataframe(result, use_container_width=True)
                except Exception as e:
                    st.error(f"Query error: {str(e)}")
        
        else:
            st.subheader("Delete/Update Operations")
            operation = st.selectbox(
                "Operation",
                [
                    "Delete duplicate observations",
                    "Delete observations by region",
                    "Delete observations before date",
                    "Custom DELETE/UPDATE"
                ]
            )
            
            if operation == "Delete duplicate observations":
                if st.button("Preview duplicates"):
                    try:
                        preview = conn.query("""
                            SELECT sub_id, COUNT(*) as count 
                            FROM observations 
                            GROUP BY sub_id 
                            HAVING COUNT(*) > 1
                        """, ttl=0)
                        st.write(f"Found {len(preview)} duplicate submission IDs")
                        st.dataframe(preview)
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                
                if st.button("Delete duplicates (CONFIRM)"):
                    try:
                        conn.session.execute("""
                            DELETE FROM observations o1
                            WHERE rowid NOT IN (
                                SELECT MIN(rowid)
                                FROM observations o2
                                WHERE o1.sub_id = o2.sub_id
                            )
                        """)
                        st.success("Duplicates deleted")
                    except Exception as e:
                        st.error(f"Delete error: {str(e)}")
            
            elif operation == "Delete observations by region":
                region_to_delete = st.selectbox("Select region to delete", [
                    "ZA-WC", "ZA-GP", "ZA-MP", "ZA-LP", "ZA-NW",
                    "ZA-KZ", "ZA-EC", "ZA-FS", "ZA-NC"
                ])
                
                if st.button(f"Preview {region_to_delete}"):
                    try:
                        preview = conn.query(f"""
                            SELECT COUNT(*) as count FROM observations 
                            WHERE region = '{region_to_delete}'
                        """, ttl=0)
                        st.write(f"Will delete {preview['count'][0]} observations")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                
                if st.button(f"Delete all from {region_to_delete} (CONFIRM)"):
                    try:
                        conn.session.execute(f"""
                            DELETE FROM observations WHERE region = '{region_to_delete}'
                        """)
                        st.success(f"Deleted all observations from {region_to_delete}")
                    except Exception as e:
                        st.error(f"Delete error: {str(e)}")
            
            elif operation == "Delete observations before date":
                cutoff_date = st.date_input("Delete observations before this date")
                
                if st.button("Preview"):
                    try:
                        preview = conn.query(f"""
                            SELECT COUNT(*) as count FROM observations 
                            WHERE obs_dt < '{cutoff_date}'
                        """, ttl=0)
                        st.write(f"Will delete {preview['count'][0]} observations")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
                
                if st.button(f"Delete before {cutoff_date} (CONFIRM)"):
                    try:
                        conn.session.execute(f"""
                            DELETE FROM observations WHERE obs_dt < '{cutoff_date}'
                        """)
                        st.success(f"Deleted observations before {cutoff_date}")
                    except Exception as e:
                        st.error(f"Delete error: {str(e)}")
            
            else:
                custom_query = st.text_area("Enter custom DELETE/UPDATE query", height=200, placeholder="DELETE FROM observations WHERE...")
                st.warning("This will execute immediately on confirmation")
                
                if st.button("Execute (CONFIRM - NO UNDO)"):
                    confirm = st.checkbox("I understand this cannot be undone")
                    if confirm:
                        try:
                            conn.session.execute(custom_query)
                            st.success("Query executed")
                        except Exception as e:
                            st.error(f"Query error: {str(e)}")

if __name__ == "__main__":
    main()