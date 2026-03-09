"""
Check These Birdz — Dashboard
A read-only dashboard displaying recent bird observations across South Africa.
Uses Supabase PostGIS views and spatial RPC functions.
"""

import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Check These Birdz",
    page_icon=":)",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------------------------

@st.cache_resource
def get_engine():
    """Creates a cached SQLAlchemy engine using Streamlit secrets."""
    return create_engine(
        st.secrets["database"]["url"],
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=2,
    )


def safe_query(query_text: str, params: dict = None) -> pd.DataFrame:
    """Runs a parameterized read-only query with error handling."""
    engine = get_engine()
    try:
        with engine.connect() as conn:
            return pd.read_sql(text(query_text), conn, params=params or {})
    except Exception as e:
        st.error(f"Database query failed: {e}")
        return pd.DataFrame()

# ---------------------------------------------------------------------------
# CACHED QUERIES — All use views or parameterized SQL
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner="Loading dashboard stats...")
def get_dashboard_stats() -> dict:
    """Fetches pre-computed stats from the v_dashboard_stats view."""
    df = safe_query("SELECT * FROM v_dashboard_stats")
    if df.empty:
        return {}
    return df.iloc[0].to_dict()


@st.cache_data(ttl=3600, show_spinner="Loading IUCN summary...")
def get_iucn_summary() -> pd.DataFrame:
    """Fetches conservation breakdown from the v_iucn_summary view."""
    return safe_query("SELECT * FROM v_iucn_summary")


@st.cache_data(ttl=3600, show_spinner="Loading species leaderboard...")
def get_species_leaderboard(limit: int = 20) -> pd.DataFrame:
    """Fetches top species from the v_species_leaderboard view."""
    return safe_query(
        "SELECT * FROM v_species_leaderboard LIMIT :lim",
        {"lim": limit},
    )


@st.cache_data(ttl=3600, show_spinner="Fetching bird sightings...")
def get_sightings(days: int) -> pd.DataFrame:
    """Fetches recent sightings using the geom column via PostGIS."""
    return safe_query("""
        SELECT
            o.obs_id, o.speciescode,
            s.comname, s.sciname, s.iucn_status, s.wiki_url,
            o.howmany,
            ST_Y(o.geom) AS lat,
            ST_X(o.geom) AS lng,
            o.obsdt
        FROM observations o
        JOIN species s ON o.speciescode = s.speciescode
        WHERE o.obsdt >= (CURRENT_DATE - :days)
        ORDER BY o.obsdt DESC
    """, {"days": days})


@st.cache_data(ttl=3600, show_spinner="Finding nearby birds...")
def get_nearby_sightings(lat: float, lng: float, radius_km: float, days: int) -> pd.DataFrame:
    """Calls the nearby_sightings RPC function (ST_DWithin spatial query)."""
    return safe_query(
        "SELECT * FROM nearby_sightings(:lat, :lng, :radius, :days)",
        {"lat": lat, "lng": lng, "radius": radius_km, "days": days},
    )


@st.cache_data(ttl=3600, show_spinner="Calculating hotspots...")
def get_hotspots(days: int = 30) -> pd.DataFrame:
    """Calls the species_hotspots RPC function (ST_ClusterDBSCAN)."""
    return safe_query(
        "SELECT * FROM species_hotspots(:days, 3)",
        {"days": days},
    )


@st.cache_data(ttl=300, show_spinner="Checking pipeline status...")
def get_last_etl_run() -> dict:
    """Fetches the most recent ETL run from the audit table."""
    df = safe_query("""
        SELECT run_id, started_at, completed_at, status, 
               species_count, obs_count, duration_secs
        FROM etl_runs
        ORDER BY run_id DESC LIMIT 1
    """)
    if df.empty:
        return {}
    return df.iloc[0].to_dict()

