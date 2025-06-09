import threading
import time
from fyers_apiv3.FyersWebsocket import data_ws

ltp_lock = threading.Lock()
global_ltp = {}
global_invalid = set()

class FyersWebSocketSingleton:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, access_token, symbols):
        self.access_token = access_token
        self.symbols = symbols
        self.ws_thread = None
        self.fyers = None
        self.started = False

    @classmethod
    def get_instance(cls, access_token, symbols):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(access_token, symbols)
            return cls._instance

    def onmessage(self, message):
        # print(f"[DEBUG] onmessage called: {message}") # Commented out to reduce console noise
        if isinstance(message, dict) and "symbol" in message:
            with ltp_lock:
                global_ltp[message['symbol']] = message  # Store full dict

    def onerror(self, message):
        print("Error:", message)
        if isinstance(message, dict) and 'invalid_symbols' in message:
            with ltp_lock:
                global_invalid.update(message['invalid_symbols'])

    def onclose(self, message):
        print("Closed:", message)

    def onopen(self):
        print("[DEBUG] WebSocket connection opened and subscribing...")
        data_type = "SymbolUpdate"
        if self.fyers is not None:
            self.fyers.subscribe(symbols=self.symbols, data_type=data_type)
            self.fyers.keep_running()
        else:
            print("[ERROR] fyers is None in onopen!")

    def ws_thread_func(self):
        print("[DEBUG] WebSocket thread started.")
        self.fyers = data_ws.FyersDataSocket(
            access_token=self.access_token,
            log_path="",
            litemode=False,  # FULL DATA MODE
            write_to_file=False,
            reconnect=True,
            on_connect=self.onopen,
            on_close=self.onclose,
            on_error=self.onerror,
            on_message=self.onmessage
        )
        self.fyers.connect()
        while True:
            time.sleep(1)

    def start(self):
        if not self.started:
            print("[DEBUG] Starting WebSocket thread (singleton)...")
            self.ws_thread = threading.Thread(target=self.ws_thread_func, daemon=True)
            self.ws_thread.start()
            self.started = True

# Module-level singleton reference
_singleton = None

def start_websocket(access_token, symbols):
    global _singleton
    if _singleton is None:
        _singleton = FyersWebSocketSingleton.get_instance(access_token, symbols)
        _singleton.start()
    return _singleton

def get_ltp_data():
    with ltp_lock:
        ltp_copy = dict(global_ltp)
        invalid_copy = set(global_invalid)
    return ltp_copy, invalid_copy 