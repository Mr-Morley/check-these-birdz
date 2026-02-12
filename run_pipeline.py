import os
from dotenv import load_dotenv
from src.ETL import ExtractTransformLoad

def main():
    load_dotenv()
    api_key = os.getenv("EBIRD_API_KEY")
        
    db_pass = os.getenv("POSTGRES_PASSWORD")
    db_url = f"postgresql://bird_user:{db_pass}@localhost:5432/bird_db"
    etl = ExtractTransformLoad(api_key=api_key, db_url=db_url)
    etl.process()

if __name__ == "__main__":
    main()
