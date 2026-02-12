import psycopg2

# Connect to your running "appliance"
conn = psycopg2.connect("host=localhost dbname=simple_db user=admin password=password123")
cur = conn.cursor()

# Create a table (The Blueprint)
cur.execute("""
    CREATE TABLE IF NOT EXISTS bird_sightings (
        id SERIAL PRIMARY KEY,
        species_name VARCHAR(100),
        location VARCHAR(100),
        observed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
""")

# Insert a row (The Data)
cur.execute("INSERT INTO bird_sightings (species_name, location) VALUES (%s, %s)", 
            ("Hadeda Ibis", "Cape Town"))

conn.commit()
print("✅ Table created and first Hadeda spotted!")
cur.close()
conn.close()