"""
database.py — MySQL Database Manager
Handles schema creation, inserts, and queries for metric history.
Falls back gracefully to SQLite when MySQL is unavailable (useful for local dev).
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SHM.DB")

# ── Try MySQL first, fall back to sqlite3 ─────────────────────────────────
try:
    import mysql.connector
    from mysql.connector import pooling
    _USE_MYSQL = True
except ImportError:
    import sqlite3
    _USE_MYSQL = False
    logger.warning("mysql-connector-python not installed — using SQLite fallback.")


# ── Configuration from environment ────────────────────────────────────────
DB_CONFIG = {
    "host":     os.getenv("DB_HOST",     "localhost"),
    "port":     int(os.getenv("DB_PORT", "3306")),
    "database": os.getenv("DB_NAME",     "system_health"),
    "user":     os.getenv("DB_USER",     "shm_user"),
    "password": os.getenv("DB_PASSWORD", "shm_password"),
}

SQLITE_PATH = os.getenv("SQLITE_PATH", "system_health.db")


class DatabaseManager:
    """
    Thin abstraction over MySQL / SQLite.
    Stores raw metric JSON blobs plus an extracted summary row per snapshot.
    """

    def __init__(self):
        self._pool: Optional[Any] = None
        self._sqlite_conn: Optional[Any] = None

    # ── Connection helpers ─────────────────────────────────────────────────
    def _get_mysql_pool(self):
        if self._pool is None:
            self._pool = mysql.connector.pooling.MySQLConnectionPool(
                pool_name="shm_pool",
                pool_size=5,
                **DB_CONFIG,
            )
        return self._pool

    def _mysql_conn(self):
        return self._get_mysql_pool().get_connection()

    def _sqlite_conn_lazy(self):
        if self._sqlite_conn is None:
            self._sqlite_conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
            self._sqlite_conn.row_factory = sqlite3.Row
        return self._sqlite_conn

    def _execute(self, sql: str, params=(), *, fetch=False, many=False):
        """Universal execute — routes to MySQL or SQLite automatically."""
        if _USE_MYSQL:
            conn = self._mysql_conn()
            try:
                cur = conn.cursor(dictionary=True)
                if many:
                    cur.executemany(sql, params)
                else:
                    cur.execute(sql, params)
                result = cur.fetchall() if fetch else None
                conn.commit()
                return result
            finally:
                conn.close()
        else:
            # SQLite: convert %s → ?
            sql_lite = sql.replace("%s", "?")
            conn = self._sqlite_conn_lazy()
            cur  = conn.cursor()
            if many:
                cur.executemany(sql_lite, params)
            else:
                cur.execute(sql_lite, params)
            if fetch:
                rows = cur.fetchall()
                return [dict(r) for r in rows]
            conn.commit()
            return None

    # ── Schema ─────────────────────────────────────────────────────────────
    def initialize_schema(self):
        """Create tables if they don't exist."""
        logger.info("Initialising database schema…")
        if _USE_MYSQL:
            self._execute(f"CREATE DATABASE IF NOT EXISTS `{DB_CONFIG['database']}`")

        metrics_table = """
            CREATE TABLE IF NOT EXISTS metrics (
                id             INTEGER PRIMARY KEY {auto},
                collected_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                cpu_percent    FLOAT,
                mem_percent    FLOAT,
                disk_percent   FLOAT,
                net_sent_mb    FLOAT,
                net_recv_mb    FLOAT,
                process_count  INTEGER,
                health_score   FLOAT,
                raw_json       TEXT
            )
        """.format(auto="AUTO_INCREMENT" if _USE_MYSQL else "AUTOINCREMENT")

        anomalies_table = """
            CREATE TABLE IF NOT EXISTS anomalies (
                id           INTEGER PRIMARY KEY {auto},
                detected_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                metric_id    INTEGER,
                anomaly_type VARCHAR(80),
                score        FLOAT,
                details      TEXT
            )
        """.format(auto="AUTO_INCREMENT" if _USE_MYSQL else "AUTOINCREMENT")

        self._execute(metrics_table)
        self._execute(anomalies_table)
        logger.info("Schema ready.")

    # ── Writes ─────────────────────────────────────────────────────────────
    def insert_metrics(self, metrics: Dict[str, Any]):
        """Persist a metrics snapshot."""
        try:
            cpu   = metrics.get("cpu", {}).get("usage_percent", 0)
            mem   = metrics.get("memory", {}).get("usage_percent", 0)
            parts = metrics.get("disk", {}).get("partitions", [])
            disk  = parts[0]["usage_percent"] if parts else 0
            net   = metrics.get("network", {})
            procs = metrics.get("processes", {}).get("total", 0)
            score = metrics.get("health_score", 100)

            sql = """
                INSERT INTO metrics
                    (cpu_percent, mem_percent, disk_percent,
                     net_sent_mb, net_recv_mb, process_count,
                     health_score, raw_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """
            self._execute(sql, (
                cpu, mem, disk,
                net.get("bytes_sent_mb", 0),
                net.get("bytes_recv_mb", 0),
                procs, score,
                json.dumps(metrics),
            ))
        except Exception as e:
            logger.error(f"insert_metrics failed: {e}")

    # ── Reads ──────────────────────────────────────────────────────────────
    def fetch_history(self, limit: int = 60, hours: int = 1) -> List[Dict]:
        """Return recent metric rows as dicts."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            SELECT id, collected_at, cpu_percent, mem_percent, disk_percent,
                   net_sent_mb, net_recv_mb, process_count, health_score
            FROM metrics
            WHERE collected_at >= %s
            ORDER BY collected_at DESC
            LIMIT %s
        """
        rows = self._execute(sql, (cutoff, limit), fetch=True) or []
        # Normalise datetime objects to strings
        for r in rows:
            if isinstance(r.get("collected_at"), datetime):
                r["collected_at"] = r["collected_at"].isoformat() + "Z"
        return rows

    def fetch_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Return aggregate statistics over the last N hours."""
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
        sql = """
            SELECT
                COUNT(*)        AS total_records,
                AVG(cpu_percent)  AS cpu_avg,
                MAX(cpu_percent)  AS cpu_max,
                MIN(cpu_percent)  AS cpu_min,
                AVG(mem_percent)  AS mem_avg,
                MAX(mem_percent)  AS mem_max,
                MIN(mem_percent)  AS mem_min,
                AVG(disk_percent) AS disk_avg,
                MAX(disk_percent) AS disk_max,
                AVG(health_score) AS health_avg,
                MIN(health_score) AS health_min
            FROM metrics
            WHERE collected_at >= %s
        """
        rows = self._execute(sql, (cutoff,), fetch=True) or [{}]
        row  = rows[0] if rows else {}
        return {
            "hours_window": hours,
            "total_records": row.get("total_records", 0),
            "cpu":  {"avg": _r(row, "cpu_avg"),  "max": _r(row, "cpu_max"),  "min": _r(row, "cpu_min")},
            "mem":  {"avg": _r(row, "mem_avg"),  "max": _r(row, "mem_max"),  "min": _r(row, "mem_min")},
            "disk": {"avg": _r(row, "disk_avg"), "max": _r(row, "disk_max")},
            "health": {"avg": _r(row, "health_avg"), "min": _r(row, "health_min")},
        }


# ── Helper ────────────────────────────────────────────────────────────────
def _r(d: dict, key: str, decimals: int = 1) -> Optional[float]:
    v = d.get(key)
    return round(float(v), decimals) if v is not None else None
