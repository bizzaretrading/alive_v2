import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from fyers_apiv3 import fyersModel

# --- Add backend directory to path to import database module ---
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from database import pool
except ImportError as e:
    print(f"❌ Could not import 'database' module. Ensure it exists in the backend directory.")
    print(f"   Error details: {e}")
    sys.exit(1)

def get_symbols_from_latest_csv():
    """
    Finds the latest daily CSV and returns a list of symbols.
    This logic is adapted from the run_optimized_dashboard_v2.py script.
    """
    data_dir = Path("C:/Users/shash/Desktop/stock_selection_live/daily_consolidated_views")
    if not data_dir.is_dir():
        print(f"❌ Error: Data directory '{data_dir}' not found.")
        return []

    try:
        candidate_files = list(data_dir.glob("consolidated_stock_view_*-*_V2.csv"))
        if not candidate_files:
            print(f"❌ Error: No 'consolidated_stock_view_*.csv' files found in {data_dir}.")
            return []

        latest_file = max(candidate_files, key=lambda f: f.stat().st_mtime)
        print(f"✅ Using latest CSV file for symbols: {latest_file.name}")
        df = pd.read_csv(latest_file)
        
        # Assume first column is the symbol
        symbols = df.iloc[:, 0].astype(str).tolist()
        
        # Format symbols for Fyers API (e.g., 'RELIANCE' -> 'NSE:RELIANCE-EQ')
        formatted_symbols = []
        for symbol in symbols:
            wsym = symbol
            if not wsym.startswith("NSE:"):
                wsym = f"NSE:{wsym}"
            if not wsym.endswith("-EQ"):
                wsym = f"{wsym}-EQ"
            formatted_symbols.append(wsym)
            
        return formatted_symbols
    except Exception as e:
        print(f"❌ Error reading symbols from CSV: {e}")
        return []

def import_historical_data():
    """
    Main function to fetch and store historical data for the last 7 days.
    """
    print("--- Starting Historical Data Import ---")

    # 1. Read Credentials
    try:
        with open(SCRIPT_DIR / "fyers_appid.txt", "r") as f:
            client_id = f.read().strip()
        with open(SCRIPT_DIR / "fyers_token.txt", "r") as f:
            access_token = f.read().strip()
        print("✅ Credentials loaded successfully.")
    except FileNotFoundError as e:
        print(f"❌ Error: Could not find '{e.filename}'.")
        print("   Please run the main dashboard first to generate login files.")
        return

    # 2. Initialize Fyers Model
    fyers = fyersModel.FyersModel(client_id=client_id, is_async=False, token=access_token, log_path="")

    # 3. Get Symbol List
    symbols = get_symbols_from_latest_csv()
    if not symbols:
        print("❌ No symbols found to import. Aborting.")
        return
    print(f"Found {len(symbols)} symbols to process.")

    # 4. Define Date Range (last 7 days)
    today = datetime.now()
    range_to = today.strftime("%Y-%m-%d")
    range_from = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    print(f"Fetching data from {range_from} to {range_to}.")

    # 5. Process in Chunks
    chunk_size = 100
    total_candles_inserted = 0
    symbols_processed = 0

    for i in range(0, len(symbols), chunk_size):
        # This outer loop is for potential future batching, but API calls are per-symbol.
        # For now, it mainly serves to provide progress updates.
        chunk = symbols[i:i + chunk_size]
        print(f"\nProcessing chunk {i//chunk_size + 1}/{(len(symbols) + chunk_size - 1)//chunk_size} (symbols {i+1}-{min(i+chunk_size, len(symbols))})...")
        
        all_candles_for_chunk = []
        for symbol in chunk:
            data = {
                "symbol": symbol,
                "resolution": "1",
                "date_format": "1",
                "range_from": range_from,
                "range_to": range_to,
                "cont_flag": "1"
            }
            try:
                response = fyers.history(data=data)
                symbols_processed += 1
                if response.get("s") == "ok" and response.get("candles"):
                    for c in response["candles"]:
                        all_candles_for_chunk.append((
                            symbol, datetime.fromtimestamp(c[0]), c[1], c[2], c[3], c[4], c[5]
                        ))
                else:
                    print(f"   - No data for {symbol}: {response.get('errmsg', 'Unknown error')}")
            except Exception as e:
                print(f"   - API Error for {symbol}: {e}")

        if all_candles_for_chunk:
            print(f"   > Fetched {len(all_candles_for_chunk)} total candles for this chunk.")
            try:
                with pool.connection() as conn:
                    with conn.cursor() as cur:
                        query = """
                            INSERT INTO candles_1min (symbol, timestamp, open, high, low, close, volume)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (symbol, timestamp) DO NOTHING;
                        """
                        cur.executemany(query, all_candles_for_chunk)
                        print(f"   ✅ Successfully inserted {cur.rowcount} new candles into the database.")
                        total_candles_inserted += cur.rowcount
            except Exception as e:
                print(f"   ❌ Database Error for chunk: {e}")
        else:
            print("   > No new candle data was fetched for this chunk.")

    print("\n--- Historical Data Import Finished ---")
    print(f"Symbols processed: {symbols_processed}")
    print(f"Total new candles inserted: {total_candles_inserted}")

if __name__ == "__main__":
    if pool:
        import_historical_data()
        pool.close()
    else:
        print("❌ Could not establish database connection. Aborting import.") 