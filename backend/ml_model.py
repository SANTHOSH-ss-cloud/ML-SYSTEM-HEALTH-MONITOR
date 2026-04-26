"""
ml_model.py — Machine Learning Model
Isolation Forest for anomaly detection + Linear Regression for short-term forecasting.
Uses scikit-learn; saves/loads the model to disk so retraining is not needed on restart.
"""

import os
import pickle
import logging
import numpy as np
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger("SHM.ML")

MODEL_PATH = os.getenv("MODEL_PATH", "shm_model.pkl")

try:
    from sklearn.ensemble import IsolationForest
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    _SKLEARN = True
except ImportError:
    logger.warning("scikit-learn not installed — ML features disabled (stub mode).")
    _SKLEARN = False


class MLModel:
    """
    Two sub-models:
      1. IsolationForest  → anomaly detection on metric vectors.
      2. LinearRegression → per-metric trend forecasting.
    """

    FEATURES = ["cpu_percent", "mem_percent", "disk_percent", "net_sent_mb", "net_recv_mb"]
    ANOMALY_THRESHOLD = -0.1   # Isolation Forest decision score threshold

    def __init__(self):
        self.iso_forest:  Any = None
        self.regressors:  Dict[str, Any] = {}
        self.scaler:      Any = None
        self._trained     = False

    # ── Initialisation ────────────────────────────────────────────────────
    def load_or_train(self, db):
        """Load model from disk; re-train from DB if not found."""
        if os.path.exists(MODEL_PATH):
            try:
                self._load()
                logger.info("ML model loaded from disk.")
                return
            except Exception as e:
                logger.warning(f"Could not load model ({e}); retraining…")

        rows = db.fetch_history(limit=500, hours=48)
        if len(rows) >= 10:
            self.train(rows)
        else:
            logger.warning("Not enough data to train — stub mode active.")

    def train(self, rows: List[Dict]):
        """Train IsolationForest and per-metric regressors."""
        if not _SKLEARN:
            return

        # Reverse rows to be chronological (oldest -> newest) for regression
        chronological_rows = rows[::-1]
        X = self._extract_matrix(chronological_rows)

        if X.shape[0] < 5:
            logger.warning("Too few samples for training.")
            return

        # ── Scaler
        self.scaler = StandardScaler()
        X_scaled    = self.scaler.fit_transform(X)

        # ── Isolation Forest
        self.iso_forest = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=42,
        )
        self.iso_forest.fit(X_scaled)

        # ── Per-metric linear regressors
        t = np.arange(len(chronological_rows)).reshape(-1, 1)
        for i, feat in enumerate(self.FEATURES):
            reg = LinearRegression()
            reg.fit(t, X[:, i])
            self.regressors[feat] = reg

        self._trained = True
        self._save()
        logger.info(f"Model trained on {X.shape[0]} samples.")

    # ── Anomaly Detection ─────────────────────────────────────────────────
    def detect_anomalies(self, rows: List[Dict]) -> List[Dict]:
        """
        Return a filtered list of rows that are anomalous.
        Each entry augmented with 'anomaly_score' and 'anomaly_reasons'.
        """
        if not self._trained or not rows:
            return self._rule_based_anomalies(rows)

        X       = self._extract_matrix(rows)
        X_sc    = self.scaler.transform(X)
        scores  = self.iso_forest.decision_function(X_sc)
        preds   = self.iso_forest.predict(X_sc)       # -1 = anomaly

        anomalies = []
        for i, row in enumerate(rows):
            if preds[i] == -1 or scores[i] < self.ANOMALY_THRESHOLD:
                enriched = dict(row)
                enriched["anomaly_score"]   = round(float(scores[i]), 4)
                enriched["anomaly_reasons"] = self._explain(row)
                anomalies.append(enriched)
        return anomalies

    def _rule_based_anomalies(self, rows: List[Dict]) -> List[Dict]:
        """Simple threshold-based fallback when model isn't trained."""
        result = []
        for row in rows:
            reasons = self._explain(row)
            if reasons:
                r = dict(row)
                r["anomaly_score"]   = -0.5
                r["anomaly_reasons"] = reasons
                result.append(r)
        return result

    def _explain(self, row: Dict) -> List[str]:
        reasons = []
        if (row.get("cpu_percent")  or 0) > 90:
            reasons.append("High CPU (>90%)")
        if (row.get("mem_percent")  or 0) > 90:
            reasons.append("High Memory (>90%)")
        if (row.get("disk_percent") or 0) > 90:
            reasons.append("High Disk (>90%)")
        return reasons

    # ── Forecasting ───────────────────────────────────────────────────────
    def predict(self, rows: List[Dict], horizon: int = 10) -> List[Dict]:
        """
        Predict future metric values for the next `horizon` intervals.
        Returns a list of dicts keyed by metric name.
        """
        if not self._trained or not self.regressors:
            return self._naive_forecast(rows, horizon)

        n = len(rows)
        forecast = []
        future_t = np.arange(n, n + horizon).reshape(-1, 1)
        for step_i in range(horizon):
            t_arr   = np.array([[n + step_i]])
            entry   = {"step": step_i + 1}
            for feat, reg in self.regressors.items():
                val = float(reg.predict(t_arr)[0])
                # Clamp percent features to [0, 100]
                if "percent" in feat:
                    val = max(0.0, min(100.0, val))
                entry[feat] = round(val, 2)
            forecast.append(entry)
        return forecast

    def _naive_forecast(self, rows: List[Dict], horizon: int) -> List[Dict]:
        """Return last-value repeated when model not available."""
        if not rows:
            return []
        last = rows[0]
        return [
            {
                "step":        i + 1,
                "cpu_percent":  last.get("cpu_percent", 0),
                "mem_percent":  last.get("mem_percent", 0),
                "disk_percent": last.get("disk_percent", 0),
                "net_sent_mb":  last.get("net_sent_mb", 0),
                "net_recv_mb":  last.get("net_recv_mb", 0),
            }
            for i in range(horizon)
        ]

    # ── Persistence ───────────────────────────────────────────────────────
    def _save(self):
        with open(MODEL_PATH, "wb") as f:
            pickle.dump({
                "iso_forest":  self.iso_forest,
                "regressors":  self.regressors,
                "scaler":      self.scaler,
                "trained":     self._trained,
            }, f)

    def _load(self):
        with open(MODEL_PATH, "rb") as f:
            data = pickle.load(f)
        self.iso_forest = data["iso_forest"]
        self.regressors = data["regressors"]
        self.scaler     = data["scaler"]
        self._trained   = data.get("trained", False)

    # ── Helpers ───────────────────────────────────────────────────────────
    def _extract_matrix(self, rows: List[Dict]) -> np.ndarray:
        matrix = []
        for r in rows:
            matrix.append([
                r.get("cpu_percent",  0) or 0,
                r.get("mem_percent",  0) or 0,
                r.get("disk_percent", 0) or 0,
                r.get("net_sent_mb",  0) or 0,
                r.get("net_recv_mb",  0) or 0,
            ])
        return np.array(matrix, dtype=float)
