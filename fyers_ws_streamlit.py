import streamlit as st
import pandas as pd
from streamlit_autorefresh import st_autorefresh
from fyers_ws_singleton import start_websocket, get_ltp_data
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode

st.set_page_config(
    page_title="Live LTP Dashboard (Fyers WebSocket)",
    page_icon="📈",
    layout="wide",
)

# --- Read all symbols and static columns from CSV once ---
csv_df = pd.read_csv("consolidated_stock_view_2025-05-23_V2.csv")
# Ensure symbol column is always string
csv_df.iloc[:, 0] = csv_df.iloc[:, 0].astype(str)

# Remove unwanted columns and prepare for reordering
cols = list(csv_df.columns)
# Remove 'Announcement Links' and 'Announcement Text'
cols = [c for c in cols if c not in ['Announcement Links', 'Announcement Text']]
# Move 'Announcement Description' to the end
if 'Announcement Description' in cols:
    cols = [c for c in cols if c != 'Announcement Description'] + ['Announcement Description']

# Build symbol list in Fyers format
symbols = []
symbol_to_static = {}
for idx, row in csv_df.iterrows():
    sym = row.iloc[0]
    wsym = sym
    if not wsym.startswith("NSE:"):
        wsym = f"NSE:{wsym}" if not wsym.endswith("-EQ") else f"NSE:{wsym}"
    if not wsym.endswith("-EQ"):
        wsym = f"{wsym}-EQ" if not wsym.endswith("-EQ") else wsym
    symbols.append(wsym)
    # Store static columns (as dict, excluding symbol col)
    static_dict = row.iloc[1:].to_dict()
    # Remove unwanted columns
    static_dict.pop('Announcement Links', None)
    static_dict.pop('Announcement Text', None)
    symbol_to_static[wsym] = static_dict

# Read access token from file
with open("fyers_token.txt", "r") as f:
    access_token = f.read().strip()

# --- Start the robust singleton WebSocket thread only once ---
start_websocket(access_token, symbols)

# --- Custom CSS for compact, minimalist dark layout ---
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 1rem !important;
    }
    .stHeader, .st-emotion-cache-1v0mbdj, .st-emotion-cache-1avcm0n {
        margin-bottom: 0.5rem !important;
    }
    .stMetric {
        font-size: 1.1rem !important;
        margin-bottom: 0.2rem !important;
    }
    .stDataFrame, .stTable {
        background-color: #2c2c2c !important;
        border-radius: 8px !important;
        font-size: 0.95rem !important;
    }
    .stDataFrame thead tr th {
        background-color: #232323 !important;
        color: #fff !important;
    }
    .stDataFrame tbody tr {
        background-color: #2c2c2c !important;
    }
    .stDataFrame tbody tr:nth-child(even) {
        background-color: #242424 !important;
    }
    .st-emotion-cache-1v0mbdj, .st-emotion-cache-1avcm0n {
        padding: 0.2rem 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# --- Visible, bold heading at the top ---
st.markdown(
    """
    <h1 style='color: #fff; font-size: 2.2rem; font-weight: 800; margin-bottom: 0.2rem; margin-top: 0.2rem;'>LIVE dash board</h1>
    """,
    unsafe_allow_html=True,
)

# --- Compact header and info row (all in one line, top of page, below heading) ---
st.markdown(
    f"""
    <div style='display: flex; flex-direction: row; align-items: center; justify-content: flex-start; gap: 2.5rem; margin-bottom: 0.2rem; margin-top: 0.2rem;'>
        <span style='font-size:1rem;'>stream from: <b>CSV, WEBSOCKET</b></span>
        <span style='font-size:1rem;'>Tracked: <b>{len(symbols)}</b></span>
        <span style='font-size:1rem;'>Invalid: <b>{len(get_ltp_data()[1])}</b></span>
        <span style='font-size:1rem;'>LTP Range: <b>{min([v for v in get_ltp_data()[0].values() if isinstance(v, (int, float))] or ['-'])} - {max([v for v in get_ltp_data()[0].values() if isinstance(v, (int, float))] or ['-'])}</b></span>
    </div>
    """,
    unsafe_allow_html=True,
)

# Auto-refresh every 5 seconds
st_autorefresh(interval=5000, key="refresh")

# --- Live-updating table and info ---
with st.container():
    ltp_copy, invalid_copy = get_ltp_data()  # <-- call inside refreshable block
    if invalid_copy:
        st.markdown(
            f"<div style='color:#ffb300;font-size:0.95rem;margin-bottom:0.2rem;'>Invalid symbols: {', '.join(sorted(invalid_copy))}</div>",
            unsafe_allow_html=True,
        )

    valid_symbols = [s for s in symbols if s not in invalid_copy]
    data = []
    for sym in valid_symbols:
        ltp_val = None
        chp_val = None
        data_dict = ltp_copy.get(sym)
        if isinstance(data_dict, dict):
            ltp_val = data_dict.get("ltp")
            chp_val = data_dict.get("chp")
        elif isinstance(data_dict, (int, float)):
            ltp_val = data_dict  # fallback for old/lite mode
        if ltp_val is None:
            ltp_val = float('nan')
        row = {'Symbol': sym, 'Change %': chp_val, 'LTP': ltp_val}
        static = symbol_to_static.get(sym, {})
        for c in cols[1:]:
            if c != 'Announcement Description':
                row[c] = static.get(c, '')
        if 'Announcement Description' in static:
            row['Announcement Description'] = static['Announcement Description']
        data.append(row)

    num_valid = len(valid_symbols)
    df = pd.DataFrame(data)
    gb = GridOptionsBuilder.from_dataframe(df)
    gb.configure_default_column(filter=True, sortable=True, editable=False)
    gridOptions = gb.build()

    # Use session state to preserve grid state
    if "aggrid_state" not in st.session_state:
        st.session_state["aggrid_state"] = None

    response = AgGrid(
        df,
        gridOptions=gridOptions,
        enable_enterprise_modules=False,
        theme='alpine-dark',
        height=800,
        fit_columns_on_grid_load=True,
        update_mode=GridUpdateMode.NO_UPDATE,  # Prevents blinking
        data_return_mode="AS_INPUT",
        reload_data=False,
    )

    st.session_state["aggrid_state"] = response
    if num_valid == 0:
        st.info('Waiting for live LTP data from Fyers WebSocket...')

    # --- Download CSV button ---
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download table as CSV",
        data=csv,
        file_name="live_ltp_dashboard.csv",
        mime="text/csv",
    )