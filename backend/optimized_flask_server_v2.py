from flask import Flask, render_template_string, send_from_directory, request
from flask_socketio import SocketIO, emit
import threading
import time
import json
import pandas as pd
import os
import random
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import deque

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

app = Flask(__name__, static_folder='../frontend/trading-dashboard/build', static_url_path='/')
app.config['SECRET_KEY'] = 'your-trading-dashboard-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global variables
symbols_data = {}
csv_data = {}
websocket_started = False
connected_clients = set()
active_alerts = [] # To store active alerts
alert_id_counter = 0 # Simple counter for unique alert IDs

# In-memory set to track stocks that have already triggered a PDH cross alert today
pdh_crossed_stocks = set()

# System alert history storage
system_alert_history = []

# Set to track stocks that have already triggered a 5-min positive candle alert today
positive_5min_alerted_stocks = set()

# Dictionary to store recent volume history for spike detection
# {'NSE:RELIANCE-EQ': deque([vol1, vol2, ...], maxlen=10)}
volume_history = {}

# Dictionary to store average intraday volume profiles
# {'NSE:RELIANCE-EQ': {'09:15': 15000, '09:16': 25000, ...}}
avg_volume_profiles = {}

# --- Client Alert Settings ---
# Stores the current alert settings from the client. Defaults to all on.
client_alert_settings = {
    'pdh_cross': True,
    'positive_5min_open': True,
    'volume_spike': True,
}
# -----------------------------

# --- Formatting Helper ---
def format_volume(vol):
    """Formats volume into a human-readable string (e.g., 1.2M, 450K)."""
    if vol >= 1_000_000:
        return f"{vol / 1_000_000:.2f}M"
    if vol >= 1_000:
        return f"{vol / 1_000:.1f}K"
    return str(vol)

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
                print("Warning: No symbols to start WebSocket with, using mock data if configured")
                if not csv_data: create_mock_data() # Ensure mock data if symbols are empty
                return False
        except Exception as e:
            print(f"Failed to start Fyers WebSocket: {e}")
            websocket_started = False
            if not csv_data: create_mock_data() # Fallback to mock data if WS fails
            return False
    return True

