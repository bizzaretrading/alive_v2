# Live Trading Dashboard V4

Welcome to Version 4 of the Live Trading Dashboard!  
This release is a major overhaul, featuring a robust Dockerized backend, PostgreSQL database, real-time alert system, and a modern, highly interactive React/TypeScript frontend.

![Live Trading Dashboard V4 Screenshot](./assets/dashboard-screenshot_v4.png)

---

## 🚀 Major Features

- **Dockerized Architecture:**  
  - One-command setup for PostgreSQL database using Docker Compose.
  - Backend and database are fully decoupled for easy deployment.

- **Real-Time Data & Alerts:**  
  - Live stock data streamed via Flask-SocketIO from the Fyers WebSocket API.
  - Powerful, persistent alert system: set price alerts, get notified instantly, manage alerts in a modern UI.

- **Advanced UI/UX:**  
  - Compact, responsive tables and cards for maximum data density.
  - Movable, modal-based alert creation and editing.
  - Sticky headers, color-coded badges, and intuitive controls.
  - All dashboards (All, Morning, Mid-Day, Afternoon) now share a consistent, compact look.

- **Historical Data & Analytics:**  
  - Automatic aggregation and storage of 1-minute OHLCV candles in PostgreSQL.
  - Script for importing historical data for new stocks.

---

## 🗂️ Project Structure

```
alive_V2/
├── backend/                # Python Flask server, Fyers integration, DB logic
│   ├── run_optimized_dashboard_v2.py
│   ├── optimized_flask_server_v2.py
│   ├── database.py
│   └── ... (other scripts)
├── frontend/
│   └── trading-dashboard/  # React + TypeScript + Vite frontend
│       ├── src/App.tsx
│       └── ...
├── docker-compose.yml      # For PostgreSQL database
└── README.md
```

---

## ⚡ Quick Start

### 1. **Database (PostgreSQL) via Docker**

```bash
docker-compose up -d
```
- This will start a PostgreSQL database on port 5432 with default credentials (`user`/`password`).

### 2. **Backend Setup**

```bash
cd backend
python run_optimized_dashboard_v2.py
```
- The backend will auto-install dependencies if needed.
- Place your Fyers API token in `backend/fyers_token.txt` for live data (otherwise, mock data is used).

### 3. **Frontend Setup**

```bash
cd frontend/trading-dashboard
npm install
npm run dev
```
- The dashboard will be available at `http://localhost:5173`.

---

## 🛡️ Migration & Branches

- The previous codebase is preserved on the `legacy` branch.
- All new development will continue on the `main` branch from Version 4 onward.

---

## 📝 Notes

- **Environment Variables:**  
  - The backend uses `DATABASE_URL` (default: `postgresql://user:password@localhost:5432/trading_dashboard`).  
    You can override this in a `.env` file in the backend directory.
- **Historical Data:**  
  - Use `backend/import_historical_data.py` to backfill candles for new stocks.
- **Educational Use Only:**  
  - This project is for demonstration and educational purposes.

---

## 📣 Major Contributors

- UI/UX, backend, and architecture: [Shashank]

--- 
