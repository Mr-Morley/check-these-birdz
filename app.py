import streamlit as st
import folium
from folium.plugins import MarkerCluster, HeatMap
from streamlit_folium import st_folium
import pandas as pd

# ============================================================================
# IMPORTS
# ============================================================================

from helpers.utils import (
    # Data retrieval
    get_recent_observations,
    get_all_species,
    # Data processing
    get_unique_species,
    get_summary_for_species,
    get_summary_for_all,
    get_recent_observations_for_species,
    prepare_map_data,
    add_iucn_colors_to_data,
    # Database info
    get_db_schema,
    get_table_stats,
    execute_select_query,
    # Database operations
    preview_duplicate_observations,
    delete_duplicate_observations,
    preview_observations_by_region,
    delete_observations_by_region,
    preview_observations_before_date,
    delete_observations_before_date,
    execute_custom_delete_update,
    # Region utilities
    get_all_regions,
    IUCN_COLORS,
)

# ============================================================================
# PAGE CONFIG & SESSION STATE
# ============================================================================

st.set_page_config(
    page_title="Check These Birdz",
    page_icon="🐦",
    layout="wide",
)

# Initialize dev auth state
if "dev_authenticated" not in st.session_state:
    st.session_state.dev_authenticated = False


# ============================================================================
# COMPONENT: MAP CREATION (Unchanged)
# ============================================================================

def create_map(
    df: pd.DataFrame,
    selected_species: str = None,
    use_heatmap: bool = False,
) -> folium.Map:
    """
    Create Folium map from observation data.
    
    Args:
        df: Observations dataframe (can be pre-filtered)
        selected_species: Filter by species name (for centering)
        use_heatmap: Use heatmap visualization instead of markers
        
    Returns:
        Folium map object
    """
    # If empty, return default map
    if df.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    
    # Prepare data
    data, center = prepare_map_data(df, selected_species)
    
    if data.empty:
        return folium.Map(location=[-29.0, 24.0], zoom_start=5)
    
    # Create map
    m = folium.Map(location=center, zoom_start=6)
    
    if use_heatmap:
        # Heatmap visualization
        heat_data = [
            [row['lat'], row['lng'], row.get('how_many', 1)]
            for _, row in data.iterrows()
        ]
        HeatMap(heat_data, radius=15, blur=25, max_zoom=1).add_to(m)
    
    else:
        # Marker cluster visualization with IUCN colors
        data = add_iucn_colors_to_data(data)
        cluster = MarkerCluster().add_to(m)
        
        for _, row in data.iterrows():
            # Build popup HTML
            wiki_link = (
                f'<a href="{row["wikipedia_url"]}" target="_blank">Wikipedia</a>'
                if pd.notna(row.get("wikipedia_url"))
                else ""
            )
            
            iucn_badge = f"<br><b>IUCN:</b> {row.get('iucn_category', 'N/A')}"
            
            popup = f"""
            <b>{row['com_name']}</b><br>
            <i>{row.get('sci_name', 'N/A')}</i><br>
            {row['loc_name']}<br>
            {row['obs_dt']}<br>
            Count: {row.get('how_many', 'N/A')}{iucn_badge}<br>
            {wiki_link}
            """
            
            folium.Marker(
                [row['lat'], row['lng']],
                popup=folium.Popup(popup, max_width=300),
                icon=folium.Icon(color='blue', icon='info-sign')
            ).add_to(cluster)
    
    return m


# COMPONENT: MAIN PAGE MAP

def render_main_map(
    df: pd.DataFrame, 
    use_heatmap: bool, 
    species_to_center: str
):
    """
    Renders the main map component.
    The df is assumed to be *already filtered* by the sidebar.
    """
    m = create_map(
        df, 
        selected_species=species_to_center, 
        use_heatmap=use_heatmap
    )
    
    # Use columns to effectively set a max-width and center the map
    # This prevents it from stretching *too* wide on 4K monitors
    _, col_map, _ = st.columns([1, 10, 1])
    with col_map:
        st_folium(m, width="100%", height=700, returned_objects=[])


# COMPONENT: SIDEBAR (New Components)

def render_sidebar_inputs() -> tuple:
    """
    Render sidebar controls that are *inputs* to the main data load.
    
    Returns:
        Tuple of (selected_regions, use_heatmap)
    """
    st.sidebar.header("Filters")
    
    regions = get_all_regions()
    
    selected_regions = st.sidebar.multiselect(
        "Select Regions",
        list(regions.keys()),
        default=['ZA-WC'],
        format_func=lambda x: regions[x]
    )

    use_heatmap = st.sidebar.checkbox(
        "Use Heatmap", 
        value=False, 
        key="sidebar_heatmap_toggle"
    )
    
    st.sidebar.divider()
    return selected_regions, use_heatmap