# --- System Alert Logic ---
def check_for_pdh_cross(symbol, ltp, pdh):
    """Check if the ltp has crossed the Previous Day High and trigger an alert."""
    # Only trigger if the alert type is enabled by the client
    if not client_alert_settings.get('pdh_cross', True):
        return

    if symbol not in pdh_crossed_stocks and pdh and ltp > pdh:
        pdh_crossed_stocks.add(symbol)
        message = f"Price crossed PDH ({pdh:.2f})"
        alert = {
            "id": f"sys_{symbol}_pdh_{int(time.time())}",
            "symbol": symbol,
            "type": "PDH Crossed",
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        system_alert_history.insert(0, alert)
        socketio.emit('system_alert_triggered', alert)
        print(f"🔔 SYSTEM ALERT: {symbol} - {message}")

def check_for_volume_spike(symbol, candle_data):
    """Checks for volume spikes and emits an alert if conditions are met."""
    global system_alert_history

    # Only trigger if the alert type is enabled by the client
    if not client_alert_settings.get('volume_spike', True):
        return

    # User-defined parameters for volume spike
    lookback_period = 10  # minutes
    threshold_multiplier = 2.5

    # Update history
    if symbol not in volume_history:
        volume_history[symbol] = deque(maxlen=lookback_period)
    volume_history[symbol].append(candle_data['volume'])

    # Check for spike
    if len(volume_history[symbol]) == lookback_period:
        current_volume = volume_history[symbol][-1]
        # Calculate average of the PREVIOUS volumes (excluding current)
        previous_volumes = list(volume_history[symbol])[:-1]
        if not previous_volumes: return

        avg_volume = sum(previous_volumes) / len(previous_volumes)
        
        if avg_volume > 0 and current_volume > (avg_volume * threshold_multiplier):
            message = f"Volume spike: {format_volume(current_volume)} vs avg {format_volume(avg_volume)}"
            alert = {
                "id": f"sys_{symbol}_vol_{int(time.time())}",
                "symbol": symbol,
                "type": "Volume Spike",
                "message": message,
                "timestamp": datetime.now().isoformat()
            }
            system_alert_history.insert(0, alert)
            socketio.emit('system_alert_triggered', alert)
            print(f"🔔 SYSTEM ALERT: {symbol} - {message}")


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
                if not isinstance(data, dict): continue

                ltp = data.get('ltp', 0)
                vol = data.get('vol_traded_today', 0)

                # Initialize candle if it's the first tick for this minute
                if symbol not in live_candles or live_candles[symbol]['timestamp'] != current_minute_timestamp:
                    # Before creating a new candle, check if the old one should be finalized
                    if symbol in live_candles:
                        old_candle = live_candles[symbol]
                        save_candle_to_db(symbol, old_candle)
                        # --- Trigger Volume Spike check on candle close ---
                        check_for_volume_spike(symbol, old_candle)
                        # --------------------------------------------------

                    live_candles[symbol] = {
                        'timestamp': current_minute_timestamp,
                        'open': ltp,
                        'high': ltp,
                        'low': ltp,
                        'close': ltp,
                        'volume': 0, # Volume for the candle starts at 0
                        'last_total_volume': vol 
                    }
                
                # Update the current candle
                candle = live_candles[symbol]
                candle['high'] = max(candle['high'], ltp)
                candle['low'] = min(candle['low'], ltp)
                candle['close'] = ltp
                
                # Volume for the candle is the change in total volume
                if vol >= candle['last_total_volume']:
                    candle['volume'] += (vol - candle['last_total_volume'])
                candle['last_total_volume'] = vol
            # --- End Candle Aggregation ---

            processed_data = {}
            current_time = time.time()
                
            for symbol, data in ltp_data.items():
                    if isinstance(data, dict):
                        # Combine live data with static CSV data
                        combined_data = {
                            'symbol': symbol,
                            'ltp': data.get('ltp', 0),
                        'change': data.get('chp', 0),
                            'volume': data.get('vol_traded_today', 0),
                            'high': data.get('high_price', 0),
                            'low': data.get('low_price', 0),
                            'open': data.get('open_price', 0),
                            'last_update': current_time
                        }
                        
                        symbol_static_data = csv_data.get(symbol, {})
                        combined_data.update(symbol_static_data)
                        
                    # --- PDH Crossing Check ---
                        pdh_value = symbol_static_data.get('pdh', 0.0)
                    if pdh_value:
                        check_for_pdh_cross(symbol, combined_data['ltp'], pdh_value)
                    
                    # --- RVol Calculation ---
                    current_dt = datetime.fromtimestamp(current_time)
                    time_key = current_dt.strftime('%H:%M')
                    if symbol in avg_volume_profiles and time_key in avg_volume_profiles[symbol]:
                        avg_vol = avg_volume_profiles[symbol][time_key]
                        current_candle_vol = live_candles.get(symbol, {}).get('volume', 0)
                        if avg_vol > 0:
                            combined_data['rvol'] = round(current_candle_vol / avg_vol, 2)

                    # --- Alert Check ---
                    check_alerts(symbol, combined_data['ltp'])
                    
                    processed_data[symbol] = combined_data

            # Check for changes and emit only if data has changed since last emission
            changed_data = {}
            for symbol, data in processed_data.items():
                last_sent = last_emission.get(symbol)
                if last_sent != data:
                    changed_data[symbol] = data
                    last_emission[symbol] = data

            if changed_data:
                # Group data by strategy before emitting
                grouped_updates = {}
                for symbol, data in changed_data.items():
                    strategies = data.get('chartStrategy', '').split(',')
                    strategies = [s.strip() for s in strategies if s.strip()]
                    if not strategies:
                        strategies = ['Uncategorized']

                    for strategy in strategies:
                        if strategy not in grouped_updates:
                            grouped_updates[strategy] = {}
                        grouped_updates[strategy][symbol] = data

                if grouped_updates:
                    socketio.emit('data_update', grouped_updates)
                    
            if invalid_symbols:
                socketio.emit('invalid_symbols', {'symbols': list(invalid_symbols)})

            time.sleep(1) # Main loop delay
        except Exception as e:
            print(f"Error in data stream thread: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(5)


# --- API / Static File Routes ---
@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    if path != "" and os.path.exists(os.path.join(app.static_folder, path)):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')


# --- SocketIO Handlers ---
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
    """Sends the entire dataset, structured by strategy, to a newly connected client."""
    
    # Process the full csv_data to match the live data structure
    initial_full_data = {}
    for symbol, static_data in csv_data.items():
        # Create a combined data structure similar to the live one
        combined_data = {
            'symbol': symbol,
            'ltp': 0, 'change': 0, 'volume': 0,
            'high': 0, 'low': 0, 'open': 0,
            'last_update': 0
        }
        combined_data.update(static_data)
        initial_full_data[symbol] = combined_data

    # Group initial data by strategy
    initial_data_by_strategy = {}
    for symbol, data in initial_full_data.items():
        strategies = data.get('chartStrategy', '').split(',')
        strategies = [s.strip() for s in strategies if s.strip()]
        if not strategies:
            strategies = ['Uncategorized']

        for strategy in strategies:
            if not strategy: continue # Skip empty strings
            if strategy not in initial_data_by_strategy:
                initial_data_by_strategy[strategy] = {}
            initial_data_by_strategy[strategy][symbol] = combined_data

    # Emit the structured data to the requesting client
    emit('initial_data', initial_data_by_strategy)
    print(f"Sent initial data for {len(initial_data_by_strategy)} strategies to client {request.sid}.")


def create_mock_data():
    """Creates mock data if CSV is not found"""
    global csv_data
    mock_symbols = ['NSE:RELIANCE-EQ', 'NSE:TCS-EQ', 'NSE:HDFCBANK-EQ', 'NSE:INFY-EQ', 'NSE:HINDUNILVR-EQ']
    strategies = ['Morning', 'Mid-day', 'Afternoon']
    for symbol in mock_symbols:
        csv_data[symbol] = {
            'newsWeight': random.choice([0, 1, 2, 3]),
            'chartStrategy': random.choice(strategies),
            'description': 'Mock announcement',
            'premarket': random.choice(['yes', 'no']),
            'sopen': random.choice(['yes', 'no']),
            'gap': round(random.uniform(-5, 5), 2),
            'spdc': random.choice(['yes', 'no']),
            'pdh': round(random.uniform(100, 3000) * 1.05, 2),
            'announcement': 'yes'
        }
    print(f"Created mock data for {len(mock_symbols)} symbols.")

def start_server_process():
    """Main entry point to start the server"""
    print("Starting server process...")
    
    # --- Initialize Database ---
    print("Initializing database...")
    create_tables()
    # ---------------------------

    # --- Pre-calculate RVol Profiles ---
    calculate_average_intraday_volume(lookback_days=10)
    # -----------------------------------

    # Start the Fyers WebSocket in a background thread
    if fyers_available:
        websocket_thread = threading.Thread(target=start_fyers_websocket, daemon=True)
        websocket_thread.start()
        print("Fyers WebSocket thread started.")

    # Start the main data streaming thread
    stream_thread = threading.Thread(target=data_stream_thread, daemon=True)
    stream_thread.start()
    print("Data streaming thread started.")
    
    # Schedule the 5-minute candle check
    schedule_5min_candle_check()
    
    # Start Flask-SocketIO server
    print("Starting Flask-SocketIO server on http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000)

def check_alerts(symbol, ltp):
    """Check user-created alerts and emit if triggered."""
    global active_alerts
    
    triggered_this_tick = False
    for alert in active_alerts:
        if alert['symbol'] == symbol and not alert.get('triggered', False):
            operator = alert['operator']
            value = alert['value']
            
            condition_met = False
            if operator == '>=' and ltp >= value:
                    condition_met = True
            elif operator == '<=' and ltp <= value:
                    condition_met = True

            if condition_met:
                alert['triggered'] = True
                print(f"🔔 ALERT: {symbol} {operator} {value} (LTP: {ltp})")
                socketio.emit('alert_triggered', {
                    'symbol': symbol,
                    'message': f"LTP {ltp} {operator} {value}",
                    'id': alert['id']
                })
                triggered_this_tick = True
    
    # If any alert was triggered, broadcast the updated list
    if triggered_this_tick:
                socketio.emit('update_alerts', active_alerts)

# --- Alert Management Sockets ---
@socketio.on('get_alerts')
def handle_get_alerts():
    """Client requests the current list of alerts."""
    emit('update_alerts', active_alerts)

@socketio.on('get_system_alert_history')
def handle_get_system_alert_history():
    """Client requests the history of system-triggered alerts."""
    emit('system_alert_history', system_alert_history)

@socketio.on('update_alert_settings')
def handle_update_alert_settings(settings):
    """Client sends updated alert settings."""
    global client_alert_settings
    print(f"Received alert settings update from client: {settings}")
    # Basic validation to ensure we only accept known keys
    if isinstance(settings, dict):
        for key in client_alert_settings:
            if key in settings and isinstance(settings[key], bool):
                client_alert_settings[key] = settings[key]
    print(f"Updated alert settings: {client_alert_settings}")

@socketio.on('add_alert')
def handle_add_alert(data):
    """Handles adding a new alert."""
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

# --- 5-Min Opening Candle Alert ---
def check_positive_5min_candle_alert():
    """Scheduled job to check for stocks with a positive 5-minute opening candle."""
    global system_alert_history, positive_5min_alerted_stocks
    print("Running scheduled 5-minute opening candle check...")

    # Only run the check if the alert type is enabled by the client
    if not client_alert_settings.get('positive_5min_open', True):
        print("Positive 5-Min Open alert is disabled by client. Skipping check.")
        return

    # Get a database connection
    conn = None
    try:
        conn = pool.connection()
        with conn.cursor() as cur:
            # Get the list of all unique symbols from the CSV data
            all_symbols = list(csv_data.keys())
            
            # Define the time range for the first 5 minutes (9:15 to 9:19) for today
            today = datetime.now().date()
            start_time = datetime.combine(today, datetime.min.time()) + timedelta(hours=9, minutes=15)
            end_time = start_time + timedelta(minutes=4) # Candles for 9:15, 9:16, 9:17, 9:18, 9:19

            for symbol in all_symbols:
                if symbol in positive_5min_alerted_stocks:
                    continue # Skip if already alerted today

                # Fetch the first 5 candles for the symbol
                cur.execute("""
                    SELECT open, high, low, close, timestamp FROM candles_1min
                    WHERE symbol = %s AND timestamp BETWEEN %s AND %s
                    ORDER BY timestamp ASC
                    LIMIT 5;
                """, (symbol, start_time, end_time))
                
                candles = cur.fetchall()

                if len(candles) == 5:
                    opening_price = candles[0][0] # Open of the first candle
                    closing_price = candles[4][3] # Close of the fifth candle

                    if closing_price > opening_price:
                        # Mark as alerted and trigger the alert
                        positive_5min_alerted_stocks.add(symbol)
                        message = f"Positive 5-min open candle ({opening_price:.2f} -> {closing_price:.2f})"
                        alert = {
                            "id": f"sys_{symbol}_5min_{int(time.time())}",
                            "symbol": symbol,
                            "type": "Positive 5-Min Open",
                            "message": message,
                            "timestamp": datetime.now().isoformat()
                        }
                        system_alert_history.insert(0, alert)
                        socketio.emit('system_alert_triggered', alert)
                        print(f"🔔 SYSTEM ALERT: {symbol} - {message}")

    except Exception as e:
        print(f"Error checking 5-min candle alert: {e}")
    finally:
        if conn:
            conn.close()

def schedule_5min_candle_check():
    """Schedules the 5-min candle check to run daily at 9:20 AM."""
    
    def get_next_run_time():
        now = datetime.now()
        run_time_today = now.replace(hour=9, minute=20, second=0, microsecond=0)
        if now > run_time_today:
            # If it's past 9:20 AM, schedule for tomorrow
            run_time_tomorrow = run_time_today + timedelta(days=1)
            return run_time_tomorrow
        return run_time_today

    def schedule_job():
        next_run = get_next_run_time()
        delay = (next_run - datetime.now()).total_seconds()
        print(f"Scheduling next 5-min candle check in {delay/3600:.2f} hours at {next_run}")
        
        # Using a Timer thread to run the check after the delay
        threading.Timer(delay, run_and_reschedule).start()

    def run_and_reschedule():
        check_positive_5min_candle_alert()
        # Reschedule for the next day
        schedule_job()

    print("Initial scheduling of 5-min candle check...")
    schedule_job()
# -----------------------------

# --- RVol Calculation Setup ---
def calculate_average_intraday_volume(lookback_days=10):
    """
    Calculates the average volume for each 1-minute interval of the trading day
    based on the last `lookback_days` of data from the database.
    """
    global avg_volume_profiles
    print("Calculating average intraday volume profiles...")
    
    conn = None
    try:
        conn = pool.connection()
        with conn.cursor() as cur:
            # Define the date range for the query
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=lookback_days)
            
            # SQL query to fetch time interval and average volume
            cur.execute("""
                SELECT
                    symbol,
                    to_char(timestamp, 'HH24:MI') AS minute_interval,
                    AVG(volume) AS avg_volume
                FROM
                    candles_1min
                WHERE
                    timestamp::date >= %s
                    AND timestamp::date < %s
                GROUP BY
                    symbol, minute_interval
                ORDER BY
                    symbol, minute_interval;
            """, (start_date, end_date))
            
            rows = cur.fetchall()
            
            # Process the results into the desired structure
            for row in rows:
                symbol, minute_interval, avg_volume = row
                if symbol not in avg_volume_profiles:
                    avg_volume_profiles[symbol] = {}
                avg_volume_profiles[symbol][minute_interval] = float(avg_volume)

        print(f"✅ Successfully calculated RVol profiles for {len(avg_volume_profiles)} symbols.")
        if avg_volume_profiles:
            # Log a sample for verification
            sample_symbol = next(iter(avg_volume_profiles))
            sample_time = next(iter(avg_volume_profiles[sample_symbol]))
            print(f"   Sample profile: {sample_symbol} @ {sample_time}: {avg_volume_profiles[sample_symbol][sample_time]:.2f} avg volume")

    except Exception as e:
        print(f"❌ Error calculating average intraday volume: {e}")
    finally:
        if conn:
            conn.close()
# --------------------------


if __name__ == '__main__':
    # This block now just calls the main server function.
    # This allows run_optimized_dashboard.py to also call this function.
    start_server_process() 