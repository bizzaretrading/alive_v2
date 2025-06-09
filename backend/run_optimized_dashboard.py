#!/usr/bin/env python3
"""
Optimized Trading Dashboard Launcher
Handles dependencies, file checks, and starts the dashboard server
"""

import os
import sys
import subprocess
import time
from pathlib import Path
import datetime
import re

def run_fyers_login():
    """Execute the fyers_login.py script."""
    fyers_login_script_path = "fyers_login.py"
    if not os.path.exists(fyers_login_script_path):
        print(f"❌ {fyers_login_script_path} not found. Skipping Fyers login.")
        return False

    print(f"\n🔄 Running {fyers_login_script_path}...")
    try:
        # Ensure we use the same Python interpreter that's running this script
        result = subprocess.run([sys.executable, fyers_login_script_path], capture_output=True, text=True, check=False)
        
        if result.stdout:
            print(f"Output from {fyers_login_script_path}:\n{result.stdout}")
        if result.stderr:
            print(f"Errors from {fyers_login_script_path}:\n{result.stderr}")

        if result.returncode == 0:
            print(f"✅ {fyers_login_script_path} executed successfully.")
            return True
        else:
            print(f"❌ {fyers_login_script_path} failed with return code {result.returncode}.")
            return False
    except FileNotFoundError:
        print(f"❌ Error: Python interpreter '{sys.executable}' not found while trying to run {fyers_login_script_path}.")
        return False
    except Exception as e:
        print(f"❌ An unexpected error occurred while running {fyers_login_script_path}: {e}")
        return False

def get_dynamic_csv_path():
    """
    Determines the path to the correct consolidated_stock_view CSV file
    based on the current date and stock market hours (9 AM opening).
    """
    data_dir = Path("C:/Users/shash/Desktop/stock_selection_live/daily_consolidated_views") # User-specified path
    if not data_dir.is_dir():
        print(f"❌ Error: Data directory '{data_dir}' not found.")
        return None

    now = datetime.datetime.now()
    target_date = now.date()

    # If current time is before 9 AM, target previous trading day's data
    if now.time() < datetime.time(9, 0):
        target_date -= datetime.timedelta(days=1)
        if target_date.weekday() == 6:  # Sunday (was Monday, went to Sun)
            target_date -= datetime.timedelta(days=2)  # Target Friday
        elif target_date.weekday() == 5:  # Saturday (was Sunday, went to Sat)
            target_date -= datetime.timedelta(days=1)  # Target Friday
    
    target_filename_stem = f"consolidated_stock_view_{target_date.strftime('%Y-%m-%d')}_V2"
    target_filename = f"{target_filename_stem}.csv"
    specific_file_path = data_dir / target_filename

    print(f"ℹ️  Attempting to find file for market date {target_date.strftime('%Y-%m-%d')}: {specific_file_path}")

    if specific_file_path.exists() and specific_file_path.is_file():
        print(f"✅ Found specific target file: {specific_file_path}")
        return str(specific_file_path)
    else:
        print(f"⚠️  Specific file '{specific_file_path.name}' not found in {data_dir}. Looking for the most recent valid file...")

        candidate_files = []
        file_pattern = re.compile(r"consolidated_stock_view_(\d{4}-\d{2}-\d{2})_V2\.csv")

        for f_path in data_dir.glob("consolidated_stock_view_*-*_V2.csv"):
            if f_path.is_file():
                match = file_pattern.match(f_path.name)
                if match:
                    date_str = match.group(1)
                    try:
                        file_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                        candidate_files.append({'path': f_path, 'date': file_date})
                    except ValueError:
                        print(f"⚠️  Could not parse date from filename: {f_path.name}")
        
        if not candidate_files:
            print(f"❌ Error: No 'consolidated_stock_view_YYYY-MM-DD_V2.csv' files found in {data_dir}.")
            return None
            
        candidate_files.sort(key=lambda x: x['date'], reverse=True)
        
        latest_file = candidate_files[0]['path']
        print(f"✅ Using the latest available file by date in filename: {latest_file} (dated {candidate_files[0]['date'].strftime('%Y-%m-%d')})")
        return str(latest_file)