def render_sidebar_data_filters(df: pd.DataFrame) -> tuple:
    """
    Render sidebar filters that are *data-driven* (based on the loaded df).
    
    Args:
        df: The *unfiltered* dataframe from the database.
        
    Returns:
        Tuple of (filtered_dataframe, selected_species_name)
    """
    st.sidebar.subheader("Filter Loaded Data")
    
    # --- IUCN Filter ---
    # Get all unique, non-null IUCN categories from the data
    iucn_options = sorted(df['iucn_category'].dropna().unique())
    
    selected_iucn = st.sidebar.multiselect(
        "Filter by IUCN Status",
        options=iucn_options,
        default=iucn_options  # Default to all selected
    )
    
    # Filter the dataframe by the selected IUCN categories
    iucn_filtered_df = df[df['iucn_category'].isin(selected_iucn)]
    
    # --- Species Filter ---
    # Get species options *from the IUCN-filtered data*
    species_options = get_unique_species(iucn_filtered_df)
    
    selected_species = st.sidebar.selectbox(
        "Filter by Species",
        species_options,
    )
    
    # --- Final Data Filtering ---
    # This df will be used by the map
    if selected_species == "All Species":
        final_filtered_df = iucn_filtered_df
    else:
        final_filtered_df = iucn_filtered_df[
            iucn_filtered_df['com_name'] == selected_species
        ]
        
    # Return the map_df (fully filtered)
    # and the iucn_filtered_df (for the summary to use)
    # and the selected_species (for the summary to use)
    return final_filtered_df, iucn_filtered_df, selected_species


def render_sidebar_summary(
    df_for_summary: pd.DataFrame, 
    selected_species: str
):
    """
    Render the summary panel in the sidebar.
    
    Args:
        df_for_summary: The dataframe to pull summary stats from 
                        (e.g., the IUCN-filtered df).
        selected_species: The species to show details for 
                          ("All Species" for general summary).
    """
    with st.sidebar:
        st.divider()
        st.subheader("Summary")
        
        if selected_species != "All Species":
            # Species-specific summary
            summary = get_summary_for_species(df_for_summary, selected_species)
            
            if summary:
                st.metric("Total Sightings", summary['total_sightings'])
                st.metric("Unique Locations", summary['unique_locations'])
                
                st.divider()
                
                st.markdown("**Species Details**")
                st.write(f"**Scientific Name:**")
                st.write(f"*{summary.get('sci_name', 'N/A')}*")
                
                if summary.get('iucn_category'):
                    st.write(f"**IUCN Status:** {summary['iucn_category']}")
                
                if summary.get('wikipedia_url'):
                    st.markdown(
                        f"[View on Wikipedia]({summary['wikipedia_url']})"
                    )
                
                st.divider()
                
                st.subheader("Recent Observations")
                recent = get_recent_observations_for_species(
                    df_for_summary, 
                    selected_species
                )
                st.dataframe(recent, hide_index=True, use_container_width=True)
        
        else:
            # All observations summary
            summary = get_summary_for_all(df_for_summary)
            
            st.metric("Total Sightings", summary['total_sightings'])
            st.metric("Unique Species", summary['unique_species'])
            st.metric("Regions Covered", summary['regions_covered'])



# COMPONENT: DEVELOPER INFO PANEL

def render_dev_info_panel():
    """Render developer information panel with password protection."""
    with st.sidebar:
        st.divider()
        
        if st.checkbox("Dev Info", value=False):
            # Password protection
            if not st.session_state.dev_authenticated:
                dev_password = st.text_input(
                    "Dev password",
                    type="password",
                    key="dev_pass_sidebar"
                )
                if dev_password:
                    if dev_password == st.secrets.get("dev_password"):
                        st.session_state.dev_authenticated = True
                        st.rerun()
                    else:
                        st.error("Incorrect password")
                st.stop()
            
            # Show dev info
            st.subheader("Database Info")
            
            try:
                stats = get_table_stats()
                st.metric("Observations", f"{stats['observations']:,}")
                st.metric("Species", f"{stats['species']:,}")
                
                st.subheader("Tables")
                schema = get_db_schema()
                for _, row in schema.iterrows():
                    st.write(
                        f"**{row['table_name']}** ({row['column_count']} columns)"
                    )
                
                st.caption("Last updated: cached (1h)")
            except Exception as e:
                st.error(f"Could not fetch schema: {str(e)}")


# COMPONENT: SQL QUERY EDITOR

def render_sql_editor():
    """Render SQL query editor for developers."""
    with st.expander("SQL Query Editor (Dev)"):
        # Password protection
        if not st.session_state.dev_authenticated:
            dev_password = st.text_input(
                "Dev password",
                type="password",
                key="dev_pass_sql"
            )
            if dev_password:
                if dev_password == st.secrets.get("dev_password"):
                    st.session_state.dev_authenticated = True
                    st.rerun()
                else:
                    st.error("Incorrect password")
            st.stop()
        
        st.warning("Read and write access to database. Use carefully.")
        
        query_type = st.radio(
            "Query Type",
            ["SELECT (Read-Only)", "DELETE/UPDATE (Cleanup)"],
            key="query_type"
        )
        
        if query_type == "SELECT (Read-Only)":
            render_select_query()
        else:
            render_delete_update_operations()

