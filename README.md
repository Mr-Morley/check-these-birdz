## Project: Check-These-Birdz

### Description

This project is a data pipeline and web application designed to track and visualize recent bird sightings. It extracts data from the eBird API, processes it through an ETL pipeline, and stores it in a PostgreSQL database. The data is ultimately displayed on a Streamlit-based map interface.

### Prerequisites

* Python 3.12+
* Docker and Docker Compose
* eBird API Key

---

### Setup and Installation

1. **Virtual Environment**
Initialize the Python environment and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install sqlalchemy psycopg2-binary streamlit

```


2. **Infrastructure**
Start the database and associated services using the management script:
```bash
./scripts/docker-manage.sh up

```


3. **Running the Pipeline**
Execute the ETL process to populate the database:
```bash
python3 run_pipeline.py

```



---

### Database Management with pgAdmin

To inspect the stored bird sightings visually, use the pgAdmin web interface included in the Docker configuration.

**Connection Details:**

* **URL:** `http://localhost:8080`
* **Login Email:** (See your docker-compose.yml environment variables)
* **Login Password:** (See your docker-compose.yml environment variables)

**Steps to Connect:**

1. Open pgAdmin in your browser.
2. Right-click **Servers** > **Register** > **Server...**
3. Under the **General** tab, name it "BirdDB".
4. Under the **Connection** tab:
* **Host name/address:** `db` (if connecting within Docker) or `localhost` (if connecting from your host machine).
* **Port:** `5432`
* **Maintenance database:** `postgres` (or your specific DB name).
* **Username:** (As defined in your .env or compose file).
* **Password:** (As defined in your .env or compose file).


5. Save the connection. You can now expand the tables under **Schemas > public > Tables** to view the sighting data.

---

### Shutdown

To stop the database services:

```bash
./scripts/docker-manage.sh down

```