# ---------------------------------------------------------------------------
# STYLING
# ---------------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=DM+Sans:wght@400;500;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'DM Sans', sans-serif;
    }

    .main-title {
        font-family: 'DM Serif Display', serif;
        font-size: 2.8rem;
        color: #1a1a2e;
        margin-bottom: 0;
        letter-spacing: -0.5px;
    }

    .subtitle {
        font-size: 1.1rem;
        color: #6c757d;
        margin-top: -8px;
        margin-bottom: 2rem;
    }

    .section-header {
        font-family: 'DM Serif Display', serif;
        font-size: 1.4rem;
        color: #1a1a2e;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }

    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border: 1px solid #dee2e6;
        border-radius: 12px;
        padding: 1rem 1.25rem;
    }

    [data-testid="stMetric"] label,
    [data-testid="stMetric"] [data-testid="stMetricLabel"],
    [data-testid="stMetric"] [data-testid="stMetricLabel"] p,
    [data-testid="stMetric"] [data-testid="stMetricLabel"] div {
        color: #495057 !important;
    }

    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] [data-testid="stMetricValue"] div {
        font-family: 'DM Serif Display', serif;
        color: #1a1a2e !important;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }

    [data-testid="stSidebar"] [data-testid="stMarkdown"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdown"] span:not(.iucn-dot),
    [data-testid="stSidebar"] .stSlider label,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] h3,
    [data-testid="stSidebar"] a {
        color: #e9ecef !important;
    }

    .etl-status {
        font-size: 0.8rem;
        padding: 4px 10px;
        border-radius: 8px;
        display: inline-block;
        font-weight: 600;
    }
    .etl-success { background: #d4edda; color: #155724; }
    .etl-failed  { background: #f8d7da; color: #721c24; }
    .etl-running { background: #fff3cd; color: #856404; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# IUCN COLOR MAP
# ---------------------------------------------------------------------------
IUCN_COLORS_HEX = {
    "least concern":          "#48c78e",
    "near threatened":        "#ffc107",
    "vulnerable":             "#ff9800",
    "endangered":             "#f44336",
    "critically endangered":  "#b71c1c",
}
DEFAULT_HEX = "#9e9e9e"


def get_marker_color(status: str) -> str:
    """Maps IUCN status to a hex color for map markers."""
    if not status:
        return DEFAULT_HEX
    status_lower = str(status).lower()
    for key, color in IUCN_COLORS_HEX.items():
        if key in status_lower:
            return color
    return DEFAULT_HEX

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## Check These Birdz")
    st.caption("Live bird observations across South Africa")
    st.divider()

    days = st.slider("Lookback Window (days)", min_value=1, max_value=14, value=7)
    st.divider()

    # --- IUCN Legend ---
    st.markdown("**IUCN Status Legend**")
    for label, hex_color in IUCN_COLORS_HEX.items():
        st.markdown(
            f'<span class="iucn-dot" style="color:{hex_color} !important; '
            f'font-size:1.4rem; line-height:1;">&#9679;</span>&nbsp;'
            f'{label.title()}',
            unsafe_allow_html=True,
        )

    st.divider()

    # --- IUCN Summary from view ---
    iucn_df = get_iucn_summary()
    if not iucn_df.empty:
        st.markdown("**Conservation Breakdown**")
        for _, row in iucn_df.iterrows():
            status = str(row["iucn_status"]).title()
            color = get_marker_color(row["iucn_status"])
            st.markdown(
                f'<span style="color:{color}; font-weight:600;">{status}</span>'
                f' &mdash; {int(row["species_count"])} species, '
                f'{int(row["observation_count"])} obs',
                unsafe_allow_html=True,
            )
        st.divider()

    # --- ETL Pipeline Status ---
    etl = get_last_etl_run()
    if etl:
        st.markdown("**Pipeline Status**")
        status_class = f"etl-{etl.get('status', 'unknown')}"
        status_label = str(etl.get("status", "unknown")).upper()
        st.markdown(
            f'<span class="etl-status {status_class}">{status_label}</span>',
            unsafe_allow_html=True,
        )
        if etl.get("started_at"):
            ts = pd.Timestamp(etl["started_at"])
            st.caption(f"Last run: {ts.strftime('%d %b %Y %H:%M')} UTC")
        if etl.get("duration_secs"):
            st.caption(f"Duration: {etl['duration_secs']:.1f}s")
        st.divider()

    # --- Refresh button ---
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

    st.markdown(
        "Data sourced from [eBird](https://ebird.org), "
        "enriched via [Wikipedia](https://en.wikipedia.org)."
    )

# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
st.markdown('<p class="main-title">Check These Birdz</p>', unsafe_allow_html=True)
st.markdown(
    f'<p class="subtitle">Live bird observations across South Africa'
    f' &mdash; last {days} days</p>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# METRICS — from v_dashboard_stats view (no Python computation)
# ---------------------------------------------------------------------------
stats = get_dashboard_stats()
if stats:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Sightings", f"{stats.get('total_sightings', 0):,}")
    with col2:
        st.metric("Unique Species", f"{stats.get('unique_species', 0):,}")
    with col3:
        st.metric("Individual Birds", f"{stats.get('total_individuals', 0):,}")
    with col4:
        latest = stats.get("latest_observation")
        if latest:
            st.metric("Latest Observation", pd.Timestamp(latest).strftime("%d %b %Y"))
        else:
            st.metric("Latest Observation", "N/A")

st.divider()

# ---------------------------------------------------------------------------
# TABS
# ---------------------------------------------------------------------------
tab_explore, tab_spatial, tab_species = st.tabs(["Explore", "Spatial Analysis", "Species"])

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------
def build_popup_html(row: pd.Series) -> str:
    """Builds the HTML content for a Folium map popup."""
    comname = str(row["comname"]).title()
    sciname = str(row["sciname"])
    wiki_slug = sciname.replace(" ", "_").capitalize()

    iucn = str(row["iucn_status"]).title()
    badge_color = get_marker_color(str(row["iucn_status"]))

    count = row["howmany"] if pd.notna(row["howmany"]) else "n/a"
    obs_date = row["obsdt"].strftime("%d %b %Y") if pd.notna(row["obsdt"]) else "n/a"
    wiki_url = row.get("wiki_url", "")

    wiki_block = ""
    if pd.notna(wiki_url) and wiki_url:
        wiki_block = (
            f'<a href="{wiki_url}" target="_blank" '
            f'style="color:#48c78e;text-decoration:none;font-weight:600;">'
            f'Wikipedia &rarr;</a>'
        )

    unique_id = f"img_{row['obs_id']}"

    return f"""
    <div style="font-family:sans-serif;min-width:220px;max-width:280px;">
        <div id="{unique_id}" style="text-align:center;font-size:12px;color:#888;margin-bottom:8px;">
            <i>Loading image...</i>
        </div>
        <div style="font-size:15px;font-weight:700;margin-bottom:2px;">
            {comname}
        </div>
        <div style="font-size:12px;color:#888;font-style:italic;margin-bottom:6px;">
            {sciname.title()}
        </div>
        <span style="display:inline-block;padding:2px 8px;border-radius:12px;
                      font-size:11px;font-weight:600;color:white;background:{badge_color};">
            {iucn}
        </span>
        <div style="margin-top:8px;font-size:12px;color:#555;">
            <b>Count:</b> {count} &nbsp;|&nbsp;
            <b>Observed:</b> {obs_date}
        </div>
        <div style="margin-top:6px;">{wiki_block}</div>
        <script>
            fetch('https://en.wikipedia.org/api/rest_v1/page/summary/{wiki_slug}')
                .then(r => r.json())
                .then(d => {{
                    const c = document.getElementById('{unique_id}');
                    if(d.thumbnail && d.thumbnail.source) {{
                        c.innerHTML = '<img src="' + d.thumbnail.source +
                            '" style="width:100%;max-height:160px;object-fit:cover;border-radius:8px;" />';
                    }} else {{ c.style.display = 'none'; }}
                }})
                .catch(() => {{
                    document.getElementById('{unique_id}').style.display = 'none';
                }});
        </script>
    </div>
    """


def build_map(df: pd.DataFrame, zoom: int = 6) -> folium.Map:
    """Builds a Folium map with IUCN-colored markers and layer control."""
    center_lat = df["lat"].mean()
    center_lng = df["lng"].mean()

    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=zoom,
        tiles="CartoDB positron",
    )

    feature_groups = {}
    for status in df["iucn_status"].unique():
        clean = str(status).title()
        fg = folium.FeatureGroup(name=clean)
        feature_groups[clean] = fg
        m.add_child(fg)

    for _, row in df.iterrows():
        clean_status = str(row["iucn_status"]).title()
        color = get_marker_color(clean_status)

        popup_html = build_popup_html(row)
        iframe = folium.IFrame(html=popup_html, width=260, height=240)
        popup = folium.Popup(iframe, max_width=260)

        folium.CircleMarker(
            location=[row["lat"], row["lng"]],
            radius=6,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.8,
            weight=1.5,
            popup=popup,
            tooltip=str(row["comname"]).title(),
        ).add_to(feature_groups[clean_status])

    folium.LayerControl(position="topright", collapsed=False).add_to(m)
    return m

# ---------------------------------------------------------------------------
# TAB 1: EXPLORE (main sightings map)
# ---------------------------------------------------------------------------
with tab_explore:
    df = get_sightings(days=days)

    if not df.empty:
        df["iucn_status"] = df["iucn_status"].fillna("Unknown").replace("None", "Unknown")

        m = build_map(df)
        st_folium(m, width="stretch", height=550, returned_objects=[])

        # --- Recent Sightings Table ---
        st.divider()
        st.markdown('<p class="section-header">Recent Sightings</p>', unsafe_allow_html=True)

        display_df = df[["comname", "sciname", "iucn_status", "howmany", "obsdt"]].copy()
        display_df.columns = ["Common Name", "Scientific Name", "IUCN Status", "Count", "Observed"]
        display_df["Common Name"] = display_df["Common Name"].str.title()
        display_df["Scientific Name"] = display_df["Scientific Name"].str.title()
        display_df["IUCN Status"] = display_df["IUCN Status"].str.title()

        st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
    else:
        st.info("No sightings found for this period. Try increasing the lookback window.")

# ---------------------------------------------------------------------------
# TAB 2: SPATIAL ANALYSIS (PostGIS features)
# ---------------------------------------------------------------------------
with tab_spatial:
    st.markdown(
        '<p class="section-header">Biodiversity Hotspots</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Areas with the highest species diversity, identified using "
        "PostGIS DBSCAN spatial clustering (ST_ClusterDBSCAN)."
    )

    hotspots_df = get_hotspots(days=30)

    if not hotspots_df.empty:
        # --- Hotspot map ---
        hotspot_map = folium.Map(
            location=[-28.5, 25.5],
            zoom_start=5,
            tiles="CartoDB positron",
        )

        max_species = hotspots_df["species_count"].max()

        for _, row in hotspots_df.iterrows():
            ratio = row["species_count"] / max_species
            radius = 10 + (ratio * 30)

            folium.CircleMarker(
                location=[row["center_lat"], row["center_lng"]],
                radius=radius,
                color="#1a1a2e",
                fill=True,
                fill_color="#48c78e",
                fill_opacity=0.4 + (ratio * 0.4),
                weight=2,
                tooltip=(
                    f"{int(row['species_count'])} species, "
                    f"{int(row['total_sightings'])} sightings"
                ),
            ).add_to(hotspot_map)

        st_folium(hotspot_map, width="stretch", height=450, returned_objects=[])

        # --- Hotspot table ---
        st.markdown(
            '<p class="section-header">Hotspot Rankings</p>',
            unsafe_allow_html=True,
        )
        hs_display = hotspots_df[["cluster_id", "species_count", "total_sightings", "center_lat", "center_lng"]].copy()
        hs_display.columns = ["Cluster", "Species Count", "Total Sightings", "Latitude", "Longitude"]
        hs_display["Latitude"] = hs_display["Latitude"].round(3)
        hs_display["Longitude"] = hs_display["Longitude"].round(3)
        hs_display = hs_display.reset_index(drop=True)
        hs_display.index = hs_display.index + 1
        hs_display.index.name = "Rank"
        st.dataframe(hs_display, use_container_width=True, height=300)
    else:
        st.info("Not enough data to compute hotspots. Try again after more observations accumulate.")

    # --- Nearby sightings ---
    st.divider()
    st.markdown(
        '<p class="section-header">Nearby Sightings Search</p>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Find birds within a given radius of any point. "
        "Uses PostGIS ST_DWithin with the GIST spatial index."
    )

    col_lat, col_lng, col_radius = st.columns(3)
    with col_lat:
        search_lat = st.number_input("Latitude", value=-33.92, format="%.4f")
    with col_lng:
        search_lng = st.number_input("Longitude", value=18.42, format="%.4f")
    with col_radius:
        search_radius = st.slider("Radius (km)", min_value=5, max_value=100, value=30)

    if st.button("Search nearby"):
        nearby_df = get_nearby_sightings(search_lat, search_lng, search_radius, days)

        if not nearby_df.empty:
            nearby_df["iucn_status"] = nearby_df["iucn_status"].fillna("Unknown")

            st.success(
                f"Found {len(nearby_df)} sightings within {search_radius}km "
                f"({nearby_df['speciescode'].nunique()} species)"
            )

            # Nearby map
            nearby_map = folium.Map(
                location=[search_lat, search_lng],
                zoom_start=10,
                tiles="CartoDB positron",
            )

            # Draw search radius circle
            folium.Circle(
                location=[search_lat, search_lng],
                radius=search_radius * 1000,
                color="#1a1a2e",
                fill=True,
                fill_opacity=0.05,
                weight=2,
                dash_array="5",
            ).add_to(nearby_map)

            # Center marker
            folium.Marker(
                location=[search_lat, search_lng],
                icon=folium.Icon(color="black", icon="crosshairs", prefix="fa"),
                tooltip="Search center",
            ).add_to(nearby_map)

            for _, row in nearby_df.iterrows():
                color = get_marker_color(str(row["iucn_status"]))
                folium.CircleMarker(
                    location=[row["lat"], row["lng"]],
                    radius=5,
                    color=color,
                    fill=True,
                    fill_color=color,
                    fill_opacity=0.8,
                    weight=1,
                    tooltip=f"{str(row['comname']).title()} ({row['dist_km']}km)",
                ).add_to(nearby_map)

            st_folium(nearby_map, width="stretch", height=450, returned_objects=[])

            # Nearby table
            nearby_display = nearby_df[["comname", "sciname", "iucn_status", "dist_km", "howmany", "obsdt"]].copy()
            nearby_display.columns = ["Common Name", "Scientific Name", "IUCN Status", "Distance (km)", "Count", "Observed"]
            nearby_display["Common Name"] = nearby_display["Common Name"].str.title()
            nearby_display["Scientific Name"] = nearby_display["Scientific Name"].str.title()
            nearby_display["IUCN Status"] = nearby_display["IUCN Status"].str.title()
            st.dataframe(nearby_display, use_container_width=True, hide_index=True, height=300)
        else:
            st.warning("No sightings found in that area. Try a larger radius or longer lookback.")

# ---------------------------------------------------------------------------
# TAB 3: SPECIES (leaderboard from view)
# ---------------------------------------------------------------------------
with tab_species:
    st.markdown(
        '<p class="section-header">Most Observed Species</p>',
        unsafe_allow_html=True,
    )
    st.caption("Ranked by total observation count across all time. Data from v_species_leaderboard view.")

    leaderboard_df = get_species_leaderboard(limit=50)

    if not leaderboard_df.empty:
        lb_display = leaderboard_df[[
            "comname", "sciname", "iucn_status",
            "total_observations", "total_individuals",
            "last_seen", "days_observed",
        ]].copy()
        lb_display.columns = [
            "Common Name", "Scientific Name", "IUCN Status",
            "Observations", "Individuals",
            "Last Seen", "Days Observed",
        ]
        lb_display["Common Name"] = lb_display["Common Name"].str.title()
        lb_display["Scientific Name"] = lb_display["Scientific Name"].str.title()
        lb_display["IUCN Status"] = lb_display["IUCN Status"].str.title()
        lb_display["Last Seen"] = pd.to_datetime(lb_display["Last Seen"]).dt.strftime("%d %b %Y")

        lb_display = lb_display.reset_index(drop=True)
        lb_display.index = lb_display.index + 1
        lb_display.index.name = "Rank"

        st.dataframe(lb_display, use_container_width=True, height=600)
    else:
        st.info("No species data available.")