import os
import sys
from dotenv import load_dotenv
from src.ETL import SetupExtractTransformLoad 

def main():
    # Load local variables
    load_dotenv()
    
    api_key = os.getenv("EBIRD_API_KEY")
    #SUPABASE Session Connection URL.
    db_url = os.getenv("DATABASE_URL")
    # Initialize the ETL class with the e-bird API key and database URL
    etl = SetupExtractTransformLoad(ebird_key=api_key, db_url=db_url)
    
    try:
        print("Running Data Extraction Pipeline from Gateways to PostGIS...\n")
        etl.run() 
        print("ETL pipeline ran successfully.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1) 

if __name__ == "__main__":
    main()