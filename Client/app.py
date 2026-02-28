"""
A read-only dashboard displaying recent bird observations across South Africa.
Connects to a Supabase PostGIS database and visualizes the data.
"""

import streamlit as st
import pandas as pd
import requests
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Birdz",
    page_icon=":)",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------------------------

@st.cache_resource
def get_engine():
    """Creates a cached SQLAlchemy engine from Streamlit secrets."""
    return create_engine(
        st.secrets["database"]["url"],
        pool_pre_ping=True,
    )

# ---------------------------------------------------------------------------
# CACHED QUERIES
# ---------------------------------------------------------------------------

@st.cache_data(ttl=3600, show_spinner="Fetching bird sightings...")
def get_sightings(days: int) -> pd.DataFrame:
    """Fetches recent sightings joined with species metadata."""
    engine = get_engine()
    query = text("""
        SELECT
            o.obs_id,
            o.speciescode,
            s.comname,
            s.sciname,
            s.iucn_status,
            s.wiki_url,
            o.howmany,
            o.lat,
            o.lng,
            o.obsdt
        FROM observations o
        JOIN species s ON o.speciescode = s.speciescode
        WHERE o.obsdt >= (CURRENT_DATE - :days)
        ORDER BY o.obsdt DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"days": days})



@st.cache_data(ttl=86400, show_spinner=True)
def get_wiki_image(sciname: str) -> str | None:
    """Fetches the main image URL for a species using its scientific name."""
    api_url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
    # Scientific names are much cleaner for Wikipedia URLs
    slug = sciname.replace(" ", "_").capitalize()
    try:
        resp = requests.get(f"{api_url}{slug}", timeout=5)
        if resp.ok:
            data = resp.json()
            return data.get("thumbnail", {}).get("source")
    except requests.RequestException:
        pass
    return None

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

    /* --- Metrics: force dark text on light background --- */
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

    /* --- Sidebar: dark bg, light text, but don't clobber everything --- */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }

    [data-testid="stSidebar"] [data-testid="stMarkdown"] p,
    [data-testid="stSidebar"] [data-testid="stMarkdown"] span:not(.iucn-dot),
    [data-testid="stSidebar"] .stSlider label,
    [data-testid="stSidebar"] h2,
    [data-testid="stSidebar"] a {
        color: #e9ecef !important;
    }

    /* IUCN legend dots keep their own color */
    .iucn-dot {
        color: inherit !important;
    }
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

    st.markdown("**IUCN Status Legend**")
    for label, hex_color in IUCN_COLORS_HEX.items():
        st.markdown(
            f'<span class="iucn-dot" style="color:{hex_color};'
            f'font-size:1.4rem;line-height:1;">●</span>&nbsp;'
            f'{label.title()}',
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown(
        "Data sourced from [eBird](https://ebird.org), "
        "enriched via [Wikipedia](https://en.wikipedia.org)."
    )

# ---------------------------------------------------------------------------
# FETCH DATA
# ---------------------------------------------------------------------------
df = get_sightings(days=days)

# ---------------------------------------------------------------------------
# HEADER
# ---------------------------------------------------------------------------
st.markdown('<p class="main-title">Check These Birdz</p>', unsafe_allow_html=True)
st.markdown(
    f'<p class="subtitle">Live bird observations across South Africa'
    f' — last {days} days</p>',
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def build_popup_html(row: pd.Series, image_url: str | None) -> str:
    """Builds the HTML for a Folium click-popup card."""
    comname = str(row["comname"]).title()
    sciname = str(row["sciname"]).title()
    iucn = (
        str(row["iucn_status"]).title()
        if pd.notna(row["iucn_status"])
        else "Unknown"
    )
    badge_color = get_marker_color(str(row.get("iucn_status", "")))
    count = row["howmany"] if pd.notna(row["howmany"]) else "—"
    obs_date = (
        row["obsdt"].strftime("%d %b %Y")
        if pd.notna(row["obsdt"])
        else "—"
    )
    wiki_url = row.get("wiki_url", "")

    img_block = ""
    if image_url:
        img_block = (
            f'<img src="{image_url}" '
            f'style="width:100%;max-height:160px;object-fit:cover;'
            f'border-radius:8px;margin-bottom:8px;" />'
        )

    wiki_block = ""
    if pd.notna(wiki_url) and wiki_url:
        wiki_block = (
            f'<a href="{wiki_url}" target="_blank" '
            f'style="color:#48c78e;text-decoration:none;font-weight:600;">'
            f'Wikipedia →</a>'
        )

    return f"""
    <div style="font-family:sans-serif;min-width:220px;max-width:280px;">
        {img_block}
        <div style="font-size:15px;font-weight:700;margin-bottom:2px;">
            {comname}
        </div>
        <div style="font-size:12px;color:#888;font-style:italic;
                    margin-bottom:6px;">
            {sciname}
        </div>
        <span style="display:inline-block;padding:2px 8px;border-radius:12px;
                     font-size:11px;font-weight:600;color:white;
                     background:{badge_color};">
            {iucn}
        </span>
        <div style="margin-top:8px;font-size:12px;color:#555;">
            <b>Count:</b> {count} &nbsp;|&nbsp;
            <b>Observed:</b> {obs_date}
        </div>
        <div style="margin-top:6px;">{wiki_block}</div>
    </div>
    """


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
if not df.empty:

    # --- Metrics ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Sightings", f"{len(df):,}")
    with col2:
        st.metric("Unique Species", df["speciescode"].nunique())
    with col3:
        total = int(df["howmany"].sum()) if df["howmany"].notna().any() else 0
        st.metric("Individual Birds", f"{total:,}")
    with col4:
        latest = (
            df["obsdt"].max().strftime("%d %b %Y")
            if df["obsdt"].notna().any()
            else "N/A"
        )
        st.metric("Latest Observation", latest)

    st.divider()

    # --- Folium Map with click popups ---
    # Pre-fetch images once per species (cached for 24h)
# --- Folium Map with click popups ---
    # Pre-fetch images once per species using Scientific Name
    species_images: dict[str, str | None] = {}
    for sciname in df["sciname"].unique():
        species_images[sciname] = get_wiki_image(sciname)

    center_lat = df["lat"].mean()
    center_lng = df["lng"].mean()

    m = folium.Map(
        location=[center_lat, center_lng],
        zoom_start=6,
        tiles="CartoDB positron",
    )

    # 1. Create a FeatureGroup for each IUCN status present in the data
    feature_groups = {}
    statuses = df["iucn_status"].fillna("Unknown").unique()
    for status in statuses:
        # Title-case the status for the Layer Control menu
        clean_status = str(status).title()
        fg = folium.FeatureGroup(name=clean_status)
        feature_groups[clean_status] = fg
        m.add_child(fg)

    # 2. Add markers to their respective FeatureGroup
    for _, row in df.iterrows():
        raw_status = str(row.get("iucn_status", ""))
        clean_status = raw_status.title() if raw_status else "Unknown"
        color = get_marker_color(raw_status)
        
        # Get image using scientific name
        image_url = species_images.get(row["sciname"])
        popup_html = build_popup_html(row, image_url)
        
        # Wrap HTML in an IFrame to ensure images aren't blocked/stripped
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

    # 3. Add the Layer Control so users can toggle IUCN statuses
    folium.LayerControl(position='topright', collapsed=False).add_to(m)

    st_folium(m, width="stretch", height=550, returned_objects=[])
    # --- Table ---
    st.divider()
    st.markdown("### Recent Sightings")

    display_df = df[
        ["comname", "sciname", "iucn_status", "howmany", "obsdt"]
    ].copy()
    display_df.columns = [
        "Common Name",
        "Scientific Name",
        "IUCN Status",
        "Count",
        "Observed",
    ]
    display_df["Common Name"] = display_df["Common Name"].str.title()
    display_df["Scientific Name"] = display_df["Scientific Name"].str.title()

    st.dataframe(display_df, width="stretch", hide_index=True, height=400)
else:
    st.info(
        "No sightings found for this period. Try increasing the lookback window."
    )