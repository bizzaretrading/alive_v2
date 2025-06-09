from flask import Flask, render_template_string, send_from_directory, request
from flask_socketio import SocketIO, emit
import threading
import time
import json
import pandas as pd
import os
import random
from pathlib import Path

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

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-trading-dashboard-secret'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global variables
symbols_data = {}
csv_data = {}
websocket_started = False
connected_clients = set()

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
    
    while True:
        try:
            if not connected_clients:
                time.sleep(1)
                continue
                
            ltp_data, invalid_symbols = get_ltp_data()
            
            if ltp_data:
                # This will hold the data grouped by strategy
                processed_data_by_strategy = {}
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
    print(f'Client disconnected: {request.sid}')
    connected_clients.discard(request.sid)

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
        
        combined_data = {
            'symbol': symbol,
            'ltp': live_data.get('ltp', 0),
            'change': live_data.get('chp', 0),
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
    # This could be used to manage per-client update preferences
    print(f"Client {request.sid} requested pause: {data.get('paused', False)}")

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
    """Initializes and runs the Flask-SocketIO server."""
    # Try to start Fyers WebSocket, fall back to mock data if needed
    websocket_success = start_fyers_websocket()
    
    # This check ensures mock data if websocket fails AND no CSV was loaded.
    if not websocket_success and not csv_data: 
        print("Failed to start Fyers WebSocket and no CSV data, creating mock data as a last resort...")
        create_mock_data()
    
    # Start data streaming thread
    data_thread = threading.Thread(target=data_stream_thread, daemon=True)
    data_thread.start()
    
    print("=" * 60)
    print("🚀 OPTIMIZED TRADING DASHBOARD SERVER STARTING")
    print("=" * 60)
    print(f"Dashboard URL: http://localhost:5000")
    print(f"WebSocket Status: {'✅ Connected' if websocket_started else '⚠️  Mock Data'}")
    print(f"Symbols Loaded: {len(csv_data)}")
    print("=" * 60)
    
    # Run the Flask-SocketIO server
    socketio.run(
        app, 
        host='0.0.0.0', 
        port=5000, 
        debug=False, # Set to True for more detailed server logs if needed during dev
        allow_unsafe_werkzeug=True # Keep this if necessary for your setup
    )

if __name__ == '__main__':
    # This block now just calls the main server function.
    # This allows run_optimized_dashboard.py to also call this function.
    start_server_process() 