def check_and_install_requirements():
    """Check and install required packages"""
    required_packages = [
        'flask',
        'flask-socketio',
        'pandas',
        'python-socketio[client]'
    ]
    
    print("🔍 Checking required packages...")
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_').split('[')[0])
            print(f"✅ {package} - OK")
        except ImportError:
            print(f"📦 Installing {package}...")
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                print(f"✅ {package} - Installed")
            except subprocess.CalledProcessError:
                print(f"❌ Failed to install {package}")
                return False
    
    return True

def check_files(dynamic_csv_file_path_to_check):
    """Check if required files exist"""
    base_required_files = [
        'optimized_trading_dashboard.html',
        'optimized_flask_server.py',
    ]
    
    optional_files = [
        'fyers_token.txt',
        'fyers_ws_singleton.py'
    ]
    
    print("\n📂 Checking required files...")
    
    missing_files = []
    for file_path_str in base_required_files:
        if os.path.exists(file_path_str):
            print(f"✅ {file_path_str} - Found")
        else:
            print(f"❌ {file_path_str} - Missing")
            missing_files.append(file_path_str)

    # Check the dynamically selected CSV file
    if dynamic_csv_file_path_to_check and os.path.exists(dynamic_csv_file_path_to_check):
        print(f"✅ {Path(dynamic_csv_file_path_to_check).name} (Dynamically selected) - Found")
    else:
        missing_file_name = Path(dynamic_csv_file_path_to_check).name if dynamic_csv_file_path_to_check else "Dynamic CSV File"
        print(f"❌ {missing_file_name} - Missing (Path: {dynamic_csv_file_path_to_check})")
        if dynamic_csv_file_path_to_check:
            missing_files.append(dynamic_csv_file_path_to_check)
        else:
            missing_files.append("Dynamic CSV File (path not determined)")
            
    print("\n📂 Checking optional files...")
    for file_path in optional_files:
        if os.path.exists(file_path):
            print(f"✅ {file_path} - Found")
        else:
            print(f"⚠️  {file_path} - Not found (will use mock data)")
    
    if missing_files:
        print(f"\n❌ Missing required files: {', '.join(missing_files)}")
        return False
    
    return True

def create_sample_token_file():
    """Create a sample token file if it doesn't exist"""
    if not os.path.exists('fyers_token.txt'):
        print("\n📝 Creating sample fyers_token.txt file...")
        with open('fyers_token.txt', 'w') as f:
            f.write('YOUR_FYERS_ACCESS_TOKEN_HERE\n')
        print("✅ Created fyers_token.txt - Please add your actual Fyers access token")
        return False
    return True

def start_dashboard():
    """Start the optimized dashboard server by calling the server's main process function."""
    print("\n🚀 Triggering Optimized Trading Dashboard Server Start...")
    # The optimized_flask_server module should have been imported earlier in main()
    # where TARGET_CSV_FILE was set.
    try:
        # Ensure the server module is available (it should be if main succeeded this far)
        if 'optimized_flask_server' in sys.modules:
            # Call the dedicated function in the server module to start its process
            optimized_flask_server.start_server_process()
        else:
            # This case should ideally not be reached if the import in main() was successful
            print("❌ Critical error: optimized_flask_server module not found in sys.modules.")
            print("Ensure it was imported correctly in the main() function before calling start_dashboard().")
            return False # Indicate failure
    except AttributeError:
        print("❌ Critical error: optimized_flask_server module does not have start_server_process attribute.")
        print("Ensure 'def start_server_process():' is defined in optimized_flask_server.py.")
        return False # Indicate failure
    except Exception as e:
        print(f"❌ Server error during startup: {e}")
        return False # Indicate failure
    return True # Indicate success if no exceptions

def print_usage_instructions():
    """Print usage instructions"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║                   OPTIMIZED TRADING DASHBOARD                   ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  📊 Features:                                                    ║
║  • Real-time data updates without filter reset                  ║
║  • Excel-like filtering with advanced operators                 ║
║  • Customizable update rates (0.5s - 5s)                       ║
║  • Quick filter buttons for common scenarios                    ║
║  • Live statistics and connection status                        ║
║  • CSV export functionality                                     ║
║                                                                  ║
║  🔧 Setup Instructions:                                          ║
║  1. Add your Fyers access token to 'fyers_token.txt'           ║
║  2. Ensure your CSV data file is present                       ║
║  3. Run this script to start the dashboard                     ║
║                                                                  ║
║  🌐 Access: http://localhost:5000                               ║
║                                                                  ║
║  💡 Filter Examples:                                             ║
║  • Change %: ">5" (gains above 5%)                             ║
║  • Gap %: "2-10" (gap between 2% and 10%)                      ║
║  • LTP: ">=100" (price 100 or above)                           ║
║                                                                  ║
║  ⚡ Quick Filters:                                               ║
║  • "Gap >2%" - Stocks with significant gaps                    ║
║  • "Score ≥7" - High chart-ink scores                          ║
║  • "With News" - Stocks with announcements                     ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
    """)

