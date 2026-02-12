import psycopg2
conn = psycopg2.connect("host=localhost dbname=simple_db user=admin password=password123")
print(f"✅ Connection Success! Database version: {conn.server_version}")