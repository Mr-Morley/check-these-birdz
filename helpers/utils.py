"""Utility functions for bird observation data processing and database operations."""
import pandas as pd
from typing import List, Dict, Tuple, Optional
import streamlit as st

# DATABASE CONNECTION

def get_db_connection():
    """Get PostgreSQL connection from Streamlit secrets."""
    return st.connection("postgresql", type="sql")


# DATA RETRIEVAL - OBSERVATIONS & SPECIES

@st.cache_data(ttl=600)
def get_recent_observations(regions: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Fetch recent observations from database, optionally filtered by regions.
    
    Args:
        regions: List of region codes (e.g., ['ZA-WC', 'ZA-MP'])
        
    Returns:
        DataFrame with observation data including species info
    """
    conn = get_db_connection()
    
    region_filter = ""
    if regions:
        region_placeholders = ",".join([f"'{r}'" for r in regions])
        region_filter = f"WHERE o.region IN ({region_placeholders})"
    
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
        s.wikipedia_url,
        s.iucn_category
    FROM observations o
    LEFT JOIN species s ON o.species_code = s."speciesCode"
    {region_filter}
    ORDER BY o.obs_dt DESC
    LIMIT 5000
    """
    return conn.query(query, ttl=0)


@st.cache_data(ttl=3600)
def get_all_species() -> pd.DataFrame:
    """Fetch all species from database."""
    conn = get_db_connection()
    query = "SELECT * FROM species"
    return conn.query(query, ttl=0)


# DATABASE SCHEMA & STATS

@st.cache_data(ttl=3600)
def get_db_schema() -> pd.DataFrame:
    """Fetch table information from database schema."""
    conn = get_db_connection()
    query = """
    SELECT 
        table_name,
        (SELECT COUNT(*) FROM information_schema.columns 
         WHERE table_name = t.table_name) as column_count
    FROM information_schema.tables t
    WHERE table_schema = 'public'
    ORDER BY table_name
    """
    return conn.query(query, ttl=0)


@st.cache_data(ttl=600)
def get_table_stats() -> Dict[str, int]:
    """Get row counts for main tables."""
    conn = get_db_connection()
    
    observations_count = conn.query(
        "SELECT COUNT(*) as count FROM observations", 
        ttl=0
    )['count'][0]
    
    species_count = conn.query(
        "SELECT COUNT(*) as count FROM species", 
        ttl=0
    )['count'][0]
    
    return {
        'observations': observations_count,
        'species': species_count
    }


# DATA FILTERING & PROCESSING

def filter_observations_by_species(
    df: pd.DataFrame, 
    species_name: str
) -> pd.DataFrame:
    """Filter observations by common name."""
    if species_name == "All Species":
        return df
    return df[df['com_name'] == species_name]


def get_unique_species(df: pd.DataFrame) -> List[str]:
    """Get sorted list of unique species from dataframe."""
    return ["All Species"] + sorted(df['com_name'].unique().tolist())


def get_summary_for_species(df: pd.DataFrame, species_name: str) -> Dict:
    """Get summary statistics for a specific species."""
    species_data = df[df['com_name'] == species_name]
    
    if species_data.empty:
        return {}
    
    return {
        'total_sightings': len(species_data),
        'unique_locations': species_data['loc_name'].nunique(),
        'sci_name': species_data.iloc[0].get('sci_name', 'N/A'),
        'wikipedia_url': species_data.iloc[0].get('wikipedia_url'),
        'iucn_category': species_data.iloc[0].get('iucn_category'),
    }


def get_summary_for_all(df: pd.DataFrame) -> Dict:
    """Get summary statistics for all observations."""
    return {
        'total_sightings': len(df),
        'unique_species': df['com_name'].nunique(),
        'regions_covered': df['region'].nunique(),
    }


def get_recent_observations_for_species(
    df: pd.DataFrame,
    species_name: str,
    limit: int = 10
) -> pd.DataFrame:
    """Get recent observations for a species."""
    species_data = df[df['com_name'] == species_name]
    return species_data[['obs_dt', 'loc_name', 'how_many']].head(limit)

# MAP DATA PREPARATION

def prepare_map_data(
    df: pd.DataFrame,
    selected_species: Optional[str] = None
) -> Tuple[pd.DataFrame, Tuple[float, float]]:
    """
    Prepare data for map visualization.
    
    Returns:
        Tuple of (filtered_data, center_coordinates)
    """
    data = df.copy()
    
    if selected_species and selected_species != "All Species":
        data = data[data['com_name'] == selected_species]
    
    if data.empty:
        # Default South Africa center
        center = (-29.0, 24.0)
    else:
        center = (data['lat'].mean(), data['lng'].mean())
    
    return data, center


# IUCN STATUS UTILITIES

IUCN_COLORS = {
    "EX": "#000000",   # Extinct - Black
    "EW": "#333333",   # Extinct in the Wild - Dark Gray
    "CR": "#FF0000",   # Critically Endangered - Red
    "EN": "#FF6600",   # Endangered - Orange
    "VU": "#FFFF00",   # Vulnerable - Yellow
    "NT": "#CCFF99",   # Near Threatened - Light Green
    "LC": "#00FF00",   # Least Concern - Green
    "DD": "#CCCCCC",   # Data Deficient - Gray
}

IUCN_ORDER = ["EX", "EW", "CR", "EN", "VU", "NT", "LC", "DD"]


def get_iucn_color(category: Optional[str]) -> str:
    """Get color code for IUCN category."""
    if not category:
        return "#808080"  # Gray for unknown
    return IUCN_COLORS.get(category, "#808080")


def add_iucn_colors_to_data(df: pd.DataFrame) -> pd.DataFrame:
    """Add color column based on IUCN category."""
    df = df.copy()
    df['color'] = df['iucn_category'].apply(get_iucn_color)
    return df


# DATABASE OPERATIONS - READ ONLY

def execute_select_query(query: str) -> pd.DataFrame:
    """
    Execute a SELECT query (read-only).
    
    Args:
        query: SQL SELECT query
        
    Returns:
        Query result as DataFrame
    """
    conn = get_db_connection()
    return conn.query(query, ttl=0)


# DATABASE OPERATIONS - WRITE (DELETE/UPDATE)

def delete_duplicate_observations() -> Tuple[bool, str]:
    """Delete duplicate observations by sub_id."""
    try:
        conn = get_db_connection()
        conn.session.execute("""
            DELETE FROM observations o1
            WHERE rowid NOT IN (
                SELECT MIN(rowid)
                FROM observations o2
                WHERE o1.sub_id = o2.sub_id
            )
        """)
        return True, "Duplicates deleted successfully"
    except Exception as e:
        return False, f"Error: {str(e)}"


def preview_duplicate_observations() -> pd.DataFrame:
    """Preview duplicate observations by sub_id."""
    conn = get_db_connection()
    query = """
        SELECT sub_id, COUNT(*) as count 
        FROM observations 
        GROUP BY sub_id 
        HAVING COUNT(*) > 1
    """
    return conn.query(query, ttl=0)


def delete_observations_by_region(region: str) -> Tuple[bool, str]:
    """Delete all observations from a specific region."""
    try:
        conn = get_db_connection()
        conn.session.execute(f"""
            DELETE FROM observations WHERE region = '{region}'
        """)
        return True, f"Deleted all observations from {region}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def preview_observations_by_region(region: str) -> int:
    """Get count of observations in a region."""
    conn = get_db_connection()
    result = conn.query(f"""
        SELECT COUNT(*) as count FROM observations 
        WHERE region = '{region}'
    """, ttl=0)
    return result['count'][0]


def delete_observations_before_date(cutoff_date: str) -> Tuple[bool, str]:
    """Delete observations before a specific date."""
    try:
        conn = get_db_connection()
        conn.session.execute(f"""
            DELETE FROM observations WHERE obs_dt < '{cutoff_date}'
        """)
        return True, f"Deleted observations before {cutoff_date}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def preview_observations_before_date(cutoff_date: str) -> int:
    """Get count of observations before a date."""
    conn = get_db_connection()
    result = conn.query(f"""
        SELECT COUNT(*) as count FROM observations 
        WHERE obs_dt < '{cutoff_date}'
    """, ttl=0)
    return result['count'][0]


def execute_custom_delete_update(query: str) -> Tuple[bool, str]:
    """
    Execute a custom DELETE or UPDATE query.
    
    Args:
        query: Custom SQL query
        
    Returns:
        Tuple of (success, message)
    """
    try:
        conn = get_db_connection()
        conn.session.execute(query)
        return True, "Query executed successfully"
    except Exception as e:
        return False, f"Error: {str(e)}"


# REGION UTILITIES

REGIONS = {
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


def get_region_name(region_code: str) -> str:
    """Get full name for region code."""
    return REGIONS.get(region_code, region_code)


def get_all_regions() -> Dict[str, str]:
    """Get all available regions."""
    return REGIONS.copy()


def get_region_codes() -> List[str]:
    """Get list of region codes."""
    return list(REGIONS.keys())