def main():
    """Main launcher function"""
    print("🎯 OPTIMIZED TRADING DASHBOARD LAUNCHER")
    print("=" * 50)
    
    # --- Run Fyers Login Script First ---
    print("\n🔑 Attempting Fyers Login...")
    fyers_login_successful = run_fyers_login()
    if fyers_login_successful:
        print("✅ Fyers login process completed.")
    else:
        print("⚠️  Fyers login process failed or was skipped. The dashboard might use mock data or fail if token is required.")
    print("=" * 50)
    # --- End Fyers Login Script ---
    
    # Check Python version
    if sys.version_info < (3, 6):
        print("❌ Python 3.6 or higher is required")
        return 1
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} - OK")
    
    # Check and install requirements
    if not check_and_install_requirements():
        print("❌ Failed to install required packages")
        return 1

    # Determine the dynamic CSV file path
    selected_csv_file = get_dynamic_csv_path()
    if not selected_csv_file:
        print("\n❌ Critical: Could not find a suitable data CSV file. Please check the data directory and file naming.")
        return 1
    
    # Check files, including the dynamically selected one
    if not check_files(selected_csv_file):
        print("\n❌ Missing required files. Please ensure all files are present.")
        return 1
    
    # Create sample token file if needed
    token_exists = create_sample_token_file()
    
    # Print usage instructions
    print_usage_instructions()
    
    if not token_exists:
        print("⚠️  Please add your Fyers access token to 'fyers_token.txt' and run again.")

    # Before starting the dashboard, set the CSV path for the server module
    global optimized_flask_server # Make it accessible to start_dashboard if not already
    try:
        import optimized_flask_server
        optimized_flask_server.TARGET_CSV_FILE = selected_csv_file
        print(f"ℹ️  Set TARGET_CSV_FILE in server to: {selected_csv_file}")
    except ImportError:
        print("❌ Critical error: Could not import optimized_flask_server to set CSV path.")
        return 1
    except AttributeError:
        print("❌ Critical error: optimized_flask_server module does not have TARGET_CSV_FILE attribute.")
        print("Ensure 'TARGET_CSV_FILE = None' is defined at the module level in optimized_flask_server.py.")
        return 1

    # Start the dashboard
    if not start_dashboard(): # Check return value
        print("❌ Dashboard failed to start. Please check logs.")
        return 1
    # If start_dashboard() is blocking (which it will be if server runs in foreground),
    # the script might not proceed beyond this unless server is in a thread or subprocess.
    # However, socketio.run() is typically blocking.
    print("✅ Dashboard server process has been initiated.") # This might only print if server start is non-blocking
    return 0 # Indicate successful launch initiation

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code) 