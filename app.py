import streamlit as st
import folium
from streamlit_folium import st_folium
import pandas as pd
import sqlite3
import yaml
import plotly.express as px

def load_config(config_file):
    with open(config_file) as f:
        config = yaml.safe_load(f)
    return config

def load_data(db_file):
    conn = sqlite3.connect(db_file)
    df = pd.read_sql('SELECT * FROM bird_data', conn)
    conn.close()
    return df

def create_map(df, config):
    m = folium.Map(location=[-29.0, 24.0], zoom_start=config['map_zoom'])
    rows = df.shape[0]
    for i in range(rows):
        row = df.iloc[i]
        folium.Marker([row['lat'], row['lng']], popup=f"{row['comName']} at {row['locName']}").add_to(m)
    return m

def main_app():
    config = load_config('config.yaml')
    df = load_data('data.db')
    
    st.sidebar.title("Edit Config")
    new_map_title = st.sidebar.text_input("Map Title", config['headers']['map_title'])
    config['headers']['map_title'] = new_map_title
    
    st.title(config['headers']['map_title'])
    m = create_map(df, config)
    st_folium(m, width=700, height=500)
    
    selected_species = st.selectbox("Select Species", config['species'] + ["All Birds"])  # Added for all
    if selected_species == "All Birds":
        spot_df = df
    else:
        spot_df = df[df['comName'] == selected_species]
    st.subheader(config['headers']['chart_title'])
    fig = px.line(spot_df, x='obsDt', y='howMany', title='Seasonal Trends', color='comName' if selected_species == "All Birds" else None)
    st.plotly_chart(fig)
    st.dataframe(spot_df[['comName', 'obsDt', 'locName', 'lat', 'lng']])

if __name__ == "__main__":
    main_app()
