"""
A read-only dashboard displaying recent bird observations across South Africa.
Connects to a Supabase PostGIS database and visualizes the data.
"""

import streamlit as st
import pandas as pd
import pydeck as pdk
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Birdz",
    page_icon=":)",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------------------------

@st.cache_resource
def get_engine():
    """Creates a cached SQLAlchemy engine from Streamlit secrets."""
    return create_engine(
        st.secrets["database"]["url"],
        pool_pre_ping=True
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
        WHERE o.obsdt >= NOW() - MAKE_INTERVAL(days => :days)
        ORDER BY o.obsdt DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"days": days})

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

    [data-testid="stMetric"] {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border: 1px solid #dee2e6;
        border-radius: 12px;
        padding: 1rem 1.25rem;
    }

    [data-testid="stMetricValue"] {
        font-family: 'DM Serif Display', serif;
        color: #1a1a2e;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }

    [data-testid="stSidebar"] * {
        color: #e9ecef !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# IUCN COLOR MAP
# ---------------------------------------------------------------------------
IUCN_COLORS = {
    "least concern":          [72, 199, 142, 180],
    "near threatened":        [255, 193, 7, 180],
    "vulnerable":             [255, 152, 0, 180],
    "endangered":             [244, 67, 54, 180],
    "critically endangered":  [183, 28, 28, 200],
}
DEFAULT_COLOR = [158, 158, 158, 160]

def get_color(status: str) -> list:
    """Maps IUCN status to an RGBA color."""
    status_lower = str(status).lower()
    for key, color in IUCN_COLORS.items():
        if key in status_lower:
            return color
    return DEFAULT_COLOR

# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## Check These Birdz")
    st.caption("Live bird observations across South Africa")
    st.divider()
    days = st.slider("Lookback Window", min_value=1, max_value=14, value=7)
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
    f'<p class="subtitle">Live bird observations across South Africa — last {days} days</p>',
    unsafe_allow_html=True
)

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
        latest = df["obsdt"].max().strftime("%d %b %Y") if df["obsdt"].notna().any() else "N/A"
        st.metric("Latest Observation", latest)

    st.divider()

    # --- Map ---
    df["color"] = df["iucn_status"].apply(get_color)

    st.pydeck_chart(pdk.Deck(
        layers=[
            pdk.Layer(
                "ScatterplotLayer",
                data=df,
                get_position=["lng", "lat"],
                get_fill_color="color",
                get_radius=3000,
                pickable=True,
                auto_highlight=True,
                highlight_color=[255, 255, 255, 80],
            )
        ],
        initial_view_state=pdk.ViewState(
            longitude=df["lng"].mean(),
            latitude=df["lat"].mean(),
            zoom=5,
            pitch=0,
        ),
        tooltip={
            "html": """
                <div style="font-family: sans-serif; padding: 4px;">
                    <b style="font-size: 14px;">{comname}</b><br/>
                    <i style="color: #aaa;">{sciname}</i><br/>
                    <span>IUCN: {iucn_status}</span><br/>
                    <span>Count: {howmany}</span><br/>
                    <a href="{wiki_url}" target="_blank" style="color: #48c78e;">Wikipedia →</a>
                </div>
            """,
            "style": {
                "backgroundColor": "#1a1a2e",
                "color": "#e9ecef",
                "borderRadius": "8px",
            }
        },
        map_style="road",
    ))

    # --- Table ---
    st.divider()
    st.markdown("### Recent Sightings")

    display_df = df[["comname", "sciname", "iucn_status", "howmany", "obsdt"]].copy()
    display_df.columns = ["Common Name", "Scientific Name", "IUCN Status", "Count", "Observed"]
    display_df["Common Name"] = display_df["Common Name"].str.title()
    display_df["Scientific Name"] = display_df["Scientific Name"].str.title()

    st.dataframe(display_df, width="stretch", hide_index=True, height=400)
else:
    st.info("No sightings found for this period. Try increasing the lookback window.")