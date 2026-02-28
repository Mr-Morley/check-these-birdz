"""
A read-only dashboard displaying recent bird observations across South Africa.
Connects to a Supabase PostGIS database and visualizes the data.
"""

import streamlit as st
import pandas as pd
import pydeck as pdk
import requests
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
        WHERE o.obsdt >= NOW() - MAKE_INTERVAL(days => :days)
        ORDER BY o.obsdt DESC
    """)
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"days": days})


@st.cache_data(ttl=86400, show_spinner=False)
def get_wiki_image(species_name: str) -> str | None:
    """Fetches the main image URL for a species from Wikipedia."""
    api_url = "https://en.wikipedia.org/api/rest_v1/page/summary/"
    slug = species_name.replace(" ", "_")
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

    /* Bird detail card */
    .bird-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border: 1px solid #dee2e6;
        border-radius: 16px;
        padding: 1.5rem;
        margin-top: 0.5rem;
    }

    .bird-card h2 {
        font-family: 'DM Serif Display', serif;
        color: #1a1a2e;
        margin: 0 0 0.25rem 0;
        font-size: 1.6rem;
    }

    .bird-card .sciname {
        color: #6c757d;
        font-style: italic;
        margin-bottom: 0.75rem;
    }

    .bird-card .detail-row {
        display: flex;
        gap: 1.5rem;
        flex-wrap: wrap;
        margin: 0.75rem 0;
    }

    .bird-card .detail-item {
        font-size: 0.9rem;
        color: #495057;
    }

    .bird-card .detail-item strong {
        color: #1a1a2e;
    }

    .iucn-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
        color: white;
    }

    .bird-card img {
        border-radius: 12px;
        width: 100%;
        max-height: 280px;
        object-fit: cover;
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

IUCN_BADGE_COLORS = {
    "least concern":          "#48c78e",
    "near threatened":        "#ffc107",
    "vulnerable":             "#ff9800",
    "endangered":             "#f44336",
    "critically endangered":  "#b71c1c",
}


def get_color(status: str) -> list:
    """Maps IUCN status to an RGBA color."""
    status_lower = str(status).lower()
    for key, color in IUCN_COLORS.items():
        if key in status_lower:
            return color
    return DEFAULT_COLOR


def get_badge_color(status: str) -> str:
    """Maps IUCN status to a hex color for badges."""
    status_lower = str(status).lower()
    for key, color in IUCN_BADGE_COLORS.items():
        if key in status_lower:
            return color
    return "#9e9e9e"


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## Check These Birdz")
    st.caption("Live bird observations across South Africa")
    st.divider()
    days = st.slider("Lookback Window", min_value=1, max_value=14, value=7)
    st.divider()

    # IUCN legend
    st.markdown("**IUCN Status Legend**")
    for label, rgba in IUCN_COLORS.items():
        hex_col = "#{:02x}{:02x}{:02x}".format(*rgba[:3])
        st.markdown(
            f'<span style="color:{hex_col}; font-size:1.3rem;">●</span> '
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
    f'<p class="subtitle">Live bird observations across South Africa — last {days} days</p>',
    unsafe_allow_html=True,
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
        latest = (
            df["obsdt"].max().strftime("%d %b %Y")
            if df["obsdt"].notna().any()
            else "N/A"
        )
        st.metric("Latest Observation", latest)

    st.divider()

    # --- Map + Detail Panel ---
    # Prepare map data
    df["color"] = df["iucn_status"].apply(get_color)

    # Build a unique-species list for the selectbox (sorted alphabetically)
    species_options = (
        df[["speciescode", "comname", "sciname"]]
        .drop_duplicates(subset="speciescode")
        .sort_values("comname")
    )
    species_display = ["Click a species below to view details"] + [
        row["comname"] for _, row in species_options.iterrows()
    ]

    map_col, detail_col = st.columns([3, 2], gap="large")

    with map_col:
        st.pydeck_chart(
            pdk.Deck(
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
                    "html": (
                        '<div style="font-family:sans-serif;padding:4px;">'
                        "<b>{comname}</b><br/>"
                        '<i style="color:#aaa;">{sciname}</i><br/>'
                        "Count: {howmany}"
                        "</div>"
                    ),
                    "style": {
                        "backgroundColor": "#1a1a2e",
                        "color": "#e9ecef",
                        "borderRadius": "8px",
                    },
                },
                map_style="road",
            )
        )

    with detail_col:
        st.markdown("#### 🔍 Bird Detail")
        selected = st.selectbox(
            "Select a species",
            species_display,
            label_visibility="collapsed",
        )

        if selected != species_display[0]:
            # Find matching rows
            bird_rows = df[df["comname"] == selected]
            bird = bird_rows.iloc[0]

            iucn = bird["iucn_status"] if pd.notna(bird["iucn_status"]) else "Unknown"
            badge_color = get_badge_color(iucn)
            sighting_count = len(bird_rows)
            total_count = (
                int(bird_rows["howmany"].sum())
                if bird_rows["howmany"].notna().any()
                else 0
            )
            last_seen = (
                bird_rows["obsdt"].max().strftime("%d %b %Y")
                if bird_rows["obsdt"].notna().any()
                else "N/A"
            )

            # Fetch Wikipedia image
            image_url = get_wiki_image(bird["comname"])

            # Build card
            image_html = ""
            if image_url:
                image_html = f'<img src="{image_url}" alt="{bird["comname"]}"/>'

            wiki_link = ""
            if pd.notna(bird["wiki_url"]):
                wiki_link = (
                    f'<a href="{bird["wiki_url"]}" target="_blank" '
                    f'style="color:#48c78e;text-decoration:none;font-weight:500;">'
                    f"Read on Wikipedia →</a>"
                )

            card_html = f"""
            <div class="bird-card">
                {image_html}
                <h2 style="margin-top:{'0.75rem' if image_url else '0'};">
                    {bird["comname"].title()}
                </h2>
                <div class="sciname">{bird["sciname"].title()}</div>
                <span class="iucn-badge" style="background:{badge_color};">
                    {iucn.title()}
                </span>
                <div class="detail-row">
                    <div class="detail-item">
                        <strong>Sightings:</strong> {sighting_count}
                    </div>
                    <div class="detail-item">
                        <strong>Individuals:</strong> {total_count}
                    </div>
                    <div class="detail-item">
                        <strong>Last seen:</strong> {last_seen}
                    </div>
                </div>
                {wiki_link}
            </div>
            """
            st.markdown(card_html, unsafe_allow_html=True)
        else:
            st.caption(
                "Select a species from the dropdown above — or hover over "
                "dots on the map to identify a bird, then find it here."
            )

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

    st.dataframe(display_df, use_container_width=True, hide_index=True, height=400)
else:
    st.info(
        "No sightings found for this period. Try increasing the lookback window."
    )