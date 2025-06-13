from flask import Flask, render_template_string, send_from_directory, request
from flask_socketio import SocketIO, emit
import threading
import time
import json
import pandas as pd
import os
import random
from pathlib import Path
from datetime import datetime, timezone

# Get the directory where the script is located
SCRIPT_DIR = Path(__file__).resolve().parent

# This will be set by run_optimized_dashboard.py before server starts
TARGET_CSV_FILE = None 

# Try to import your existing Fyers WebSocket singleton
fyers_available = False
try:
    from fyers_ws_singleton import start_websocket, get_ltp_data
    fyers_available = True
    print("✅ Fyers WebSocket imported successfully")
except ImportError:
    print("⚠️  Fyers WebSocket not available - will use mock data")
    
    # Create mock functions
    def start_websocket(token, symbols):
        print("Mock: WebSocket started")
        return True
        
    def get_ltp_data():
        """Mock function that returns sample trading data"""
        mock_symbols = ['NSE:RELIANCE-EQ', 'NSE:TCS-EQ', 'NSE:HDFCBANK-EQ', 'NSE:INFY-EQ', 'NSE:HINDUNILVR-EQ']
        mock_data = {}
        for symbol in mock_symbols:
            base_price = random.uniform(100, 3000)
            change_pct = random.uniform(-10, 15)
            mock_data[symbol] = {
                'ltp': round(base_price, 2),
                'chp': round(change_pct, 2),
                'vol_traded_today': random.randint(100000, 5000000),
                'high_price': round(base_price * 1.05, 2),
                'low_price': round(base_price * 0.95, 2),
                'open_price': round(base_price / (1 + change_pct/100), 2)
            }
        return mock_data, set()

# --- Database Integration ---
from database import pool, create_tables
# --------------------------

# --- Candle Aggregation ---
live_candles = {} # Holds the current 1-min candle data for each symbol
# Example: {'NSE:RELIANCE-EQ': {'timestamp': ..., 'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ...}}
# --------------------------

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-trading-dashboard-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global variables
symbols_data = {}
csv_data = {}
websocket_started = False
connected_clients = set()
active_alerts = [] # To store active alerts
alert_id_counter = 0 # Simple counter for unique alert IDs