# --- (All sub-functions for SQL editor remain unchanged) ---
# render_select_query()
# render_delete_update_operations()
# render_delete_duplicates()
# render_delete_by_region()
# render_delete_before_date()
# render_custom_delete_update()

# (Assuming all functions from line 290 to 386 are present and correct)
def render_select_query():
    """Render SELECT query interface."""
    sql_query = st.text_area(
        "Enter SELECT query",
        height=200,
        placeholder="SELECT * FROM observations LIMIT 10;"
    )
    
    if st.button("Execute Query"):
        try:
            result = execute_select_query(sql_query)
            st.write(f"Rows returned: {len(result)}")
            st.dataframe(result, use_container_width=True)
        except Exception as e:
            st.error(f"Query error: {str(e)}")


def render_delete_update_operations():
    """Render DELETE/UPDATE operations interface."""
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
        render_delete_duplicates()
    elif operation == "Delete observations by region":
        render_delete_by_region()
    elif operation == "Delete observations before date":
        render_delete_before_date()
    else:
        render_custom_delete_update()


def render_delete_duplicates():
    """Render duplicate deletion interface."""
    if st.button("Preview duplicates"):
        try:
            preview = preview_duplicate_observations()
            st.write(f"Found {len(preview)} duplicate submission IDs")
            st.dataframe(preview)
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    if st.button("Delete duplicates (CONFIRM)"):
        try:
            success, message = delete_duplicate_observations()
            if success:
                st.success(message)
            else:
                st.error(message)
        except Exception as e:
            st.error(f"Delete error: {str(e)}")


def render_delete_by_region():
    """Render region deletion interface."""
    regions = get_all_regions()
    
    region_to_delete = st.selectbox(
        "Select region to delete",
        list(regions.keys()),
        format_func=lambda x: regions[x]
    )
    
    if st.button(f"Preview {regions[region_to_delete]}"):
        try:
            count = preview_observations_by_region(region_to_delete)
            st.write(f"Will delete {count} observations")
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    if st.button(f"Delete all from {regions[region_to_delete]} (CONFIRM)"):
        try:
            success, message = delete_observations_by_region(region_to_delete)
            if success:
                st.success(message)
            else:
                st.error(message)
        except Exception as e:
            st.error(f"Delete error: {str(e)}")


def render_delete_before_date():
    """Render date-based deletion interface."""
    cutoff_date = st.date_input("Delete observations before this date")
    
    if st.button("Preview"):
        try:
            count = preview_observations_before_date(str(cutoff_date))
            st.write(f"Will delete {count} observations")
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    if st.button(f"Delete before {cutoff_date} (CONFIRM)"):
        try:
            success, message = delete_observations_before_date(str(cutoff_date))
            if success:
                st.success(message)
            else:
                st.error(message)
        except Exception as e:
            st.error(f"Delete error: {str(e)}")


def render_custom_delete_update():
    """Render custom query interface."""
    custom_query = st.text_area(
        "Enter custom DELETE/UPDATE query",
        height=200,
        placeholder="DELETE FROM observations WHERE..."
    )
    st.warning("This will execute immediately on confirmation")
    
    confirm = st.checkbox("I understand this cannot be undone")
    if st.button("Execute (CONFIRM - NO UNDO)"):
        if confirm:
            try:
                success, message = execute_custom_delete_update(custom_query)
                if success:
                    st.success(message)
                else:
                    st.error(message)
            except Exception as e:
                st.error(f"Query error: {str(e)}")



def main():
    """Main application entry point."""
    # NOTE: st.set_page_config() is already called at top level
    st.title("Check These Birdz")
    

    # 1. Render data-loading inputs
    selected_regions, use_heatmap = render_sidebar_inputs()
    
    # 2. Render developer info panel (conditionally)
    render_dev_info_panel()
    
  
    # LOAD DATA
    # Validate selection
    if not selected_regions:
        st.warning("Please select at least one region in the sidebar to load data.")
        st.stop()
    
    # Load initial data
    with st.spinner("Loading observations..."):
        df = get_recent_observations(selected_regions)
    
    if df.empty:
        st.warning("No observations found for the selected regions.")
        st.stop()
    
    
    (
        map_df, 
        summary_df, 
        selected_species
    ) = render_sidebar_data_filters(df)

    render_sidebar_summary(summary_df, selected_species)
    
  
    render_main_map(map_df, use_heatmap, selected_species)
    

    render_sql_editor()


if __name__ == "__main__":
    main()