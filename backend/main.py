"""
System Health Monitoring - FastAPI Backend
Main application entry point with all API endpoints.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from collector import MetricsCollector
from database import DatabaseManager
from ml_model import MLModel
from algorithms import HealthAnalyzer

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("SHM")

# ─── Singletons ─────────────────────────────────────────────────────────────
db      = DatabaseManager()
collector = MetricsCollector()
ml      = MLModel()
analyzer = HealthAnalyzer()

# ─── Background collection loop ─────────────────────────────────────────────
async def auto_collect():
    """Collect metrics every 10 seconds in the background."""
    while True:
        try:
            metrics = collector.collect()
            db.insert_metrics(metrics)
            logger.debug("Metrics collected and stored.")
        except Exception as e:
            logger.error(f"Auto-collect error: {e}")
        await asyncio.sleep(10)

# ─── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting System Health Monitor...")
    db.initialize_schema()
    ml.load_or_train(db)
    task = asyncio.create_task(auto_collect())
    yield
    task.cancel()
    logger.info("Shutdown complete.")

from fastapi.staticfiles import StaticFiles
import os

# ─── App ─────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="System Health Monitor API",
    description="Real-time system metrics, ML anomaly detection, and health scoring.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 1 — GET /health
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Status"])
def health_check():
    """
    Simple health check.
    Returns:
        { "status": "ok", "timestamp": "..." }
    """
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version": "1.0.0",
    }

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 2 — GET /metrics/current
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/metrics/current", tags=["Metrics"])
def get_current_metrics():
    """
    Live snapshot of all system metrics.
    Returns CPU, RAM, disk, network, processes, temperature.
    """
    try:
        metrics = collector.collect()
        score   = analyzer.health_score(metrics)
        metrics["health_score"] = score
        metrics["timestamp"]    = datetime.utcnow().isoformat() + "Z"
        return metrics
    except Exception as e:
        logger.error(f"/metrics/current error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 3 — GET /metrics/history
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/metrics/history", tags=["Metrics"])
def get_metrics_history(limit: int = 60, hours: int = 1):
    """
    Historical metrics for chart rendering.
    Args:
        limit: max rows to return (default 60)
        hours: lookback window in hours (default 1)
    Returns list of metric snapshots.
    """
    try:
        rows = db.fetch_history(limit=limit, hours=hours)
        return {"data": rows, "count": len(rows)}
    except Exception as e:
        logger.error(f"/metrics/history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 4 — GET /metrics/summary
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/metrics/summary", tags=["Metrics"])
def get_metrics_summary(hours: int = 24):
    """
    Aggregated statistics over the last N hours.
    Returns avg/min/max for CPU, RAM, Disk, Network.
    """
    try:
        summary = db.fetch_summary(hours=hours)
        return summary
    except Exception as e:
        logger.error(f"/metrics/summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 5 — GET /anomalies
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/anomalies", tags=["ML"])
def get_anomalies(limit: int = 20):
    """
    Returns recent anomaly events detected by the ML model.
    Each event includes metric snapshot + anomaly score.
    """
    try:
        rows = db.fetch_history(limit=200, hours=24)
        anomalies = ml.detect_anomalies(rows)
        return {"anomalies": anomalies[:limit], "total": len(anomalies)}
    except Exception as e:
        logger.error(f"/anomalies error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 6 — GET /predictions
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/predictions", tags=["ML"])
def get_predictions(horizon: int = 10):
    """
    Forecast system metrics for the next N intervals.
    Args:
        horizon: number of future steps to predict (default 10)
    """
    try:
        rows       = db.fetch_history(limit=120, hours=6)
        forecast   = ml.predict(rows, horizon=horizon)
        return {"predictions": forecast, "horizon": horizon}
    except Exception as e:
        logger.error(f"/predictions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Endpoint 7 — POST /metrics/collect
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/metrics/collect", tags=["Metrics"])
def trigger_collection(background_tasks: BackgroundTasks):
    """
    Manually trigger a one-shot metrics collection.
    Runs in background; returns immediately with confirmation.
    """
    def _collect():
        try:
            metrics = collector.collect()
            db.insert_metrics(metrics)
            logger.info("Manual collection complete.")
        except Exception as e:
            logger.error(f"Manual collect error: {e}")

    background_tasks.add_task(_collect)
    return {"status": "collection_triggered", "timestamp": datetime.utcnow().isoformat() + "Z"}


# ─── Static Files (Serve Frontend) ───────────────────────────────────────────
# We mount this at the very end so it doesn't shadow the API routes
frontend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend")
if os.path.exists(frontend_path):
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")
else:
    logger.warning(f"Frontend directory not found at {frontend_path}")
