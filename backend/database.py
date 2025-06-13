import os
import time
import psycopg
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/trading_dashboard")

def connect_with_retry(retries=5, delay=5):
    """Attempt to connect to the database with retries."""
    for i in range(retries):
        try:
            # Add `check` to the pool to validate connections before use
            pool = ConnectionPool(
                DATABASE_URL, 
                min_size=1, 
                max_size=10, 
                timeout=10,
                check=ConnectionPool.check_connection
            )
            # Test connection
            with pool.connection():
                print("✅ Database connection successful.")
            return pool
        except psycopg.OperationalError as e:
            print(f"⚠️  Database connection failed: {e}")
            if i < retries - 1:
                print(f"   Retrying in {delay} seconds... ({i+1}/{retries})")
                time.sleep(delay)
            else:
                print("❌ Could not connect to the database after several retries. Aborting.")
                raise
    return None

# Initialize the pool globally with retry logic
pool = connect_with_retry()

def create_tables():
    """Creates the necessary database tables if they don't already exist."""
    if not pool:
        print("❌ Database pool is not available. Cannot create tables.")
        return

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS candles_1min (
                    id SERIAL PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    timestamp TIMESTAMPTZ NOT NULL,
                    open NUMERIC NOT NULL,
                    high NUMERIC NOT NULL,
                    low NUMERIC NOT NULL,
                    close NUMERIC NOT NULL,
                    volume BIGINT NOT NULL,
                    UNIQUE(symbol, timestamp)
                );
            """)
    print("✅ Table 'candles_1min' is ready.") 