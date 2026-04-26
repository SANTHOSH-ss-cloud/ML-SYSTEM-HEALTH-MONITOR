"""
algorithms.py — Health Analysis Algorithms
Pure-Python scoring and analysis helpers; no ML library required.
"""

from typing import Any, Dict, List, Optional


class HealthAnalyzer:
    """
    Rule-based health scoring and alert generation.
    
    Health score: 0 (critical) → 100 (perfect).
    Deductions are weighted and additive; the score never goes below 0.
    """

    # ── Thresholds ────────────────────────────────────────────────────────
    THRESHOLDS = {
        "cpu": {
            "warning":  70,   # -5 pts
            "high":     85,   # -15 pts
            "critical": 95,   # -30 pts
        },
        "mem": {
            "warning":  70,
            "high":     85,
            "critical": 95,
        },
        "disk": {
            "warning":  70,
            "high":     85,
            "critical": 95,
        },
        "swap": {
            "warning":  50,
            "high":     70,
            "critical": 90,
        },
    }

    DEDUCTIONS = {
        "warning":  5,
        "high":     15,
        "critical": 30,
    }

    # ── Public API ────────────────────────────────────────────────────────
    def health_score(self, metrics: Dict[str, Any]) -> float:
        """
        Compute an overall health score (0–100) from a metrics snapshot.
        """
        score = 100.0

        cpu_pct  = metrics.get("cpu",    {}).get("usage_percent",   0) or 0
        mem_pct  = metrics.get("memory", {}).get("usage_percent",   0) or 0
        swap_pct = metrics.get("memory", {}).get("swap_percent",    0) or 0
        parts    = metrics.get("disk",   {}).get("partitions",      [])
        disk_pct = parts[0]["usage_percent"] if parts else 0

        score -= self._deduct("cpu",  cpu_pct)
        score -= self._deduct("mem",  mem_pct)
        score -= self._deduct("disk", disk_pct)
        score -= self._deduct("swap", swap_pct)

        return max(0.0, round(score, 1))

    def alert_level(self, score: float) -> str:
        """Map a health score to a human-readable alert level."""
        if score >= 85:
            return "healthy"
        if score >= 70:
            return "warning"
        if score >= 50:
            return "elevated"
        return "critical"

    def generate_alerts(self, metrics: Dict[str, Any]) -> List[Dict]:
        """
        Produce a list of alert dicts for all thresholds exceeded.
        Each alert: { metric, value, level, message }
        """
        alerts: List[Dict] = []

        cpu_pct  = metrics.get("cpu",    {}).get("usage_percent",   0) or 0
        mem_pct  = metrics.get("memory", {}).get("usage_percent",   0) or 0
        swap_pct = metrics.get("memory", {}).get("swap_percent",    0) or 0
        parts    = metrics.get("disk",   {}).get("partitions",      [])
        disk_pct = parts[0]["usage_percent"] if parts else 0
        temp     = metrics.get("cpu",    {}).get("temperature_c")

        self._check(alerts, "cpu",  cpu_pct,  "CPU usage")
        self._check(alerts, "mem",  mem_pct,  "Memory usage")
        self._check(alerts, "disk", disk_pct, "Disk usage")
        self._check(alerts, "swap", swap_pct, "Swap usage")

        if temp is not None and temp > 80:
            alerts.append({
                "metric":  "temperature",
                "value":   temp,
                "level":   "critical" if temp > 90 else "warning",
                "message": f"CPU temperature is {temp}°C",
            })

        return alerts

    def trend(self, history: List[Dict], metric: str = "cpu_percent",
              window: int = 5) -> Dict:
        """
        Simple linear trend over the last `window` samples.
        Returns: { direction: 'rising'|'falling'|'stable', slope, values }
        """
        vals = [r.get(metric, 0) or 0 for r in history[:window]]
        if len(vals) < 2:
            return {"direction": "stable", "slope": 0.0, "values": vals}

        n     = len(vals)
        x_mean = (n - 1) / 2
        y_mean = sum(vals) / n
        num    = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(vals))
        den    = sum((i - x_mean) ** 2 for i in range(n))
        slope  = num / den if den else 0.0

        direction = "stable"
        if slope > 0.5:
            direction = "rising"
        elif slope < -0.5:
            direction = "falling"

        return {"direction": direction, "slope": round(slope, 3), "values": vals}

    def top_processes_impact(self, metrics: Dict[str, Any]) -> List[Dict]:
        """
        Return top processes with a simple 'impact' score.
        impact = 0.7 * cpu + 0.3 * mem  (both as % of 100)
        """
        procs = metrics.get("processes", {}).get("top_10", [])
        scored = []
        for p in procs:
            impact = round(0.7 * (p.get("cpu", 0) or 0) + 0.3 * (p.get("mem", 0) or 0), 2)
            scored.append({**p, "impact_score": impact})
        return sorted(scored, key=lambda x: x["impact_score"], reverse=True)

    # ── Internal helpers ──────────────────────────────────────────────────
    def _deduct(self, key: str, value: float) -> float:
        th = self.THRESHOLDS.get(key, {})
        if value >= th.get("critical", 999):
            return self.DEDUCTIONS["critical"]
        if value >= th.get("high", 999):
            return self.DEDUCTIONS["high"]
        if value >= th.get("warning", 999):
            return self.DEDUCTIONS["warning"]
        return 0.0

    def _check(self, alerts: List, key: str, value: float, label: str):
        th = self.THRESHOLDS.get(key, {})
        if value >= th.get("critical", 999):
            level = "critical"
        elif value >= th.get("high", 999):
            level = "high"
        elif value >= th.get("warning", 999):
            level = "warning"
        else:
            return
        alerts.append({
            "metric":  key,
            "value":   round(value, 1),
            "level":   level,
            "message": f"{label} is at {round(value,1)}%",
        })
