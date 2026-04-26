# SHM-ULTRA: Neon Health Monitor

A real-time system monitoring dashboard with Machine Learning (ML) anomaly detection, forecasting, and health scoring. Featuring a professional high-tech neon interface.

## 🚀 Features
- **Real-time Metrics:** CPU, RAM, Disk, Network, and Process tracking.
- **Health Scoring:** Rule-based algorithm to calculate system health (0-100).
- **ML Anomaly Detection:** Isolation Forest model detects unusual system behavior.
- **Forecasting:** Linear Regression models to predict future resource usage.
- **Interactive Dashboard:** Modern responsive frontend built with Vanilla JS and Chart.js.
- **Persistent Storage:** SQLite (auto-fallback) or MySQL support.

## 📁 Project Structure
```text
SYSTEM-HEALTH-MONITORING/
├── backend/            # FastAPI Backend
│   ├── main.py         # Entry point & API
│   ├── collector.py    # psutil metrics collection
│   ├── database.py     # SQL storage logic
│   ├── ml_model.py     # ML (Scikit-Learn)
│   ├── algorithms.py   # Health scoring logic
│   └── requirements.txt
├── frontend/           # Static Web Frontend
│   ├── index.html
│   ├── style.css
│   └── app.js
├── Dockerfile          # Container configuration
└── docker-compose.yml  # Deployment configuration
```

## 🛠️ Getting Started

### Prerequisites
- Python 3.9+
- Docker (optional)

### Option 1: Local Setup
1. **Install Dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
2. **Run Backend:**
   ```bash
   python -m uvicorn main:app --reload
   ```
3. **Access Dashboard:**
   Open `http://localhost:8000` in your browser.

### Option 2: Docker Setup
```bash
docker-compose up --build
```
Access the dashboard at `http://localhost:8000`.

## 🛰️ API Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/health` | GET | API Status check |
| `/metrics/current` | GET | Live snapshot of all metrics |
| `/metrics/history` | GET | Last 60 snapshots for charts |
| `/anomalies` | GET | List of detected anomaly events |
| `/predictions` | GET | Forecast for the next 10 intervals |
| `/metrics/collect` | POST | Manually trigger metrics collection |

## 🧠 Machine Learning Note
The ML models require at least 10 samples in the database to train. The system will automatically collect metrics every 10 seconds. Once enough data is gathered, the Isolation Forest and Linear Regression models will activate.

---
Built with 💙 by Antigravity.
