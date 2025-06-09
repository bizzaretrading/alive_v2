from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO, emit
import threading
import time
import json
import pandas as pd
from fyers_ws_singleton import start_websocket, get_ltp_data

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global variables
symbols_data = {}
csv_data = {}
websocket_started = False

def load_csv_data():
    """Load static data from CSV file"""
    global csv_data
    try:
        df = pd.read_csv("consolidated_stock_view_2025-05-23_V2.csv")
        df.iloc[:, 0] = df.iloc[:, 0].astype(str)
        
        for idx, row in df.iterrows():
            symbol = row.iloc[0]
            # Convert symbol to Fyers format
            wsym = symbol
            if not wsym.startswith("NSE:"):
                wsym = f"NSE:{wsym}" if not wsym.endswith("-EQ") else f"NSE:{wsym}"
            if not wsym.endswith("-EQ"):
                wsym = f"{wsym}-EQ"
            
            # Store all CSV columns as static data
            static_data = row.iloc[1:].to_dict()
            # Remove unwanted columns
            static_data.pop('Announcement Links', None)
            static_data.pop('Announcement Text', None)
            csv_data[wsym] = static_data
            
        print(f"Loaded {len(csv_data)} symbols from CSV")
        return list(csv_data.keys())
    except Exception as e:
        print(f"Error loading CSV: {e}")
        return []

def start_fyers_websocket():
    """Start Fyers WebSocket connection"""
    global websocket_started
    if not websocket_started:
        try:
            with open("fyers_token.txt", "r") as f:
                access_token = f.read().strip()
            
            symbols = load_csv_data()
            print(f"Starting WebSocket for {len(symbols)} symbols")
            start_websocket(access_token, symbols)
            websocket_started = True
            print("Fyers WebSocket started successfully")
        except Exception as e:
            print(f"Error starting WebSocket: {e}")

def data_stream_thread():
    """Background thread to stream data to clients"""
    while True:
        try:
            ltp_data, invalid_symbols = get_ltp_data()
            
            if ltp_data:
                # Process and emit data
                processed_data = {}
                for symbol, data in ltp_data.items():
                    if isinstance(data, dict):
                        # Combine live data with static CSV data
                        combined_data = {
                            'symbol': symbol.replace('NSE:', '').replace('-EQ', ''),
                            'ltp': data.get('ltp', 0),
                            'change': data.get('chp', 0),  # change percentage
                            'volume': data.get('vol_traded_today', 0),
                            'high': data.get('high_price', 0),
                            'low': data.get('low_price', 0),
                            'open': data.get('open_price', 0),
                            'last_update': time.time()
                        }
                        
                        # Add static data from CSV
                        if symbol in csv_data:
                            combined_data.update(csv_data[symbol])
                        
                        processed_data[symbol] = combined_data
                
                # Emit to all connected clients
                socketio.emit('market_data', {
                    'data': processed_data,
                    'invalid_symbols': list(invalid_symbols),
                    'timestamp': time.time()
                })
            
        except Exception as e:
            print(f"Error in data stream: {e}")
        
        time.sleep(0.5)  # Update every 500ms

@app.route('/')
def dashboard():
    """Serve the dashboard HTML"""
    # Read the HTML template (you'll need to save the previous HTML as a template)
    with open('dashboard_template.html', 'r') as f:
        html_content = f.read()
    return html_content

@app.route('/api/columns')
def get_columns():
    """Get available columns from CSV"""
    if csv_data:
        sample_data = next(iter(csv_data.values()))
        columns = ['symbol', 'ltp', 'change', 'volume', 'high', 'low', 'open'] + list(sample_data.keys())
        return jsonify(columns)
    return jsonify(['symbol', 'ltp', 'change', 'volume', 'high', 'low', 'open'])

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('connection_status', {'status': 'connected'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

@socketio.on('request_initial_data')
def handle_initial_data():
    """Send initial data to newly connected client"""
    try:
        ltp_data, invalid_symbols = get_ltp_data()
        processed_data = {}
        
        for symbol in csv_data.keys():
            data = ltp_data.get(symbol, {})
            combined_data = {
                'symbol': symbol.replace('NSE:', '').replace('-EQ', ''),
                'ltp': data.get('ltp', 0) if isinstance(data, dict) else 0,
                'change': data.get('chp', 0) if isinstance(data, dict) else 0,
                'volume': data.get('vol_traded_today', 0) if isinstance(data, dict) else 0,
                'high': data.get('high_price', 0) if isinstance(data, dict) else 0,
                'low': data.get('low_price', 0) if isinstance(data, dict) else 0,
                'open': data.get('open_price', 0) if isinstance(data, dict) else 0,
                'last_update': time.time()
            }
            combined_data.update(csv_data[symbol])
            processed_data[symbol] = combined_data
        
        emit('initial_data', {
            'data': processed_data,
            'invalid_symbols': list(invalid_symbols)
        })
    except Exception as e:
        print(f"Error sending initial data: {e}")

if __name__ == '__main__':
    # Start Fyers WebSocket in background
    start_fyers_websocket()
    
    # Start data streaming thread
    data_thread = threading.Thread(target=data_stream_thread, daemon=True)
    data_thread.start()
    
    print("Starting Flask-SocketIO server...")
    print("Dashboard will be available at: http://localhost:5000")
    
    # Run the Flask-SocketIO server
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)