# --- Database Writing Helper ---
def save_candle_to_db(symbol, candle_data):
    """Saves a completed candle to the PostgreSQL database."""
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO candles_1min (symbol, timestamp, open, high, low, close, volume)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (symbol, timestamp) DO NOTHING;
                """, (
                    symbol,
                    candle_data['timestamp'],
                    candle_data['open'],
                    candle_data['high'],
                    candle_data['low'],
                    candle_data['close'],
                    candle_data['volume']
                ))
    except Exception as e:
        print(f"Error saving candle for {symbol}: {e}")
# -----------------------------

def load_csv_data():
    """Load static data from CSV file with proper error handling"""
    global csv_data, TARGET_CSV_FILE # Ensure TARGET_CSV_FILE is accessible
    try:
        # Use the dynamically set path
        csv_path = TARGET_CSV_FILE 
        
        if not csv_path or not os.path.exists(csv_path):
            print(f"⚠️  Warning: CSV file '{str(csv_path)}' not found or not specified.")
            if not fyers_available:
                print("ℹ️  Fyers not available and CSV missing. Creating mock data.")
                create_mock_data() # This populates global csv_data
            else:
                print("ℹ️  Fyers is available, but CSV data is missing. Proceeding without static CSV data.")
                csv_data = {} # Ensure csv_data is empty if no file and no mock
            return list(csv_data.keys()) # Return keys from (potentially mock or empty) csv_data
            
        print(f"ℹ️  Loading data from CSV: {csv_path}")
        df = pd.read_csv(csv_path)
        df.iloc[:, 0] = df.iloc[:, 0].astype(str)
        
        # Map CSV columns to dashboard fields
        column_mapping = {
            'Announcement Weight': 'newsWeight',
            'chart-ink strategy': 'chartStrategy',
            'Announcement Description': 'description',
            'Nse_pre market': 'premarket',
            'Open in Prev Range Top 20%': 'sopen',
            'Gap %': 'gap',
            'PDC strong close': 'spdc',
            'Prev_High': 'pdh'
        }
        
        for idx, row in df.iterrows():
            symbol = row.iloc[0]
            # Convert symbol to Fyers format
            wsym = symbol
            if not wsym.startswith("NSE:"):
                wsym = f"NSE:{wsym}" if not wsym.endswith("-EQ") else f"NSE:{wsym}"
            if not wsym.endswith("-EQ"):
                wsym = f"{wsym}-EQ"
            
            # Process static data
            static_data = {}
            for col_idx, col_name in enumerate(df.columns[1:], 1):
                if col_name in ['Announcement Links', 'Announcement Text']:
                    continue
                    
                value = row.iloc[col_idx]
                if pd.isna(value):
                    value = None
                elif col_name == 'chart-ink strategy':
                    # Keep the original text as-is, don't extract numbers
                    static_data['chartStrategy'] = str(value) if value and str(value) != 'nan' else ''
                elif col_name.strip().lower() == 'announcement weight':
                    # Keep announcement weight as numeric value, map to newsWeight
                    try:
                        # More robust parsing to handle non-numeric strings like '-'
                        if value is None or (isinstance(value, str) and value.strip() in ['-', '']):
                            static_data['newsWeight'] = 0.0
                        else:
                            static_data['newsWeight'] = float(value)
                    except (ValueError, TypeError):
                        static_data['newsWeight'] = 0.0
                elif col_name == 'Gap %':
                    try:
                        if isinstance(value, str):
                            value = value.replace('%', '')
                        static_data['gap'] = float(value) if value else 0
                    except:
                        static_data['gap'] = 0
                elif col_name == 'Prev_High': # Corrected PDH processing to use underscore
                    try:
                        static_data['pdh'] = float(value) if value else 0.0
                    except:
                        static_data['pdh'] = 0.0
                elif col_name in ['Nse_pre market', 'Open in Prev Range Top 20%', 'PDC strong close']:
                    static_data[column_mapping[col_name]] = 'yes' if str(value).lower() in ['yes', 'true', '1'] else 'no'
                else:
                    mapped_key = column_mapping.get(col_name, col_name.lower().replace(' ', '_'))
                    static_data[mapped_key] = value
            
            # Set announcement based on description
            static_data['announcement'] = 'yes' if static_data.get('description') and static_data['description'] != '-' else 'no'
            
            csv_data[wsym] = static_data
            
        print(f"Loaded {len(csv_data)} symbols from CSV")
        # Sample logging for PDH values after CSV load
        sample_symbols_to_log = list(csv_data.keys())[:5]
        for s_key in sample_symbols_to_log:
            print(f"CSV Load Check: Symbol: {s_key}, PDH: {csv_data[s_key].get('pdh')}")
        return list(csv_data.keys())
    except Exception as e:
        print(f"Error loading CSV: {e}")
        if not fyers_available: # If CSV loading fails catastrophically
            print("ℹ️  Fallback to mock data due to CSV loading error and Fyers not available.")
            create_mock_data()
        else:
            csv_data = {}
        return list(csv_data.keys())

def start_fyers_websocket():
    """Start Fyers WebSocket connection with error handling"""
    global websocket_started
    if not websocket_started:
        try:
            token_path = SCRIPT_DIR / "fyers_token.txt"
            if not os.path.exists(token_path):
                print("Warning: fyers_token.txt not found, using mock data")
                return False
                
            with open(token_path, "r") as f:
                access_token = f.read().strip()
            
            symbols = load_csv_data()
            if symbols:
                print(f"Starting WebSocket for {len(symbols)} symbols")
                start_websocket(access_token, symbols)
                websocket_started = True
                print("Fyers WebSocket started successfully")
                return True
            else:
                print("No symbols loaded, cannot start WebSocket")
                return False
        except Exception as e:
            print(f"Error starting WebSocket: {e}")
            return False

def data_stream_thread():
    """Background thread to stream data to clients with optimized updates and strategy grouping"""
    last_emission = {}
    first_data_received = False # Flag for one-time message
    
    while True:
        try:
            if not connected_clients:
                time.sleep(1)
                continue
                
            ltp_data, invalid_symbols = get_ltp_data()
            
            # --- One-time check to confirm data stream is live ---
            if ltp_data and not first_data_received:
                print("✅ First data packet received from Fyers WebSocket. Data stream is live.")
                first_data_received = True
            # ----------------------------------------------------

            # --- Candle Aggregation Logic ---
            current_utc_time = datetime.now(timezone.utc)
            current_minute_timestamp = current_utc_time.replace(second=0, microsecond=0)

            for symbol, data in ltp_data.items():
                if not isinstance(data, dict) or 'ltp' not in data:
                    continue

                ltp = data.get('ltp', 0)
                # --- Check for alerts on this tick ---
                check_alerts(symbol, ltp)
                # -------------------------------------

                # Use 'vol_traded_today' as Fyers WS provides this
                total_volume = data.get('vol_traded_today', 0)

                if symbol not in live_candles:
                    # First tick for this symbol this run
                    live_candles[symbol] = {
                        "timestamp": current_minute_timestamp,
                        "open": ltp,
                        "high": ltp,
                        "low": ltp,
                        "close": ltp,
                        "start_volume": total_volume, # Store volume at the start of the candle
                        "volume": 0 # This will be the calculated volume for the minute
                    }
                else:
                    # Existing symbol, check if minute has changed
                    last_candle = live_candles[symbol]
                    if last_candle['timestamp'] < current_minute_timestamp:
                        # Minute has rolled over, finalize and save the old candle
                        last_candle['volume'] = total_volume - last_candle['start_volume']
                        if last_candle['volume'] < 0: last_candle['volume'] = 0 # In case of reset
                        
                        save_candle_to_db(symbol, last_candle)
                        
                        # Start a new candle
                        live_candles[symbol] = {
                            "timestamp": current_minute_timestamp,
                            "open": ltp,
                            "high": ltp,
                            "low": ltp,
                            "close": ltp,
                            "start_volume": total_volume,
                            "volume": 0
                        }
                    else:
                        # Update the current candle
                        last_candle['high'] = max(last_candle['high'], ltp)
                        last_candle['low'] = min(last_candle['low'], ltp)
                        last_candle['close'] = ltp
                        # Volume is calculated at the end of the minute
                        current_candle_volume = total_volume - last_candle['start_volume']
                        last_candle['volume'] = current_candle_volume if current_candle_volume >= 0 else 0
            # ----------------------------------
            
            if ltp_data:
                # This will hold the data grouped by strategy
                processed_data_by_strategy = {}
                current_time = time.time()
                
                for symbol, data in ltp_data.items():
                    if isinstance(data, dict):
                        # --- FIX: Use 'chp' from Fyers for change percentage ---
                        change_percent = data.get('chp', 0)
                        
                        # Combine live data with static CSV data
                        combined_data = {
                            'symbol': symbol,
                            'ltp': data.get('ltp', 0),
                            'change': change_percent, # Use reliable value from API
                            'volume': data.get('vol_traded_today', 0),
                            'high': data.get('high_price', 0),
                            'low': data.get('low_price', 0),
                            'open': data.get('open_price', 0),
                            'last_update': current_time
                        }
                        
                        symbol_static_data = csv_data.get(symbol, {})
                        combined_data.update(symbol_static_data)
                        
                        # PDH Crossing Logic
                        pdh_value = symbol_static_data.get('pdh', 0.0)
                        current_ltp = combined_data.get('ltp', 0.0)
                        crossed_pdh_status = '-'
                        pdh_alert = False

                        if pdh_value > 0:
                            crossed_pdh_status = 'yes' if current_ltp > pdh_value else 'no'
                            last_symbol_data = last_emission.get(symbol, {})
                            previous_ltp = last_symbol_data.get('ltp')
                            
                            if previous_ltp is not None and previous_ltp <= pdh_value and current_ltp > pdh_value:
                                pdh_alert = True
                        
                        combined_data['pdh'] = pdh_value
                        combined_data['crossed_pdh'] = crossed_pdh_status
                        combined_data['pdh_alert'] = pdh_alert
                        
                        # Check if data has changed significantly
                        last_data = last_emission.get(symbol, {})
                        if (not last_data or 
                            abs(combined_data.get('ltp', 0) - last_data.get('ltp', 0)) > 0.01 or
                            abs(combined_data.get('change', 0) - last_data.get('change', 0)) > 0.01 or
                            pdh_alert):

                            # Group by strategy, splitting comma-separated strategies
                            raw_strategy = symbol_static_data.get('chartStrategy', 'Uncategorized')
                            strategies = [s.strip() for s in raw_strategy.split(',')]

                            for strategy in strategies:
                                if not strategy: continue # Skip empty strings
                                if strategy not in processed_data_by_strategy:
                                    processed_data_by_strategy[strategy] = {}
                                
                                processed_data_by_strategy[strategy][symbol] = combined_data
                            
                            last_emission[symbol] = combined_data.copy()

                if processed_data_by_strategy:
                    socketio.emit('stock_update', processed_data_by_strategy)
            
            # Reduce sleep time for more frequent updates if needed
            time.sleep(1) # Emits updates every 1 second if there are changes

        except Exception as e:
            print(f"Error in data stream thread: {e}")
            time.sleep(5) # Avoid rapid-fire errors

@app.route('/api/columns')
def get_columns():
    """Get available columns from CSV"""
    if csv_data:
        sample_data = next(iter(csv_data.values()))
        columns = ['symbol', 'ltp', 'change', 'volume', 'high', 'low', 'open'] + list(sample_data.keys())
        # Ensure new keys are in the columns list for /api/columns if they aren't dynamically added from sample_data
        if 'pdh' not in columns: columns.append('pdh')
        if 'crossed_pdh' not in columns: columns.append('crossed_pdh')
        return json.dumps(list(dict.fromkeys(columns))) # Ensure unique columns
    return json.dumps(['symbol', 'ltp', 'change', 'volume', 'high', 'low', 'open', 'pdh', 'crossed_pdh'])

@app.route('/api/stats')
def get_stats():
    """Get dashboard statistics"""
    try:
        ltp_data, invalid_symbols = get_ltp_data()
        total_symbols = len(csv_data)
        active_symbols = len(ltp_data)
        invalid_count = len(invalid_symbols)
        
        return json.dumps({
            'total_symbols': total_symbols,
            'active_symbols': active_symbols,
            'invalid_symbols': invalid_count,
            'status': 'connected' if websocket_started else 'disconnected'
        })
    except Exception as e:
        return json.dumps({
            'error': str(e),
            'status': 'error'
        })

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f'Client connected: {request.sid}')
    connected_clients.add(request.sid)
    emit('connection_status', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    global connected_clients
    if request.sid in connected_clients:
        connected_clients.remove(request.sid)
    print(f"Client disconnected: {request.sid}. Total clients: {len(connected_clients)}")

@socketio.on('request_initial_data')
def handle_initial_data():
    """Handle request for initial full data set, grouped by strategy."""
    print(f"Client {request.sid} requested initial data.")
    
    # Ensure CSV data is loaded before proceeding
    if not csv_data:
        print("Warning: Initial data requested but CSV data is not loaded.")
        load_csv_data() 
    
    initial_data_by_strategy = {}
    
    # Get the latest LTP data to ensure we send current prices
    ltp_data, _ = get_ltp_data()

    for symbol, static_info in csv_data.items():
        strategy = static_info.get('chartStrategy', 'Uncategorized')
        
        # Combine with latest LTP data if available
        live_data = ltp_data.get(symbol, {})
        
        # --- FIX: Use 'chp' from Fyers for change percentage ---
        change_percent = live_data.get('chp', 0)

        combined_data = {
            'symbol': symbol,
            'ltp': live_data.get('ltp', 0),
            'change': change_percent, # Use reliable value from API
            'volume': live_data.get('vol_traded_today', 0),
            'high': live_data.get('high_price', 0),
            'low': live_data.get('low_price', 0),
            'open': live_data.get('open_price', 0)
        }
        combined_data.update(static_info)
        
        # Add PDH status for initial load
        pdh_value = static_info.get('pdh', 0.0)
        current_ltp = combined_data.get('ltp', 0.0)
        crossed_pdh_status = '-'
        if pdh_value > 0:
            crossed_pdh_status = 'yes' if current_ltp > pdh_value else 'no'
        combined_data['pdh'] = pdh_value
        combined_data['crossed_pdh'] = crossed_pdh_status
        combined_data['pdh_alert'] = False # No alert on initial load

        # Group by strategy, splitting comma-separated strategies
        raw_strategy = static_info.get('chartStrategy', 'Uncategorized')
        strategies = [s.strip() for s in raw_strategy.split(',')]

        for strategy in strategies:
            if not strategy: continue # Skip empty strings
            if strategy not in initial_data_by_strategy:
                initial_data_by_strategy[strategy] = {}
            initial_data_by_strategy[strategy][symbol] = combined_data

    # Emit the structured data to the requesting client
    emit('initial_data', initial_data_by_strategy)
    print(f"Sent initial data for {len(initial_data_by_strategy)} strategies to client {request.sid}.")

@socketio.on('pause_updates')
def handle_pause_updates(data):
    """Handle pause/resume updates request"""
    # This feature is not fully implemented in this version
    print(f"Pause/Resume request for {data.get('symbols')}, status: {data.get('pause')}")

def create_mock_data():
    """Create mock data if real WebSocket is not available"""
    mock_symbols = ['RELIANCE', 'TCS', 'HDFCBANK', 'INFY', 'HINDUNILVR', 'ICICIBANK', 'BHARTIARTL', 'ITC', 'KOTAKBANK', 'LT']
    
    for symbol in mock_symbols:
        wsym = f"NSE:{symbol}-EQ"
        csv_data[wsym] = {
            'chartScore': 7.5,
            'announcement': 'yes',
            'premarket': 'yes',
            'prevRange': 'yes',
            'gap': round((random.random() - 0.5) * 10, 2),
            'pdc': 'yes' if random.random() > 0.5 else 'no',
            'description': 'Mock data for testing'
        }
    
    print(f"Created mock data for {len(mock_symbols)} symbols")

def start_server_process():
    """Main entry point to start the server"""
    print("Starting server process...")
    
    # --- Initialize Database ---
    print("Initializing database...")
    create_tables()
    # ---------------------------

    # Start the Fyers WebSocket in a background thread
    if fyers_available:
        websocket_thread = threading.Thread(target=start_fyers_websocket, daemon=True)
        websocket_thread.start()
        print("Fyers WebSocket thread started.")

    # Start the main data streaming thread
    stream_thread = threading.Thread(target=data_stream_thread, daemon=True)
    stream_thread.start()
    print("Data streaming thread started.")
    
    # Start Flask-SocketIO server
    print("Starting Flask-SocketIO server on http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000)

# --- Alert Checking Logic ---
def check_alerts(symbol, ltp):
    """Checks the live price against active alerts."""
    global active_alerts
    for alert in active_alerts:
        # Check if symbol matches and alert is not yet triggered
        if alert['symbol'] == symbol and not alert.get('triggered', False):
            condition_met = False
            try:
                # Safely convert to float for comparison
                live_price = float(ltp)
                alert_value = float(alert['value'])
                
                op = alert['operator']
                if op == '>' and live_price > alert_value:
                    condition_met = True
                elif op == '<' and live_price < alert_value:
                    condition_met = True
                elif op == '>=' and live_price >= alert_value:
                    condition_met = True
                elif op == '<=' and live_price <= alert_value:
                    condition_met = True
            
            except (ValueError, TypeError) as e:
                print(f"Could not compare prices for alert {alert['id']}: {e}")
                continue

            if condition_met:
                print(f"🎉 ALERT TRIGGERED: {alert['symbol']} {alert['operator']} {alert['value']}")
                alert['triggered'] = True # Mark as triggered to avoid repeat notifications
                # Notify all clients about the triggered alert
                socketio.emit('alert_triggered', alert)
                # Also broadcast the updated list of alerts (with the triggered flag)
                socketio.emit('update_alerts', active_alerts)

# --- Alert Management Sockets ---
@socketio.on('get_alerts')
def handle_get_alerts():
    """Client requests the current list of alerts."""
    emit('update_alerts', active_alerts)

@socketio.on('create_alert')
def handle_create_alert(data):
    """Handles creation of a new alert."""
    global active_alerts, alert_id_counter
    try:
        alert_id_counter += 1
        new_alert = {
            "id": alert_id_counter,
            "symbol": f"NSE:{data['symbol'].upper()}-EQ",
            "operator": data['operator'],
            "value": float(data['value']),
            "triggered": False
        }
        active_alerts.append(new_alert)
        print(f"Alert created: {new_alert}")
        # Broadcast the full updated list to all clients
        socketio.emit('update_alerts', active_alerts)
    except (KeyError, ValueError) as e:
        print(f"Error creating alert. Invalid data: {data}. Error: {e}")

@socketio.on('update_alert')
def handle_update_alert(data):
    """Handles updating an existing alert."""
    global active_alerts
    try:
        alert_id = data.get('id')
        if not alert_id:
            return

        for alert in active_alerts:
            if alert['id'] == alert_id:
                alert['operator'] = data.get('operator', alert['operator'])
                alert['value'] = float(data.get('value', alert['value']))
                alert['triggered'] = False # Reset trigger status on update
                print(f"Alert updated: {alert}")
                break
        
        # Broadcast the full updated list to all clients
        socketio.emit('update_alerts', active_alerts)
    except (KeyError, ValueError) as e:
        print(f"Error updating alert. Invalid data: {data}. Error: {e}")

@socketio.on('delete_alert')
def handle_delete_alert(data):
    """Handles deletion of an alert by its ID."""
    global active_alerts
    try:
        alert_id = data.get('id')
        if not alert_id:
            return

        initial_len = len(active_alerts)
        active_alerts = [alert for alert in active_alerts if alert.get('id') != alert_id]
        
        if len(active_alerts) < initial_len:
            print(f"Alert with ID {alert_id} deleted.")
        
        # Broadcast the full updated list to all clients
        socketio.emit('update_alerts', active_alerts)
    except KeyError as e:
        print(f"Error deleting alert. Invalid data: {data}. Error: {e}")
# --------------------------------

if __name__ == '__main__':
    # This block now just calls the main server function.
    # This allows run_optimized_dashboard.py to also call this function.
    start_server_process() 